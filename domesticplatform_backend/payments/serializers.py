from rest_framework import serializers
from .models import Transaction, TransactionLedger, Rating


class TransactionSerializer(serializers.ModelSerializer):
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'task', 'task_title', 'amount', 'status',
            'mpesa_reference', 'checkout_request_id', 'phone_number',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']


class TransactionLedgerSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, default=None)

    class Meta:
        model = TransactionLedger
        fields = [
            'id', 'task', 'amount', 'transaction_type', 'status',
            'mpesa_reference', 'idempotency_key',
            'actor', 'actor_username', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'task', 'created_at', 'idempotency_key']


class RatingSerializer(serializers.ModelSerializer):
    rater_username = serializers.CharField(source='rater.username', read_only=True)
    rated_user_username = serializers.CharField(source='rated_user.username', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = Rating
        fields = [
            'id', 'task', 'task_title', 'rater', 'rater_username',
            'rated_user', 'rated_user_username', 'score', 'comment', 'created_at'
        ]
        read_only_fields = ['id', 'rater', 'created_at']
