from django.contrib import admin
from .models import Transaction, Rating


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'task', 'amount', 'status', 'mpesa_reference', 'created_at']
    list_filter = ['status']
    search_fields = ['task__title', 'mpesa_reference', 'phone_number']


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ['task', 'rater', 'rated_user', 'score', 'created_at']
    list_filter = ['score']
    search_fields = ['task__title', 'rater__username', 'rated_user__username', 'comment']
