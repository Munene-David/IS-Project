import uuid as uuid_lib
from decimal import Decimal, InvalidOperation

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone as django_tz
import threading

from .models import (
    PriceGuide, Task, Message, TaskRequest,
    TaskCompletion, Dispute, CancellationPolicy, AuditLog,
    CheckIn, LocationConsent, LocationPolicy,
)
from payments.models import Transaction, TransactionLedger
from payments.mpesa_service import mpesa_service
from payments import refund_service
from .serializers import (
    PriceGuideSerializer,
    TaskListSerializer,
    TaskDetailSerializer,
    TaskCreateSerializer,
    MessageSerializer,
    TaskRequestSerializer,
    StudentInboxTaskRequestSerializer,
    TaskCompletionSerializer,
    DisputeSerializer,
    CancellationPolicySerializer,
    CheckInSerializer,
    LocationPolicySerializer,
)
from . import matching
from . import geo
from .task_transitions import (
    transition, InvalidTransition,
    DELETION_BLOCKED_STATUSES, CANCEL_REQUIRED_STATUSES, FREE_CANCEL_STATUSES,
)


# ---------------------------------------------------------------------------
# Price Guide
# ---------------------------------------------------------------------------

class PriceGuideView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, category=None):
        if category:
            guide = PriceGuide.objects.filter(category__iexact=category).first()
            if not guide:
                return Response(
                    {'error': f'No price guide found for category {category}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            return Response(PriceGuideSerializer(guide).data)
        guides = PriceGuide.objects.all()
        return Response(PriceGuideSerializer(guides, many=True).data)


# ---------------------------------------------------------------------------
# Main Task ViewSet
# ---------------------------------------------------------------------------

class TaskViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        # Exclude soft-deleted tasks and seed/system tasks from all listings
        qs = Task.objects.filter(
            is_deleted=False
        ).exclude(
            title__startswith='_'
        ).order_by('-created_at')

        user = self.request.user
        category = self.request.query_params.get('category')
        task_status = self.request.query_params.get('status')
        search = self.request.query_params.get('search')
        my_tasks = self.request.query_params.get('my_tasks')

        if my_tasks:
            # Explicit "my tasks" request
            if user.is_household():
                qs = qs.filter(household_owner=user)
            else:
                # Student: tasks they have a request for OR are assigned to
                request_task_ids = TaskRequest.objects.filter(
                    student=user
                ).values_list('task_id', flat=True)
                qs = qs.filter(
                    Q(assigned_student=user) | Q(id__in=request_task_ids)
                )
        else:
            # Default listing — enforce role-based visibility
            if user.is_household():
                # Households only ever see their own tasks
                qs = qs.filter(household_owner=user)
            elif user.is_student():
                # Students only see:
                #   1. Tasks that were broadcast to them (they have a TaskRequest)
                #   2. Tasks they are assigned to
                # They do NOT see tasks belonging to other households/students
                request_task_ids = TaskRequest.objects.filter(
                    student=user
                ).values_list('task_id', flat=True)
                qs = qs.filter(
                    Q(assigned_student=user) | Q(id__in=request_task_ids)
                )
            # Admins see everything (no extra filter)

        if category:
            qs = qs.filter(category__iexact=category)
        if task_status:
            qs = qs.filter(status=task_status)
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return TaskCreateSerializer
        if self.action == 'retrieve':
            return TaskDetailSerializer
        return TaskListSerializer

    def perform_create(self, serializer):
        user = self.request.user
        category = serializer.validated_data.get('category')
        rec_price = PriceGuide.get_recommended_price(category)
        task = serializer.save(
            household_owner=user,
            recommended_price=rec_price,
            status='Posted'
        )
        t = threading.Thread(target=matching.broadcast_task, args=[task])
        t.daemon = True
        t.start()

    def destroy(self, request, *args, **kwargs):
        """
        Soft-delete a task.  Rules:
        - Only the household owner may delete.
        - Blocked when status ∈ DELETION_BLOCKED_STATUSES.
        - Blocked when there is an active payment (escrow Held).
        - Assigned/NoShow: direct to cancel-with-refund instead.
        - For free-cancel statuses: notify and withdraw pending requests.
        """
        task = self.get_object()
        user = request.user

        if task.household_owner != user:
            return Response(
                {'error': 'Only the task owner can delete a task.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if task.status in DELETION_BLOCKED_STATUSES:
            reason_map = {
                'InProgress': 'The student is currently working on this task.',
                'AwaitingConfirmation': 'Awaiting your confirmation. Mark complete or raise a dispute instead.',
                'Completed': 'Completed tasks cannot be deleted — they are needed for records.',
                'Disputed': 'A dispute is in progress. Wait for admin resolution.',
            }
            reason = reason_map.get(task.status, f'Task is {task.status}.')
            return Response(
                {'error': f'Cannot delete: {reason}', 'status': task.status},
                status=status.HTTP_400_BAD_REQUEST
            )

        if task.status in CANCEL_REQUIRED_STATUSES:
            return Response(
                {
                    'error': (
                        'This task has an assigned student or active payment. '
                        'Use POST /tasks/{id}/cancel/ to cancel and trigger the refund policy.'
                    ),
                    'status': task.status,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Block if escrow is Held (payment exists)
        escrow = getattr(task, 'escrow_transaction', None)
        if escrow and escrow.status == 'Held':
            return Response(
                {
                    'error': (
                        'Escrow funds are held for this task. '
                        'Use POST /tasks/{id}/cancel/ to cancel and trigger a refund.'
                    ),
                    'status': task.status,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Safe to soft-delete: withdraw pending requests and notify students
        with db_transaction.atomic():
            pending_requests = TaskRequest.objects.filter(
                task=task, status__in=['SENT', 'VIEWED', 'ACCEPTED']
            ).select_related('student')
            from users.notifications import Notification
            for req in pending_requests:
                Notification.send(
                    recipient=req.student,
                    notification_type='task_deleted',
                    title='Task removed',
                    message=(
                        f'The task "{task.title}" you were matched with has been removed by the household.'
                    ),
                    task_id=task.id,
                )
            pending_requests.update(status='EXPIRED')

            task.is_deleted = True
            task.deleted_at = django_tz.now()
            task.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

            AuditLog.log(
                task=task, actor=user, action='transition',
                from_status=task.status, to_status='DELETED',
                notes='Soft-deleted by household owner.',
            )

        return Response({'message': 'Task deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)

    # ----------------------------------------------------------------
    # Completion verification
    # ----------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='checkin')
    def student_checkin(self, request, pk=None):
        """
        Student submits the 4-digit start code together with a device
        location snapshot (captured once, at this event only).

        Body: {
          start_code, lat, lng, accuracy_m,
          device_time (ISO string), mock_location (bool),
          late_sync (bool, offline queue), device_info (object)
        }

        The server validates the code, computes the Haversine distance to the
        task pin and returns one of:
          VERIFIED | OUT_OF_RANGE | LOW_ACCURACY | LOCATION_DENIED |
          FLAGGED_MOCK | WRONG_CODE

        Out-of-range / low-accuracy check-ins are allowed but flagged (the
        student may retry to upgrade to VERIFIED).  A denied location
        permission blocks starting, unless LocationPolicy.allow_flagged_when_denied.
        Mock locations are rejected.  Every attempt is recorded in the
        append-only CheckIn table.
        """
        task = self.get_object()
        user = request.user

        if task.assigned_student != user:
            return Response({'error': 'You are not the assigned student.'}, status=status.HTTP_403_FORBIDDEN)

        retry_mode = task.status == 'InProgress'
        if task.status not in ('Assigned', 'InProgress'):
            return Response(
                {'error': f'Check-in is only allowed when task is Assigned (current: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if retry_mode:
            # Retries only make sense while the accepted check-in is flagged
            accepted = task.checkins.filter(type='START').order_by('-server_time').first()
            if accepted is None or accepted.result == 'VERIFIED':
                return Response(
                    {'error': 'The task already has a verified check-in; no retry needed.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # --- Consent must be recorded before the first check-in -------------
        if not LocationConsent.objects.filter(student=user).exists():
            return Response(
                {
                    'error': 'You must accept the location-collection notice before checking in.',
                    'code': 'consent_required',
                    'consent_version': geo.LOCATION_CONSENT_VERSION,
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Retrieve the start code (created when task was funded)
        try:
            completion = task.completion
        except TaskCompletion.DoesNotExist:
            return Response({'error': 'Start code not generated yet. Contact support.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- Parse the payload -----------------------------------------------
        submitted_code = str(request.data.get('start_code', '')).strip()
        lat = _parse_coord(request.data.get('lat'))
        lng = _parse_coord(request.data.get('lng'))
        try:
            accuracy_m = float(request.data['accuracy_m']) if request.data.get('accuracy_m') is not None else None
        except (TypeError, ValueError):
            accuracy_m = None
        device_time = geo.parse_device_time(request.data.get('device_time'))
        mock_location = geo.parse_bool(request.data.get('mock_location'))
        late_sync = geo.parse_bool(request.data.get('late_sync'))
        device_info = request.data.get('device_info') if isinstance(request.data.get('device_info'), dict) else {}
        policy = LocationPolicy.get()

        # --- Start code check --------------------------------------------------
        if not retry_mode:
            if not submitted_code:
                return Response({'error': 'start_code is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if submitted_code != completion.start_code:
                self._record_checkin(
                    task, user, 'ARRIVAL', lat, lng, accuracy_m, device_time,
                    'WRONG_CODE', policy, mock_location, late_sync, device_info,
                )
                return Response(
                    {'error': 'Incorrect start code.', 'result': 'WRONG_CODE'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # --- Location verification ----------------------------------------------
        previous = (
            CheckIn.objects
            .filter(student=user, lat__isnull=False)
            .exclude(task=task)
            .order_by('-server_time')
            .first()
        )
        evaluation = geo.evaluate_checkin(
            task, lat, lng, accuracy_m, mock_location, device_time, policy,
            previous_checkin=previous,
        )
        result = evaluation['result']
        flagged_by = {
            'mock_location': mock_location,
            'late_sync': geo.is_late_sync(device_time, late_sync, policy.max_time_skew_seconds),
            'impossible_jump': evaluation['impossible_jump'],
        }

        # --- Gate: rejected outcomes --------------------------------------------
        denied_blocked = result == 'LOCATION_DENIED' and not policy.allow_flagged_when_denied
        if result == 'FLAGGED_MOCK' or denied_blocked:
            self._record_checkin(
                task, user, 'ARRIVAL', lat, lng, accuracy_m, device_time,
                result, policy, mock_location, flagged_by['late_sync'], device_info,
                time_skew_seconds=evaluation['time_skew_s'],
                impossible_jump=flagged_by['impossible_jump'],
            )
            if result == 'FLAGGED_MOCK':
                message = (
                    'Your location appears to be simulated or mocked. '
                    'Check-in is rejected — disable location mocking and try again.'
                )
            else:
                message = (
                    'Location permission is required to check in. '
                    'Allow location access in your settings and try again.'
                )
            return Response(
                {'error': message, 'result': result, 'retry': True},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Accepted: VERIFIED or flagged (OUT_OF_RANGE / LOW_ACCURACY /
        #     LOCATION_DENIED with admin override) -------------------------------
        now = django_tz.now()
        checkin = self._record_checkin(
            task, user,
            'ARRIVAL' if retry_mode else 'START',
            lat, lng, accuracy_m, device_time,
            result, policy, mock_location, flagged_by['late_sync'], device_info,
            time_skew_seconds=evaluation['time_skew_s'],
            impossible_jump=flagged_by['impossible_jump'],
        )

        if not retry_mode:
            with db_transaction.atomic():
                completion.start_code_verified = True
                completion.arrived_at = now
                completion.started_at = now
                if lat is not None:
                    completion.checkin_lat = lat
                if lng is not None:
                    completion.checkin_lng = lng
                completion.save()
                try:
                    transition(task, 'InProgress', actor=user,
                               notes=f'Student checked in with start code [{result}].')
                except InvalidTransition as e:
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        from users.notifications import Notification
        if not retry_mode:
            if result == 'VERIFIED':
                Notification.send(
                    recipient=task.household_owner,
                    notification_type='general',
                    title='Student has arrived! ✅',
                    message=(
                        f'{user.first_name or user.username} checked in and started '
                        f'"{task.title}". Location verified.'
                    ),
                    task_id=task.id,
                )
            else:
                Notification.send(
                    recipient=task.household_owner,
                    notification_type='general',
                    title='Student checked in — location flagged ⚠️',
                    message=(
                        f'{user.first_name or user.username} checked in for '
                        f'"{task.title}", but the location check was flagged: '
                        f'{result.replace("_", " ").lower()}. '
                        f'You may want to confirm they arrived in person.'
                    ),
                    task_id=task.id,
                )

        return Response({
            'message': (
                'Check-in successful — task is now In Progress.'
                if not retry_mode else 'Retry recorded.'
            ),
            'result': result,
            'flagged': result != 'VERIFIED',
            'started': not retry_mode,
            'status': task.status,
            'distance_m': checkin.distance_m,
            'accuracy_m': checkin.accuracy_m,
            'retry_allowed': result != 'VERIFIED',
            'started_at': completion.started_at,
        })

    @staticmethod
    def _record_checkin(task, student, checkin_type, lat, lng, accuracy_m,
                        device_time, result, policy, mock_location, late_sync,
                        device_info, time_skew_seconds=None, impossible_jump=False):
        """Append one immutable check-in row (never updates existing rows)."""
        distance_m = None
        if lat is not None and lng is not None and task.location_lat is not None and task.location_lng is not None:
            distance_m = geo.haversine_m(task.location_lat, task.location_lng, lat, lng)
        return CheckIn.objects.create(
            task=task,
            student=student,
            type=checkin_type,
            lat=lat, lng=lng,
            accuracy_m=accuracy_m,
            distance_m=distance_m,
            device_time=device_time,
            result=result,
            mock_location_flag=mock_location,
            late_sync_flag=late_sync,
            time_skew_seconds=int(time_skew_seconds) if time_skew_seconds is not None else None,
            impossible_jump_flag=impossible_jump,
            device_info=device_info,
        )

    # ----------------------------------------------------------------
    # Admin: location audit / dispute map view
    # ----------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='location-audit')
    def location_audit(self, request, pk=None):
        """
        ADMIN ONLY.  Everything an admin needs to adjudicate a location
        dispute on one screen: the task pin + geofence, every check-in
        attempt (point, distance, accuracy, timestamps, flags), the
        household's complaint (dispute) and the full chat history.
        """
        task = self.get_object()
        user = request.user
        if not user.is_system_admin():
            return Response({'error': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)

        checkins = CheckInSerializer(task.checkins.all(), many=True).data
        dispute = None
        try:
            dispute = DisputeSerializer(task.dispute).data
        except Dispute.DoesNotExist:
            pass
        messages = MessageSerializer(
            task.messages.select_related('sender', 'receiver').order_by('timestamp'),
            many=True,
        ).data

        return Response({
            'task': {
                'id': task.id,
                'title': task.title,
                'status': task.status,
                'household_owner': task.household_owner.username,
                'assigned_student': task.assigned_student.username if task.assigned_student else None,
                'location_address': task.location_address,
                'location_landmark': task.location_landmark,
                'location_lat': str(task.location_lat) if task.location_lat is not None else None,
                'location_lng': str(task.location_lng) if task.location_lng is not None else None,
                'geofence_radius_m': task.geofence_radius_m,
                'scheduled_date': task.scheduled_date,
                'scheduled_time': task.scheduled_time,
            },
            'checkins': checkins,
            'dispute': dispute,
            'messages': messages,
        })

    @action(detail=True, methods=['post'], url_path='student-complete',
            parser_classes=[MultiPartParser, FormParser, JSONParser])
    def student_mark_complete(self, request, pk=None):
        """
        Student marks work finished.
        Optional: after_photo (file upload), plus an optional finish-location
        snapshot {lat, lng, accuracy_m, device_time, device_info} captured at
        this event only (never in the background).
        Moves task InProgress → AwaitingConfirmation and starts 48-hour window.
        """
        task = self.get_object()
        user = request.user

        if task.assigned_student != user:
            return Response({'error': 'You are not the assigned student.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status != 'InProgress':
            return Response(
                {'error': f'Cannot mark complete from status: {task.status}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # A finish-location snapshot requires consent, same as check-in.
        # Checked BEFORE the atomic block so nothing commits on a rejection.
        # Tasks started before this feature (no consent recorded) simply
        # finish without the optional snapshot — completion never blocks.
        lat = _parse_coord(request.data.get('lat'))
        lng = _parse_coord(request.data.get('lng'))
        if lat is not None and lng is not None:
            if not LocationConsent.objects.filter(student=user).exists():
                lat = lng = None

        with db_transaction.atomic():
            # Record finish timestamp
            completion, _ = TaskCompletion.objects.get_or_create(task=task)
            completion.finished_at = django_tz.now()
            after_photo = request.FILES.get('after_photo')
            if after_photo:
                _validate_photo(after_photo)
                completion.after_photo = after_photo
            completion.save()

            # Optional FINISH check-in location snapshot
            if lat is not None and lng is not None:
                policy = LocationPolicy.get()
                try:
                    acc = float(request.data['accuracy_m']) if request.data.get('accuracy_m') is not None else None
                except (TypeError, ValueError):
                    acc = None
                device_time = geo.parse_device_time(request.data.get('device_time'))
                mock_location = geo.parse_bool(request.data.get('mock_location'))
                evaluation = geo.evaluate_checkin(
                    task, lat, lng, acc,
                    mock_location, device_time, policy,
                )
                self._record_checkin(
                    task, user, 'FINISH', lat, lng, acc, device_time,
                    evaluation['result'], policy,
                    mock_location,
                    geo.parse_bool(request.data.get('late_sync')),
                    request.data.get('device_info') if isinstance(request.data.get('device_info'), dict) else {},
                    time_skew_seconds=evaluation['time_skew_s'],
                    impossible_jump=evaluation['impossible_jump'],
                )

            # Set 48-hour confirmation deadline
            deadline = django_tz.now() + django_tz.timedelta(hours=48)
            task.confirmation_deadline = deadline
            task.save(update_fields=['confirmation_deadline', 'updated_at'])

            try:
                transition(task, 'AwaitingConfirmation', actor=user, notes='Student marked task finished.')
            except InvalidTransition as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        from users.notifications import Notification
        Notification.send(
            recipient=task.household_owner,
            notification_type='awaiting_confirmation',
            title='Work finished — please confirm',
            message=(
                f'{user.first_name or user.username} has finished "{task.title}". '
                f'You have 48 hours to confirm or report a problem. '
                f'Payment will be released automatically after {deadline.strftime("%b %d, %H:%M")} UTC.'
            ),
            task_id=task.id,
        )

        return Response({
            'message': 'Task marked as finished. Awaiting household confirmation.',
            'status': task.status,
            'confirmation_deadline': task.confirmation_deadline,
        })

    @action(detail=True, methods=['post'], url_path='confirm-completion')
    def household_confirm_completion(self, request, pk=None):
        """
        Household confirms work is satisfactory.
        Moves AwaitingConfirmation → Completed and releases escrow.
        """
        task = self.get_object()
        user = request.user

        if task.household_owner != user:
            return Response({'error': 'Only the task owner can confirm completion.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status != 'AwaitingConfirmation':
            return Response(
                {'error': f'Task is not awaiting confirmation (status: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        idem_key = uuid_lib.uuid4()
        with db_transaction.atomic():
            try:
                transition(task, 'Completed', actor=user, notes='Household confirmed completion.')
            except InvalidTransition as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            ok, msg, _ = refund_service.release_to_student(task, actor=user, idempotency_key=idem_key)
            if not ok:
                # Rollback the transition by re-setting status (or just log the payment failure)
                task.status = 'AwaitingConfirmation'
                task.save(update_fields=['status', 'updated_at'])
                return Response({'error': f'Completion recorded but payment release failed: {msg}'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        from users.notifications import Notification
        if task.assigned_student:
            Notification.send(
                recipient=task.assigned_student,
                notification_type='payment_received',
                title='Payment released! 💰',
                message=(
                    f'{user.first_name or user.username} confirmed "{task.title}" is complete. '
                    f'Your payment of KES {task.posted_price} has been released.'
                ),
                task_id=task.id,
            )

        return Response({'message': 'Task confirmed and payment released.', 'status': task.status})

    @action(detail=True, methods=['get'], url_path='start-code')
    def get_start_code(self, request, pk=None):
        """
        Household retrieves the 4-digit start code.
        Only visible to the household owner, only after payment is confirmed (Assigned).
        """
        task = self.get_object()
        user = request.user

        if task.household_owner != user:
            return Response({'error': 'Only the household owner can view the start code.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status not in ('Assigned', 'InProgress'):
            return Response(
                {'error': f'Start code is only available once the task is Assigned (current: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            completion = task.completion
        except TaskCompletion.DoesNotExist:
            return Response({'error': 'Start code not yet generated.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'start_code': completion.start_code})

    @action(detail=True, methods=['post'], url_path='upload-before-photo',
            parser_classes=[MultiPartParser, FormParser])
    def upload_before_photo(self, request, pk=None):
        """Student uploads a before-work photo (before check-in or immediately after)."""
        task = self.get_object()
        user = request.user

        if task.assigned_student != user:
            return Response({'error': 'Only the assigned student can upload photos.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status not in ('Assigned', 'InProgress'):
            return Response(
                {'error': 'Photos can only be uploaded when task is Assigned or InProgress.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        photo = request.FILES.get('before_photo')
        if not photo:
            return Response({'error': 'before_photo file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        _validate_photo(photo)

        completion, _ = TaskCompletion.objects.get_or_create(task=task)
        completion.before_photo = photo
        completion.save(update_fields=['before_photo', 'updated_at'])

        return Response({'message': 'Before photo uploaded.'})

    # ----------------------------------------------------------------
    # Completion (legacy path kept for backward compat — routes to new paths)
    # ----------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='complete')
    def mark_complete(self, request, pk=None):
        """
        Legacy endpoint kept for backward compatibility.
        Student call → student_mark_complete (InProgress → AwaitingConfirmation).
        Household call → household_confirm_completion (AwaitingConfirmation → Completed).
        """
        task = self.get_object()
        user = request.user

        if user != task.household_owner and user != task.assigned_student:
            return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)

        if user == task.assigned_student:
            # Legacy: treat as student marking done
            if task.status == 'Assigned':
                # Old flow didn't require start code — allow direct transition for backward compat
                try:
                    transition(task, 'InProgress', actor=user, notes='Legacy mark-complete (start).')
                except InvalidTransition as e:
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                from users.notifications import Notification
                Notification.send(
                    recipient=task.household_owner,
                    notification_type='general',
                    title='Student started the task!',
                    message=f'{user.username} has started working on "{task.title}".',
                    task_id=task.id,
                )
                return Response({'message': 'Task is now In Progress.', 'status': task.status})
            return self.student_mark_complete(request, pk=pk)

        if user == task.household_owner:
            if task.status == 'InProgress':
                # Old flow: household completes directly (no AwaitingConfirmation)
                # Accept this for backward compat but go through the new confirmation path
                # by first moving to AwaitingConfirmation then immediately confirming.
                idem_key = uuid_lib.uuid4()
                with db_transaction.atomic():
                    # Set deadline then transition
                    task.confirmation_deadline = django_tz.now() + django_tz.timedelta(hours=48)
                    task.save(update_fields=['confirmation_deadline', 'updated_at'])
                    try:
                        transition(task, 'AwaitingConfirmation', actor=user,
                                   notes='Direct mark-complete by household (legacy).')
                    except InvalidTransition as e:
                        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

                # Then confirm immediately
                return self.household_confirm_completion(request, pk=pk)

            if task.status == 'AwaitingConfirmation':
                return self.household_confirm_completion(request, pk=pk)

        return Response({'status': task.status})

    # ----------------------------------------------------------------
    # Disputes
    # ----------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='dispute')
    def raise_dispute(self, request, pk=None):
        """
        Household raises a dispute within the confirmation window.
        Body: { reason, description }
        Freezes payment (task → Disputed).  One dispute per task.
        """
        task = self.get_object()
        user = request.user

        if user != task.household_owner:
            return Response({'error': 'Only the household owner can raise a dispute.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status not in ('AwaitingConfirmation', 'InProgress'):
            return Response(
                {'error': f'Disputes can only be raised during InProgress or AwaitingConfirmation (current: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Enforce one-dispute-per-task
        if Dispute.objects.filter(task=task).exists():
            return Response({'error': 'A dispute has already been raised for this task.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '')
        description = request.data.get('description', '')
        if not reason or not description:
            return Response({'error': 'reason and description are required.'}, status=status.HTTP_400_BAD_REQUEST)

        valid_reasons = [r[0] for r in Dispute.REASON_CHOICES]
        if reason not in valid_reasons:
            return Response(
                {'error': f'Invalid reason. Must be one of: {", ".join(valid_reasons)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with db_transaction.atomic():
            dispute = Dispute.objects.create(
                task=task,
                raised_by=user,
                reason=reason,
                description=description,
            )
            try:
                transition(task, 'Disputed', actor=user, notes=f'Dispute raised: {reason}')
            except InvalidTransition as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            AuditLog.log(
                task=task, actor=user, action='dispute_event',
                notes=f'Dispute #{dispute.id} raised. Reason: {reason}.',
            )

        from users.notifications import Notification
        # Notify student
        if task.assigned_student:
            Notification.send(
                recipient=task.assigned_student,
                notification_type='dispute_raised',
                title='A dispute has been raised',
                message=(
                    f'The household raised a dispute on "{task.title}": {reason}. '
                    f'Please respond within 24 hours via the app.'
                ),
                task_id=task.id,
            )
        # Notify admin(s)
        from users.models import CustomUser
        for admin in CustomUser.objects.filter(role='ADMIN', is_active=True):
            Notification.send(
                recipient=admin,
                notification_type='dispute_raised',
                title=f'New dispute on task #{task.id}',
                message=f'Task "{task.title}": {reason} — {description[:100]}',
                task_id=task.id,
            )

        return Response({
            'message': 'Dispute raised. Payment is frozen. Admin will review.',
            'dispute_id': dispute.id,
            'status': task.status,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='dispute-response')
    def dispute_response(self, request, pk=None):
        """
        Student submits their response to an open dispute.
        Body: { response }
        """
        task = self.get_object()
        user = request.user

        if task.assigned_student != user:
            return Response({'error': 'Only the assigned student can respond to this dispute.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status != 'Disputed':
            return Response(
                {'error': f'Task is not in Disputed state (current: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            dispute = task.dispute
        except Dispute.DoesNotExist:
            return Response({'error': 'No dispute found for this task.'}, status=status.HTTP_404_NOT_FOUND)

        if dispute.student_responded_at:
            return Response({'error': 'You have already responded to this dispute.'}, status=status.HTTP_400_BAD_REQUEST)

        response_text = request.data.get('response', '').strip()
        if not response_text:
            return Response({'error': 'response text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        dispute.student_response = response_text
        dispute.student_responded_at = django_tz.now()
        dispute.save(update_fields=['student_response', 'student_responded_at'])

        AuditLog.log(
            task=task, actor=user, action='dispute_event',
            notes=f'Student response submitted to dispute #{dispute.id}.',
        )

        from users.notifications import Notification
        from users.models import CustomUser
        for admin in CustomUser.objects.filter(role='ADMIN', is_active=True):
            Notification.send(
                recipient=admin,
                notification_type='dispute_response',
                title=f'Student responded to dispute on task #{task.id}',
                message=f'"{task.title}": student has submitted their response.',
                task_id=task.id,
            )

        return Response({'message': 'Response submitted. Admin will review shortly.'})

    @action(detail=True, methods=['post'], url_path='dispute-resolve')
    def dispute_resolve(self, request, pk=None):
        """
        Admin resolves a dispute.
        Body: { outcome, partial_refund_amount (opt), admin_notes (opt) }
        outcome: full_refund | partial_refund | release
        """
        task = self.get_object()
        user = request.user

        if not user.is_system_admin():
            return Response({'error': 'Only admins can resolve disputes.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status != 'Disputed':
            return Response(
                {'error': f'Task is not in Disputed state (current: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            dispute = task.dispute
        except Dispute.DoesNotExist:
            return Response({'error': 'No dispute found for this task.'}, status=status.HTTP_404_NOT_FOUND)

        outcome = request.data.get('outcome', '')
        valid_outcomes = [o[0] for o in Dispute.OUTCOME_CHOICES]
        if outcome not in valid_outcomes:
            return Response(
                {'error': f'Invalid outcome. Must be one of: {", ".join(valid_outcomes)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        partial_amount = None
        if outcome == 'partial_refund':
            partial_amount = request.data.get('partial_refund_amount')
            if not partial_amount:
                return Response({'error': 'partial_refund_amount is required for partial_refund outcome.'}, status=status.HTTP_400_BAD_REQUEST)
            partial_amount = Decimal(str(partial_amount))

        admin_notes = request.data.get('admin_notes', '')
        idem_key = uuid_lib.uuid4()

        with db_transaction.atomic():
            # Apply payment outcome
            if outcome == 'full_refund':
                ok, msg, _ = refund_service.refund_to_household(
                    task, actor=user, idempotency_key=idem_key,
                    notes=f'Dispute #{dispute.id} resolved: full refund. {admin_notes}',
                )
                if not ok:
                    return Response({'error': msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                new_task_status = 'Cancelled'

            elif outcome == 'partial_refund':
                ok, msg, _ = refund_service.refund_to_household(
                    task, actor=user, idempotency_key=idem_key,
                    partial_amount=partial_amount,
                    notes=f'Dispute #{dispute.id} resolved: partial refund KES {partial_amount}. {admin_notes}',
                )
                if not ok:
                    return Response({'error': msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                # Release remainder to student
                remainder = (task.escrow_transaction.amount
                             if hasattr(task, 'escrow_transaction') else Decimal('0')) - partial_amount
                if remainder > 0:
                    refund_service.release_to_student(
                        task, actor=user, idempotency_key=uuid_lib.uuid4()
                    )
                new_task_status = 'Completed'

            else:  # release
                ok, msg, _ = refund_service.release_to_student(
                    task, actor=user, idempotency_key=idem_key
                )
                if not ok:
                    return Response({'error': msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                new_task_status = 'Completed'

            # Update dispute record
            dispute.resolved_by = user
            dispute.outcome = outcome
            dispute.partial_refund_amount = partial_amount
            dispute.admin_notes = admin_notes
            dispute.resolved_at = django_tz.now()
            dispute.save()

            try:
                transition(task, new_task_status, actor=user,
                           notes=f'Dispute resolved: {outcome}. {admin_notes}')
            except InvalidTransition as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            AuditLog.log(
                task=task, actor=user, action='admin_decision',
                notes=f'Dispute #{dispute.id} resolved with outcome: {outcome}. {admin_notes}',
            )

        from users.notifications import Notification
        # Notify both parties
        for recipient in [task.household_owner, task.assigned_student]:
            if recipient:
                Notification.send(
                    recipient=recipient,
                    notification_type='dispute_resolved',
                    title='Dispute resolved',
                    message=(
                        f'The dispute on "{task.title}" has been resolved by an admin. '
                        f'Outcome: {outcome.replace("_", " ")}.'
                        + (f' Admin notes: {admin_notes}' if admin_notes else '')
                    ),
                    task_id=task.id,
                )

        return Response({
            'message': f'Dispute resolved: {outcome}.',
            'task_status': task.status,
            'dispute': DisputeSerializer(dispute).data,
        })

    # ----------------------------------------------------------------
    # Cancellation with refund policy
    # ----------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_task(self, request, pk=None):
        """
        Household cancels a task at any stage.

        Free (no payment yet): Posted / Broadcasting / Bidding / Reopened / Matched / PaymentPending
        Refund policy applies: Assigned (escrow Held):
          - >free_before_hours before scheduled_time → full refund
          - ≤free_before_hours → partial refund (default 80%)
        Blocked: InProgress / AwaitingConfirmation / Completed / Disputed
        """
        task = self.get_object()
        user = request.user

        if task.household_owner != user:
            return Response({'error': 'Only the task owner can cancel a task.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status in DELETION_BLOCKED_STATUSES:
            reason_map = {
                'InProgress': 'The student is currently working. Raise a dispute if there is a problem.',
                'AwaitingConfirmation': 'Work is finished. Confirm or raise a dispute instead.',
                'Completed': 'Task is already completed.',
                'Disputed': 'A dispute is in progress. Wait for admin resolution.',
            }
            return Response(
                {'error': reason_map.get(task.status, f'Cannot cancel in status: {task.status}.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        policy = CancellationPolicy.get()
        escrow = getattr(task, 'escrow_transaction', None)
        idem_key = uuid_lib.uuid4()

        with db_transaction.atomic():
            if task.status in FREE_CANCEL_STATUSES or not (escrow and escrow.status == 'Held'):
                # Free cancellation — no payment to refund
                try:
                    transition(task, 'Cancelled', actor=user, notes='Household cancelled (no payment).')
                except InvalidTransition as e:
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

                _notify_students_on_cancel(task, user)

                TransactionLedger.record(
                    task=task, transaction_type='HOLD',
                    amount=task.posted_price, actor=user,
                    notes='Cancelled before payment.', status='COMPLETED',
                )

                return Response({
                    'message': 'Task cancelled. No charges applied.',
                    'refund_amount': 0,
                    'status': task.status,
                })

            # Task has held escrow — apply policy
            from datetime import datetime, timezone as dt_tz
            hours_until_start = None
            if task.scheduled_date and task.scheduled_time:
                scheduled_dt = datetime.combine(task.scheduled_date, task.scheduled_time).replace(tzinfo=dt_tz.utc)
                delta = scheduled_dt - django_tz.now()
                hours_until_start = delta.total_seconds() / 3600

            if hours_until_start is None or hours_until_start > policy.free_before_hours:
                # Full refund
                ok, msg, _ = refund_service.refund_to_household(
                    task, actor=user, idempotency_key=idem_key,
                    notes='Household cancelled >free_before_hours before start.'
                )
                refund_amount = task.posted_price
                refund_msg = 'Full refund issued.'
            else:
                # Partial refund
                refund_pct = Decimal(str(policy.partial_refund_pct)) / 100
                partial = (escrow.amount * refund_pct).quantize(Decimal('0.01'))
                ok, msg, _ = refund_service.refund_to_household(
                    task, actor=user, idempotency_key=idem_key,
                    partial_amount=partial,
                    notes=f'Household cancelled within {policy.free_before_hours}h: {policy.partial_refund_pct}% refund.'
                )
                refund_amount = partial
                refund_msg = f'Partial refund of KES {partial} ({policy.partial_refund_pct}%) issued.'

            if not ok:
                return Response({'error': msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                transition(task, 'Cancelled', actor=user, notes=f'Household cancelled. {refund_msg}')
            except InvalidTransition as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            _notify_students_on_cancel(task, user)

        from users.notifications import Notification
        if task.assigned_student:
            Notification.send(
                recipient=task.assigned_student,
                notification_type='cancellation',
                title='Task cancelled by household',
                message=(
                    f'The household cancelled "{task.title}". '
                    f'The escrow has been returned to them.'
                ),
                task_id=task.id,
            )

        return Response({
            'message': f'Task cancelled. {refund_msg}',
            'refund_amount': str(refund_amount),
            'status': task.status,
        })

    @action(detail=True, methods=['post'], url_path='student-cancel')
    def student_cancel(self, request, pk=None):
        """
        Student cancels an accepted task.
        Full refund to household + reliability penalty + re-broadcast.
        """
        task = self.get_object()
        user = request.user

        if task.assigned_student != user:
            return Response({'error': 'You are not the assigned student.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status not in ('Matched', 'Assigned', 'PaymentPending'):
            return Response(
                {'error': f'Cannot cancel at this stage ({task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        idem_key = uuid_lib.uuid4()
        with db_transaction.atomic():
            # Mark request as declined
            TaskRequest.objects.filter(task=task, student=user, status='ACCEPTED').update(status='DECLINED')

            # Reliability penalty
            if hasattr(user, 'student_profile'):
                user.student_profile.record_cancellation()

            # Refund escrow if held
            escrow = getattr(task, 'escrow_transaction', None)
            if escrow and escrow.status == 'Held':
                ok, msg, _ = refund_service.refund_to_household(
                    task, actor=user, idempotency_key=idem_key,
                    notes='Student cancelled after acceptance — full refund.'
                )
                if not ok:
                    return Response({'error': f'Refund failed: {msg}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                transition(task, 'Reopened', actor=user, notes='Student cancelled — task re-broadcast.')
            except InvalidTransition as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            task.assigned_student = None
            task.grace_window_deadline = None
            task.broadcast_round = 0
            task.save(update_fields=['assigned_student', 'grace_window_deadline', 'broadcast_round', 'updated_at'])

        from users.notifications import Notification
        Notification.send(
            recipient=task.household_owner,
            notification_type='cancellation',
            title='Student cancelled the task',
            message=(
                f'{user.first_name or user.username} cancelled "{task.title}". '
                f'We are finding a replacement student. Any escrow has been fully refunded.'
            ),
            task_id=task.id,
        )

        t = threading.Thread(target=matching.broadcast_task, args=[task])
        t.daemon = True
        t.start()

        return Response({'message': 'Cancelled. We are finding a replacement student.'})

    # ----------------------------------------------------------------
    # Broadcast-flow actions (unchanged from original)
    # ----------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='rebroadcast')
    def rebroadcast_task(self, request, pk=None):
        task = self.get_object()
        user = request.user
        if not user.is_household() or task.household_owner != user:
            return Response({'error': 'Only the task owner can re-broadcast.'}, status=status.HTTP_403_FORBIDDEN)
        if task.status not in ('Posted', 'Reopened', 'Broadcasting'):
            return Response(
                {'error': f'Cannot broadcast a task with status: {task.status}.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        t = threading.Thread(target=matching.rebroadcast_to_remaining, args=[task])
        t.daemon = True
        t.start()
        return Response({'message': 'Task has been re-broadcast to eligible students (excluding those who declined or ignored).'})

    @action(detail=True, methods=['post'], url_path='confirm-match')
    def confirm_match(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if not user.is_household() or task.household_owner != user:
            return Response({'error': 'Only the task owner can confirm.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status != 'Matched':
            return Response(
                {'error': f'No pending match to confirm (status: {task.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if task.grace_window_deadline and django_tz.now() > task.grace_window_deadline:
            return Response({'error': 'Grace window has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        phone_number = request.data.get('phone_number')
        if not phone_number:
            return Response({'error': 'phone_number is required for payment.'}, status=status.HTTP_400_BAD_REQUEST)

        escrow, _ = Transaction.objects.get_or_create(
            task=task,
            defaults={'amount': task.posted_price, 'status': 'PendingDeposit'}
        )
        escrow.amount = task.posted_price
        escrow.save()

        task.status = 'PaymentPending'
        task.save(update_fields=['status', 'updated_at'])

        mpesa_response = mpesa_service.stk_push(
            phone_number=phone_number,
            amount=float(escrow.amount),
            account_reference=f"Task{task.id}",
            transaction_desc=f"Escrow for {task.title[:20]}"
        )

        if mpesa_response.get('success'):
            escrow.phone_number = phone_number
            escrow.checkout_request_id = mpesa_response.get('CheckoutRequestID')
            escrow.status = 'Held'
            escrow.save()

            task.status = 'Assigned'
            task.save(update_fields=['status', 'updated_at'])

            # Generate start code when task is funded
            completion, _ = TaskCompletion.objects.get_or_create(task=task)

            # Record HOLD in ledger
            TransactionLedger.record(
                task=task,
                transaction_type='HOLD',
                amount=escrow.amount,
                actor=user,
                mpesa_reference=escrow.checkout_request_id,
                notes='Escrow held on task confirmation.',
                status='SIMULATED',
            )

            AuditLog.log(task=task, actor=user, action='payment_event',
                         notes=f'Escrow HOLD KES {escrow.amount}. Task Assigned.')

            from users.notifications import Notification
            if task.assigned_student:
                Notification.send(
                    recipient=task.assigned_student,
                    notification_type='escrow_deposited',
                    title='Payment received — task confirmed!',
                    message=(
                        f'KES {escrow.amount} has been secured for "{task.title}". '
                        f'Full address: {task.location_address}. You can now start! '
                        f'Enter the start code from the household when you arrive.'
                    ),
                    task_id=task.id,
                )
                # Notify household of start code
                Notification.send(
                    recipient=user,
                    notification_type='start_code',
                    title=f'Start code for "{task.title}"',
                    message=(
                        f'Your start code is: {completion.start_code}. '
                        f'Share this with the student when they arrive so they can begin.'
                    ),
                    task_id=task.id,
                )

            return Response({
                'success': True,
                'message': 'Payment initiated. Task confirmed!',
                'checkout_request_id': escrow.checkout_request_id,
                'task_status': task.status,
                'start_code': completion.start_code,
            })
        else:
            task.status = 'Matched'
            task.save(update_fields=['status', 'updated_at'])
            return Response({
                'success': False,
                'error': mpesa_response.get('error', 'Payment failed.'),
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='cancel-match')
    def cancel_match(self, request, pk=None):
        task = self.get_object()
        user = request.user
        if not user.is_household() or task.household_owner != user:
            return Response({'error': 'Only the task owner can cancel a match.'}, status=status.HTTP_403_FORBIDDEN)
        block_student = request.data.get('block_student', False)
        success, message = matching.household_cancel_match(task, block_student=block_student)
        if success:
            return Response({'message': message, 'task_status': task.status})
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    # ----------------------------------------------------------------
    # Messages
    # ----------------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def task_messages(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if request.method == 'GET':
            messages = Message.objects.filter(task=task).order_by('timestamp')
            messages.filter(receiver=user).update(is_read=True)
            return Response(MessageSerializer(messages, many=True).data)

        content = request.data.get('content')
        if not content:
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if user == task.household_owner:
            receiver = task.assigned_student
        elif user == task.assigned_student:
            receiver = task.household_owner
        else:
            receiver = task.household_owner

        if not receiver:
            return Response({'error': 'No valid recipient found for this task chat.'}, status=status.HTTP_400_BAD_REQUEST)

        msg = Message.objects.create(task=task, sender=user, receiver=receiver, content=content)
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    # ----------------------------------------------------------------
    # Student task-request actions (unchanged)
    # ----------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='my-requests')
    def my_requests(self, request):
        user = request.user
        if not user.is_student():
            return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)

        qs = TaskRequest.objects.filter(
            student=user, status__in=['SENT', 'VIEWED'],
        ).select_related('task', 'task__household_owner').order_by('-sent_at')
        qs.filter(status='SENT').update(status='VIEWED')
        serializer = StudentInboxTaskRequestSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-requests/history')
    def my_requests_history(self, request):
        user = request.user
        if not user.is_student():
            return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)

        qs = TaskRequest.objects.filter(student=user).select_related(
            'task', 'task__household_owner'
        ).order_by('-sent_at')
        serializer = StudentInboxTaskRequestSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='accept-request')
    def accept_request(self, request):
        user = request.user
        if not user.is_student():
            return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)
        request_id = request.data.get('request_id')
        if not request_id:
            return Response({'error': 'request_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        success, message = matching.accept_task_request(request_id, user)
        if success:
            return Response({'message': message})
        return Response({'error': message}, status=status.HTTP_409_CONFLICT)

    @action(detail=False, methods=['post'], url_path='decline-request')
    def decline_request(self, request):
        user = request.user
        if not user.is_student():
            return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)
        request_id = request.data.get('request_id')
        if not request_id:
            return Response({'error': 'request_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            req = TaskRequest.objects.get(pk=request_id, student=user)
        except TaskRequest.DoesNotExist:
            return Response({'error': 'Request not found.'}, status=status.HTTP_404_NOT_FOUND)
        if req.status not in ('SENT', 'VIEWED'):
            return Response(
                {'error': f'Request is no longer open ({req.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )
        req.status = 'DECLINED'
        req.responded_at = django_tz.now()
        req.save(update_fields=['status', 'responded_at'])
        return Response({'message': 'Request declined.'})

    @action(detail=False, methods=['post'], url_path='ignore-request')
    def ignore_request(self, request):
        """Dismiss a broadcast request from the inbox without declining it.

        A softer signal than declining: the request closes for this student
        but the task simply proceeds with the other broadcast recipients.
        """
        user = request.user
        if not user.is_student():
            return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)
        request_id = request.data.get('request_id')
        if not request_id:
            return Response({'error': 'request_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            req = TaskRequest.objects.get(pk=request_id, student=user)
        except TaskRequest.DoesNotExist:
            return Response({'error': 'Request not found.'}, status=status.HTTP_404_NOT_FOUND)
        if req.status not in ('SENT', 'VIEWED'):
            return Response(
                {'error': f'Request is no longer open ({req.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )
        req.status = 'IGNORED'
        req.responded_at = django_tz.now()
        req.save(update_fields=['status', 'responded_at'])
        return Response({'message': 'Request ignored.'})


# ----------------------------------------------------------------
# Cancellation Policy CRUD (admin only)
# ----------------------------------------------------------------

class CancellationPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        policy = CancellationPolicy.get()
        return Response(CancellationPolicySerializer(policy).data)

    def patch(self, request):
        if not request.user.is_system_admin():
            return Response({'error': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        policy = CancellationPolicy.get()
        serializer = CancellationPolicySerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ----------------------------------------------------------------
# Dispute detail (admin view)
# ----------------------------------------------------------------

class DisputeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        """Admin or task parties can view the dispute details."""
        try:
            task = Task.objects.get(pk=task_id, is_deleted=False)
        except Task.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_party = user in (task.household_owner, task.assigned_student)
        if not (user.is_system_admin() or is_party):
            return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            dispute = task.dispute
        except Dispute.DoesNotExist:
            return Response({'error': 'No dispute on this task.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(DisputeSerializer(dispute).data)


# ----------------------------------------------------------------
# Admin: Audit Log
# ----------------------------------------------------------------

class AuditLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        if not request.user.is_system_admin():
            return Response({'error': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        from .serializers import AuditLogSerializer
        logs = task.audit_logs.all().order_by('created_at')
        return Response(AuditLogSerializer(logs, many=True).data)


# ----------------------------------------------------------------
# Ledger endpoint
# ----------------------------------------------------------------

class LedgerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        """Household or admin can view the ledger for a task."""
        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user != task.household_owner and not user.is_system_admin():
            return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)

        from .serializers import LedgerEntrySerializer
        entries = task.ledger_entries.all().order_by('created_at')
        return Response(LedgerEntrySerializer(entries, many=True).data)


# ----------------------------------------------------------------
# Location consent (student, before first check-in)
# ----------------------------------------------------------------

class GeoConsentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        consented = LocationConsent.objects.filter(student=request.user).exists()
        return Response({
            'required': True,
            'version': geo.LOCATION_CONSENT_VERSION,
            'text': geo.LOCATION_CONSENT_TEXT,
            'consented': consented,
        })

    def post(self, request):
        version = str(request.data.get('version', geo.LOCATION_CONSENT_VERSION))
        consent, created = LocationConsent.objects.get_or_create(
            student=request.user, defaults={'version': version}
        )
        if not created and consent.version != version:
            consent.version = version
            consent.consented_at = django_tz.now()
            consent.save(update_fields=['version', 'consented_at'])
        return Response({'consented': True, 'version': consent.version})


# ----------------------------------------------------------------
# Location policy (admin-configurable)
# ----------------------------------------------------------------

class LocationPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        policy = LocationPolicy.get()
        return Response(LocationPolicySerializer(policy).data)

    def patch(self, request):
        if not request.user.is_system_admin():
            return Response({'error': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        policy = LocationPolicy.get()
        serializer = LocationPolicySerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ----------------------------------------------------------------
# Nominatim (OpenStreetMap) proxy — free geocoding, no API key.
# The User-Agent is configurable via the NOMINATIM_USER_AGENT env var
# to comply with OSM's usage policy.
# ----------------------------------------------------------------

class GeoPlacesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import os
        import requests as http

        query = request.query_params.get('q', '').strip()
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')

        user_agent = os.getenv('NOMINATIM_USER_AGENT', 'domestic-jobs-platform-dev')
        headers = {'User-Agent': user_agent, 'Accept-Language': 'en'}
        base = 'https://nominatim.openstreetmap.org'
        try:
            if lat and lng:
                url = f'{base}/reverse'
                params = {'lat': lat, 'lon': lng, 'format': 'json', 'zoom': 18}
            elif query:
                url = f'{base}/search'
                params = {'q': query, 'format': 'json', 'limit': 6, 'countrycodes': 'ke'}
            else:
                return Response({'error': 'Provide ?q= or ?lat=&lng='}, status=status.HTTP_400_BAD_REQUEST)
            resp = http.get(url, params=params, headers=headers, timeout=5)
            data = resp.json()
        except Exception:
            return Response({'results': [], 'error': 'Address search is unavailable right now.'})

        if isinstance(data, dict):  # reverse geocode returns a single object
            data = [data]
        results = [
            {
                'label': item.get('display_name', ''),
                'lat': float(item.get('lat', 0)),
                'lng': float(item.get('lon', 0)),
            }
            for item in data if item.get('lat') and item.get('lon')
        ]
        return Response({'results': results})


# ----------------------------------------------------------------
# Private helpers
# ----------------------------------------------------------------

def _parse_coord(value):
    """Parse a coordinate from JSON (number or string) to Decimal, or None."""
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _validate_photo(photo):
    """Raise ValueError if photo exceeds size or type limits."""
    from tasks.models import PHOTO_MAX_SIZE_MB, ALLOWED_PHOTO_CONTENT_TYPES
    max_bytes = PHOTO_MAX_SIZE_MB * 1024 * 1024
    if photo.size > max_bytes:
        raise ValueError(f'Photo must be under {PHOTO_MAX_SIZE_MB} MB.')
    content_type = getattr(photo, 'content_type', '')
    if content_type and content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
        raise ValueError(f'Photo must be JPEG, PNG or WebP.')


def _notify_students_on_cancel(task, actor):
    """Withdraw pending task requests and notify affected students."""
    from users.notifications import Notification
    pending = TaskRequest.objects.filter(
        task=task, status__in=['SENT', 'VIEWED', 'ACCEPTED']
    ).select_related('student')
    for req in pending:
        Notification.send(
            recipient=req.student,
            notification_type='cancellation',
            title='Task cancelled',
            message=f'The task "{task.title}" has been cancelled by the household.',
            task_id=task.id,
        )
    pending.update(status='EXPIRED')
