from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TaskViewSet, PriceGuideView,
    CancellationPolicyView, DisputeDetailView, AuditLogView, LedgerView,
    GeoConsentView, LocationPolicyView, GeoPlacesView,
)

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('price-guide/', PriceGuideView.as_view(), name='price-guide-list'),
    path('price-guide/<str:category>/', PriceGuideView.as_view(), name='price-guide-detail'),
    # Cancellation policy (GET for all, PATCH for admin)
    path('cancellation-policy/', CancellationPolicyView.as_view(), name='cancellation-policy'),
    # Location policy (GET for all, PATCH for admin)
    path('location-policy/', LocationPolicyView.as_view(), name='location-policy'),
    # Location consent (student must POST before first check-in)
    path('geo/consent/', GeoConsentView.as_view(), name='geo-consent'),
    # Address search / reverse geocode proxy (OpenStreetMap Nominatim)
    path('geo/places/', GeoPlacesView.as_view(), name='geo-places'),
    # Dispute detail per task
    path('tasks/<int:task_id>/dispute-detail/', DisputeDetailView.as_view(), name='dispute-detail'),
    # Audit log (admin only)
    path('tasks/<int:task_id>/audit-log/', AuditLogView.as_view(), name='audit-log'),
    # Transaction ledger (household + admin)
    path('tasks/<int:task_id>/ledger/', LedgerView.as_view(), name='ledger'),
    path('', include(router.urls)),
]
# Router auto-generates extra URL patterns from @action decorators:
#   POST /api/tasks/{id}/checkin/              (geolocation-verified check-in)
#   GET  /api/tasks/{id}/location-audit/        (admin dispute map view)
#   POST /api/tasks/{id}/student-complete/
#   POST /api/tasks/{id}/confirm-completion/
#   GET  /api/tasks/{id}/start-code/
#   POST /api/tasks/{id}/upload-before-photo/
#   POST /api/tasks/{id}/dispute/
#   POST /api/tasks/{id}/dispute-response/
#   POST /api/tasks/{id}/dispute-resolve/
#   POST /api/tasks/{id}/cancel/
#   POST /api/tasks/{id}/student-cancel/
#   POST /api/tasks/{id}/rebroadcast/
#   POST /api/tasks/{id}/confirm-match/
#   POST /api/tasks/{id}/cancel-match/
#   GET  /api/tasks/my-requests/
#   GET  /api/tasks/my-requests/history/
#   POST /api/tasks/accept-request/
#   POST /api/tasks/decline-request/
#   POST /api/tasks/ignore-request/
