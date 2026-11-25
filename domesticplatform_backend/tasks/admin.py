from django.contrib import admin
from .models import PriceGuide, Task, Bid, Message


@admin.register(PriceGuide)
class PriceGuideAdmin(admin.ModelAdmin):
    list_display = ['category', 'recommended_price', 'min_price', 'max_price']
    search_fields = ['category']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'household_owner', 'posted_price', 'status', 'created_at']
    list_filter = ['status', 'category']
    search_fields = ['title', 'description', 'household_owner__username']


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ['task', 'student', 'amount', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['task__title', 'student__username']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['task', 'sender', 'receiver', 'timestamp', 'is_read']
    list_filter = ['is_read']
    search_fields = ['task__title', 'sender__username', 'receiver__username', 'content']
