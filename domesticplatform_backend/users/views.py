from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate

from .models import CustomUser
from .serializers import (
    UserSerializer,
    StudentRegisterSerializer,
    HouseholdRegisterSerializer,
)


class RegisterStudentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = StudentRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data,
                'message': 'Student registered successfully',
                'next': '/api/auth/me/'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegisterHouseholdView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = HouseholdRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data,
                'message': 'Household owner registered successfully',
                'next': '/api/auth/me/'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = request.data.get('email') or request.data.get('username')
        password = request.data.get('password')

        if not identifier or not password:
            return Response(
                {'error': 'Please provide both username/email and password.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Allow logging in with either email or username
        user = authenticate(username=identifier, password=password)
        if not user and '@' in identifier:
            try:
                user_obj = CustomUser.objects.get(email=identifier)
                user = authenticate(username=user_obj.username, password=password)
            except CustomUser.DoesNotExist:
                user = None

        if user:
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data,
                'next': '/'  # redirect to site landing page
            })
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        user = request.user
        # Strip fields that must never be changed via self-service PATCH
        mutable = {k: v for k, v in request.data.items()
                   if k not in ('role', 'is_staff', 'is_superuser', 'is_active')}
        serializer = UserSerializer(user, data=mutable, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Also update specific profile fields if passed
            if user.is_student() and hasattr(user, 'student_profile'):
                profile = user.student_profile
                for field in [
                    'university_id', 'university_name', 'availability_status',
                    'categories_offered', 'location_lat', 'location_lng',
                ]:
                    if field in request.data:
                        setattr(profile, field, request.data[field])
                profile.save()
            elif user.is_household() and hasattr(user, 'household_profile'):
                profile = user.household_profile
                for field in [
                    'address', 'location_lat', 'location_lng',
                    'min_rating', 'search_radius_km',
                ]:
                    if field in request.data:
                        setattr(profile, field, request.data[field])
                profile.save()
            return Response(UserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationsView(APIView):
    """Get all notifications for the logged-in user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .notifications import Notification
        from tasks.models import TaskRequest

        notifications = Notification.objects.filter(recipient=request.user)[:50]

        # Live status of the TaskRequest behind each task_request notification
        # (so the client only offers accept/ignore/decline while still open).
        request_ids = [n.request_id for n in notifications if n.request_id]
        request_statuses = {}
        if request_ids:
            request_statuses = {
                tr.id: tr.status
                for tr in TaskRequest.objects.filter(id__in=request_ids, student=request.user)
            }

        data = [
            {
                'id': n.id,
                'type': n.notification_type,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'task_id': n.task_id,
                'request_id': n.request_id,
                'request_status': request_statuses.get(n.request_id) if n.request_id else None,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifications
        ]
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'notifications': data, 'unread_count': unread_count})

    def patch(self, request):
        """Mark all notifications as read."""
        from .notifications import Notification
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})


class HouseholdSettingsView(APIView):
    """
    GET  /api/household/settings/ — return min_rating, search_radius_km, block list
    PATCH                         — update min_rating and/or search_radius_km
    """
    permission_classes = [IsAuthenticated]

    def _require_household(self, user):
        if not user.is_household():
            return Response({'error': 'Household accounts only.'}, status=status.HTTP_403_FORBIDDEN)

    def get(self, request):
        err = self._require_household(request.user)
        if err:
            return err
        profile = request.user.household_profile
        from .models import BlockedStudent
        blocked = BlockedStudent.objects.filter(household=request.user).select_related('student')
        return Response({
            'min_rating': float(profile.min_rating),
            'search_radius_km': float(profile.search_radius_km),
            'blocked_students': [
                {'id': b.student.id, 'username': b.student.username,
                 'first_name': b.student.first_name, 'last_name': b.student.last_name}
                for b in blocked
            ],
        })

    def patch(self, request):
        err = self._require_household(request.user)
        if err:
            return err
        profile = request.user.household_profile
        for field in ('min_rating', 'search_radius_km'):
            if field in request.data:
                try:
                    setattr(profile, field, float(request.data[field]))
                except (TypeError, ValueError):
                    return Response({'error': f'Invalid value for {field}.'}, status=status.HTTP_400_BAD_REQUEST)
        profile.save()
        return Response({'message': 'Settings updated.', 'min_rating': float(profile.min_rating),
                         'search_radius_km': float(profile.search_radius_km)})


class BlockStudentView(APIView):
    """
    POST   /api/household/block/   {student_id}  — block a student
    DELETE /api/household/block/   {student_id}  — unblock a student
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_household():
            return Response({'error': 'Household accounts only.'}, status=status.HTTP_403_FORBIDDEN)
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'error': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            student = CustomUser.objects.get(id=student_id, role='STUDENT')
        except CustomUser.DoesNotExist:
            return Response({'error': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)
        from .models import BlockedStudent
        BlockedStudent.objects.get_or_create(household=request.user, student=student)
        return Response({'message': f'{student.username} has been blocked.'})

    def delete(self, request):
        if not request.user.is_household():
            return Response({'error': 'Household accounts only.'}, status=status.HTTP_403_FORBIDDEN)
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'error': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        from .models import BlockedStudent
        BlockedStudent.objects.filter(household=request.user, student_id=student_id).delete()
        return Response({'message': 'Student unblocked.'})
