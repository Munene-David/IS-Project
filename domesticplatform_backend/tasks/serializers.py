from rest_framework import serializers
from .models import (
    PriceGuide, Task, Message, TaskRequest,
    TaskCompletion, Dispute, CancellationPolicy, AuditLog,
    CheckIn, LocationConsent, LocationPolicy,
)
from payments.models import Rating, TransactionLedger
from . import geo


class PriceGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceGuide
        fields = ['id', 'category', 'min_price', 'max_price', 'recommended_price', 'description']


class TaskRequestSerializer(serializers.ModelSerializer):
    """Full TaskRequest — used in household task detail."""
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_first_name = serializers.CharField(source='student.first_name', read_only=True)
    student_last_name = serializers.CharField(source='student.last_name', read_only=True)
    student_rating = serializers.SerializerMethodField()
    student_verification = serializers.SerializerMethodField()

    class Meta:
        model = TaskRequest
        fields = [
            'id', 'task', 'student', 'student_username',
            'student_first_name', 'student_last_name',
            'student_rating', 'student_verification',
            'status', 'sent_at', 'responded_at', 'broadcast_round', 'rank_score',
        ]
        read_only_fields = [
            'id', 'task', 'student', 'student_username',
            'student_first_name', 'student_last_name',
            'student_rating', 'student_verification',
            'status', 'sent_at', 'responded_at', 'broadcast_round', 'rank_score',
        ]

    def get_student_rating(self, obj):
        return Rating.calculate_average(obj.student)

    def get_student_verification(self, obj):
        if hasattr(obj.student, 'student_profile'):
            return obj.student.student_profile.verification_status
        return 'Pending'


class StudentInboxTaskRequestSerializer(serializers.ModelSerializer):
    """Minimal TaskRequest for the student's Available Requests inbox."""
    task_id = serializers.IntegerField(source='task.id', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)
    task_category = serializers.CharField(source='task.category', read_only=True)
    task_posted_price = serializers.DecimalField(
        source='task.posted_price', max_digits=10, decimal_places=2, read_only=True
    )
    task_scheduled_date = serializers.DateField(source='task.scheduled_date', read_only=True)
    task_scheduled_time = serializers.TimeField(source='task.scheduled_time', read_only=True)
    task_location_approximate = serializers.SerializerMethodField()

    class Meta:
        model = TaskRequest
        fields = [
            'id', 'task_id', 'task_title', 'task_category',
            'task_posted_price', 'task_scheduled_date', 'task_scheduled_time',
            'task_location_approximate', 'status', 'sent_at',
        ]
        read_only_fields = [
            'id', 'task_id', 'task_title', 'task_category',
            'task_posted_price', 'task_scheduled_date', 'task_scheduled_time',
            'task_location_approximate', 'status', 'sent_at',
        ]

    def get_task_location_approximate(self, obj):
        addr = obj.task.location_address or ''
        parts = [p.strip() for p in addr.split(',')]
        return ', '.join(parts[1:]) if len(parts) > 1 else addr


# ---------------------------------------------------------------------------
# Location visibility helpers (shared by list/detail serializers)
# ---------------------------------------------------------------------------

def _location_access(request, obj):
    """
    Returns (exact_allowed, privileged) for the requesting user on `obj`.

    exact_allowed — the user may see the true pin coordinates
    privileged    — owner, admin, or assigned student with payment held/released
                    (may also see the landmark text)
    """
    if not request or not request.user.is_authenticated:
        return False, False
    user = request.user
    if user.is_system_admin():
        return True, True
    if user == obj.household_owner:
        return True, True
    if user == obj.assigned_student:
        paid = (
            hasattr(obj, 'escrow_transaction')
            and obj.escrow_transaction.status in ('Held', 'Released')
        )
        return paid, paid
    return False, False


def location_visible_exact(request, obj):
    exact_allowed, _ = _location_access(request, obj)
    return exact_allowed


def location_lat_for(request, obj):
    if obj.location_lat is None:
        return None
    exact_allowed, _ = _location_access(request, obj)
    if exact_allowed:
        return str(obj.location_lat)
    approx_lat, _ = geo.approximate_coords(obj.location_lat, obj.location_lng, f'task-{obj.id}')
    return str(approx_lat)


def location_lng_for(request, obj):
    if obj.location_lng is None:
        return None
    exact_allowed, _ = _location_access(request, obj)
    if exact_allowed:
        return str(obj.location_lng)
    _, approx_lng = geo.approximate_coords(obj.location_lat, obj.location_lng, f'task-{obj.id}')
    return str(approx_lng)


def location_address_for(request, obj):
    """
    Full address text only for privileged viewers (owner / paid student /
    admin).  Everyone else gets the coarse area label — the address typed or
    geocoded for the pin can name the exact building, which must stay hidden
    until the student is assigned and has paid.
    """
    _, privileged = _location_access(request, obj)
    if privileged:
        return obj.location_address
    return geo.approximate_area_label(obj.location_address)


