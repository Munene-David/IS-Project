from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InitiateEscrowView, ReleaseEscrowView, MpesaCallbackView, RatingViewSet

router = DefaultRouter()
router.register(r'ratings', RatingViewSet, basename='rating')

urlpatterns = [
    path('payments/initiate-escrow/', InitiateEscrowView.as_view(), name='initiate-escrow'),
    path('payments/release-escrow/', ReleaseEscrowView.as_view(), name='release-escrow'),
    path('payments/mpesa-callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
    path('', include(router.urls)),
]
