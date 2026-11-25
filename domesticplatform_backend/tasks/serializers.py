from rest_framework import serializers
from .models import PriceGuide, Task, Bid, Message
from payments.models import Rating


class PriceGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceGuide
        fields = ['id', 'category', 'min_price', 'max_price', 'recommended_price', 'description']


class BidSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_verification = serializers.SerializerMethodField()
    student_rating = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            'id', 'task', 'student', 'student_username',
            'student_verification', 'student_rating',
            'amount', 'message', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'student', 'status', 'created_at']

    def get_student_verification(self, obj):
        if hasattr(obj.student, 'student_profile'):
            return obj.student.student_profile.verification_status
        return 'Pending'

    def get_student_rating(self, obj):
        return Rating.calculate_average(obj.student)


class TaskListSerializer(serializers.ModelSerializer):
    household_owner_name = serializers.CharField(source='household_owner.username', read_only=True)
    bids_count = serializers.IntegerField(source='bids.count', read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'category', 'recommended_price',
            'posted_price', 'location_address', 'location_lat', 'location_lng',
            'status', 'household_owner', 'household_owner_name',
            'assigned_student', 'bids_count', 'created_at'
        ]


class TaskDetailSerializer(serializers.ModelSerializer):
    household_owner_name = serializers.CharField(source='household_owner.username', read_only=True)
    assigned_student_name = serializers.CharField(source='assigned_student.username', read_only=True)
    bids = BidSerializer(many=True, read_only=True)
    escrow_status = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'category', 'recommended_price',
            'posted_price', 'location_address', 'location_lat', 'location_lng',
            'status', 'household_owner', 'household_owner_name',
            'assigned_student', 'assigned_student_name', 'bids',
            'escrow_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'household_owner', 'assigned_student', 'status', 'created_at', 'updated_at']

    def get_escrow_status(self, obj):
        if hasattr(obj, 'escrow_transaction'):
            return obj.escrow_transaction.status
        return None


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'category', 'recommended_price',
            'posted_price', 'location_address', 'location_lat', 'location_lng'
        ]
        read_only_fields = ['id']


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    receiver_username = serializers.CharField(source='receiver.username', read_only=True)

    class Meta:
        model = Message
        fields = [
            'id', 'task', 'sender', 'sender_username',
            'receiver', 'receiver_username', 'content', 'timestamp', 'is_read'
        ]
        read_only_fields = ['id', 'sender', 'receiver', 'timestamp']
