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
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Also update specific profile fields if passed
            if user.is_student() and hasattr(user, 'student_profile'):
                profile = user.student_profile
                for field in ['university_id', 'university_name', 'availability_status']:
                    if field in request.data:
                        setattr(profile, field, request.data[field])
                profile.save()
            elif user.is_household() and hasattr(user, 'household_profile'):
                profile = user.household_profile
                for field in ['address', 'location_lat', 'location_lng']:
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
        notifications = Notification.objects.filter(recipient=request.user)[:50]
        data = [
            {
                'id': n.id,
                'type': n.notification_type,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'task_id': n.task_id,
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
