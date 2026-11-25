from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet, PriceGuideView

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('price-guide/', PriceGuideView.as_view(), name='price-guide-list'),
    path('price-guide/<str:category>/', PriceGuideView.as_view(), name='price-guide-detail'),
    path('', include(router.urls)),
]
