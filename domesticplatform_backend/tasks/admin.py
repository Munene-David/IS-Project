from django.contrib import admin
from .models import (
    PriceGuide, Task, Message, TaskRequest,
    CheckIn, LocationConsent, LocationPolicy,
)


@admin.register(PriceGuide)
class PriceGuideAdmin(admin.ModelAdmin):
    list_display = ['category', 'recommended_price', 'min_price', 'max_price']
    search_fields = ['category']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'household_owner', 'posted_price', 'status', 'created_at']
    list_filter = ['status', 'category']
    search_fields = ['title', 'description', 'household_owner__username']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['task', 'sender', 'receiver', 'timestamp', 'is_read']
    list_filter = ['is_read']
    search_fields = ['task__title', 'sender__username', 'receiver__username', 'content']


@admin.register(TaskRequest)
class TaskRequestAdmin(admin.ModelAdmin):
    list_display = ['task', 'student', 'status', 'broadcast_round', 'sent_at', 'responded_at']
    list_filter = ['status', 'broadcast_round']
    search_fields = ['task__title', 'student__username']


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    """Append-only location check-in audit records (admin only)."""
    list_display = [
        'task', 'student', 'type', 'result', 'distance_m', 'accuracy_m',
        'server_time', 'mock_location_flag', 'late_sync_flag', 'anonymised_at',
    ]
    list_filter = ['result', 'type', 'mock_location_flag', 'late_sync_flag']
    search_fields = ['task__title', 'student__username']
    readonly_fields = [f.name for f in CheckIn._meta.fields]


@admin.register(LocationConsent)
class LocationConsentAdmin(admin.ModelAdmin):
    list_display = ['student', 'version', 'consented_at']
    search_fields = ['student__username']


@admin.register(LocationPolicy)
class LocationPolicyAdmin(admin.ModelAdmin):
    """Single-row location policy (retention, accuracy threshold, etc.)."""
    list_display = [
        'allow_flagged_when_denied', 'retention_days',
        'low_accuracy_threshold_m', 'max_time_skew_seconds', 'max_speed_mps',
    ]
