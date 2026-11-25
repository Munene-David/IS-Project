from django.urls import path
from .views import (
    RegisterStudentView, RegisterHouseholdView, LoginView, MeView,
    NotificationsView, HouseholdSettingsView, BlockStudentView,
)

urlpatterns = [
    path('auth/register/student/', RegisterStudentView.as_view(), name='register-student'),
    path('auth/register/household/', RegisterHouseholdView.as_view(), name='register-household'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('household/settings/', HouseholdSettingsView.as_view(), name='household-settings'),
    path('household/block/', BlockStudentView.as_view(), name='block-student'),
]