class TaskListSerializer(serializers.ModelSerializer):
    household_owner_name = serializers.CharField(source='household_owner.username', read_only=True)
    requests_count = serializers.SerializerMethodField()
    # Coordinates and address text are privacy-controlled: exact/full only for
    # the household owner, the assigned student (once paid) and admins.
    # Everyone else — including browsing students — sees an approximate area.
    location_address = serializers.SerializerMethodField()
    location_lat = serializers.SerializerMethodField()
    location_lng = serializers.SerializerMethodField()
    location_exact = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'category', 'recommended_price',
            'posted_price', 'location_address', 'location_lat', 'location_lng',
            'location_exact',
            'status', 'household_owner', 'household_owner_name',
            'assigned_student', 'requests_count',
            'scheduled_date', 'scheduled_time',
            'broadcast_round', 'created_at',
            'is_deleted',
        ]

    def get_requests_count(self, obj):
        return obj.requests.count()

    def get_location_exact(self, obj):
        return location_visible_exact(self.context.get('request'), obj)

    def get_location_address(self, obj):
        return location_address_for(self.context.get('request'), obj)

    def get_location_lat(self, obj):
        return location_lat_for(self.context.get('request'), obj)

    def get_location_lng(self, obj):
        return location_lng_for(self.context.get('request'), obj)


class TaskDetailSerializer(serializers.ModelSerializer):
    household_owner_name = serializers.CharField(source='household_owner.username', read_only=True)
    assigned_student_name = serializers.CharField(source='assigned_student.username', read_only=True)
    assigned_student_first_name = serializers.CharField(
        source='assigned_student.first_name', read_only=True, default=None
    )
    task_requests = TaskRequestSerializer(source='requests', many=True, read_only=True)
    my_request = serializers.SerializerMethodField()
    escrow_status = serializers.SerializerMethodField()
    grace_window_deadline = serializers.DateTimeField(read_only=True)
    location_address = serializers.SerializerMethodField()
    location_address_full = serializers.SerializerMethodField()
    # Privacy-controlled coordinates (exact only for owner/paid student/admin)
    location_lat = serializers.SerializerMethodField()
    location_lng = serializers.SerializerMethodField()
    location_exact = serializers.SerializerMethodField()
    location_area = serializers.SerializerMethodField()
    location_landmark = serializers.SerializerMethodField()
    geofence_radius_m = serializers.IntegerField(read_only=True)
    # Check-in summary for the parties — no raw coordinates (privacy)
    checkin_summary = serializers.SerializerMethodField()
    # Completion info (start code hidden; timestamps/photos visible to both parties)
    has_completion = serializers.SerializerMethodField()
    completion_timestamps = serializers.SerializerMethodField()
    has_dispute = serializers.SerializerMethodField()
    confirmation_deadline = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'category', 'recommended_price',
            'posted_price', 'location_address', 'location_address_full',
            'location_lat', 'location_lng', 'location_exact', 'location_area',
            'location_landmark', 'geofence_radius_m',
            'status', 'household_owner', 'household_owner_name',
            'assigned_student', 'assigned_student_name', 'assigned_student_first_name',
            'task_requests', 'my_request',
            'escrow_status', 'created_at', 'updated_at',
            'scheduled_date', 'scheduled_time',
            'broadcast_round', 'search_radius_km', 'grace_window_deadline',
            'confirmation_deadline',
            'has_completion', 'completion_timestamps', 'checkin_summary',
            'has_dispute', 'is_deleted',
        ]
        read_only_fields = ['id', 'household_owner', 'assigned_student', 'status', 'created_at', 'updated_at']

    def get_escrow_status(self, obj):
        if hasattr(obj, 'escrow_transaction'):
            return obj.escrow_transaction.status
        return None

    def get_my_request(self, obj):
        """The requesting student's own TaskRequest for this task (if any).

        Lets the student act on a broadcast (accept / ignore / decline)
        straight from the task detail screen.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        if not request.user.is_student():
            return None
        req = obj.requests.filter(student=request.user).first()
        if not req:
            return None
        return {
            'id': req.id,
            'status': req.status,
            'sent_at': req.sent_at,
        }

    def get_location_address_full(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        _, privileged = _location_access(request, obj)
        if privileged:
            return obj.location_address
        return None

    def get_location_address(self, obj):
        return location_address_for(self.context.get('request'), obj)

    def get_location_lat(self, obj):
        return location_lat_for(self.context.get('request'), obj)

    def get_location_lng(self, obj):
        return location_lng_for(self.context.get('request'), obj)

    def get_location_exact(self, obj):
        return location_visible_exact(self.context.get('request'), obj)

    def get_location_area(self, obj):
        """Coarse area label (e.g. 'Kilimani, Nairobi') for non-privileged viewers."""
        request = self.context.get('request')
        _, privileged = _location_access(request, obj)
        if privileged:
            return None
        return geo.approximate_area_label(obj.location_address)

    def get_location_landmark(self, obj):
        request = self.context.get('request')
        _, privileged = _location_access(request, obj)
        if privileged:
            return obj.location_landmark
        return None

    def get_checkin_summary(self, obj):
        """
        Coordinate-free summary of the accepted check-in for the task parties:
        households see 'Arrived at HH:MM, location verified' style info.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        is_party = user in (obj.household_owner, obj.assigned_student)
        if not (is_party or user.is_system_admin()):
            return None
        accepted = obj.checkins.filter(type='START').order_by('-server_time').first()
        if accepted is None:
            return None
        # Retries recorded after the accepted check-in (type ARRIVAL)
        retries = list(
            obj.checkins.filter(type='ARRIVAL', server_time__gte=accepted.server_time)
            .order_by('server_time')
        )
        attempts = [accepted] + retries
        verified = any(a.result == 'VERIFIED' for a in attempts)
        flagged = (
            not verified
            or accepted.mock_location_flag
            or accepted.late_sync_flag
            or accepted.impossible_jump_flag
        )
        latest = attempts[-1]
        return {
            'arrived_at': accepted.server_time,
            'result': 'VERIFIED' if verified else latest.result,
            'location_verified': verified and not flagged,
            'flagged': flagged,
            'flags': {
                'mock_location': accepted.mock_location_flag,
                'late_sync': accepted.late_sync_flag,
                'impossible_jump': accepted.impossible_jump_flag,
            },
        }

    def get_has_completion(self, obj):
        return hasattr(obj, 'completion')

    def get_completion_timestamps(self, obj):
        try:
            c = obj.completion
            return {
                'arrived_at': c.arrived_at,
                'started_at': c.started_at,
                'finished_at': c.finished_at,
                # NOTE: check-in coordinates are deliberately NOT exposed here.
                # Raw coordinates are admin-only (see the location-audit endpoint).
                'has_before_photo': bool(c.before_photo),
                'has_after_photo': bool(c.after_photo),
            }
        except Exception:
            return None

    def get_has_dispute(self, obj):
        return hasattr(obj, 'dispute')


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'category', 'recommended_price',
            'posted_price', 'location_address', 'location_lat', 'location_lng',
            'location_landmark', 'geofence_radius_m', 'location_pin_confirmed',
            'scheduled_date', 'scheduled_time',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        """
        A confirmed map pin is preferred but not mandatory — tasks without
        coordinates are accepted and broadcast normally; check-in geofencing
        simply skips the distance check for those tasks (treats them as VERIFIED).
        """
        radius = attrs.get('geofence_radius_m', 150)
        if radius is not None and not (30 <= radius <= 1000):
            raise serializers.ValidationError(
                'geofence_radius_m must be between 30 and 1000 metres.'
            )
        return attrs


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    receiver_username = serializers.CharField(source='receiver.username', read_only=True)

    class Meta:
        model = Message
        fields = [
            'id', 'task', 'sender', 'sender_username',
            'receiver', 'receiver_username', 'content', 'timestamp', 'is_read'
        ]
        read_only_fields = ['id', 'sender', 'receiver', 'timestamp']


class TaskCompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCompletion
        fields = [
            'id', 'task', 'start_code_verified',
            'arrived_at', 'started_at', 'finished_at',
            'checkin_lat', 'checkin_lng',
            'before_photo', 'after_photo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'task', 'start_code_verified', 'created_at', 'updated_at']


class DisputeSerializer(serializers.ModelSerializer):
    raised_by_username = serializers.CharField(source='raised_by.username', read_only=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True, default=None)

    class Meta:
        model = Dispute
        fields = [
            'id', 'task', 'raised_by', 'raised_by_username',
            'reason', 'description',
            'student_response', 'student_responded_at',
            'resolved_by', 'resolved_by_username',
            'outcome', 'partial_refund_amount', 'admin_notes', 'resolved_at',
            'created_at',
        ]
        read_only_fields = [
            'id', 'task', 'raised_by', 'raised_by_username',
            'resolved_by', 'resolved_by_username',
            'student_responded_at', 'resolved_at', 'created_at',
        ]


class CancellationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CancellationPolicy
        fields = ['id', 'free_before_hours', 'partial_refund_pct', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'task', 'actor', 'actor_username',
            'action', 'from_status', 'to_status', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'task', 'actor', 'created_at']


class LedgerEntrySerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, default=None)

    class Meta:
        model = TransactionLedger
        fields = [
            'id', 'task', 'amount', 'transaction_type', 'status',
            'mpesa_reference', 'idempotency_key', 'actor', 'actor_username',
            'notes', 'created_at',
        ]
        read_only_fields = ['id', 'task', 'created_at', 'idempotency_key']


class CheckInSerializer(serializers.ModelSerializer):
    """Full check-in record — ADMIN ONLY (location-audit / dispute view)."""
    student_username = serializers.CharField(source='student.username', read_only=True)

    class Meta:
        model = CheckIn
        fields = [
            'id', 'task', 'student', 'student_username', 'type',
            'lat', 'lng', 'accuracy_m', 'distance_m',
            'device_time', 'server_time', 'time_skew_seconds',
            'result', 'mock_location_flag', 'late_sync_flag',
            'impossible_jump_flag', 'device_info', 'anonymised_at',
        ]
        read_only_fields = fields


class LocationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationPolicy
        fields = [
            'id', 'allow_flagged_when_denied', 'retention_days',
            'low_accuracy_threshold_m', 'max_time_skew_seconds', 'max_speed_mps',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
