from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from django.db.models import Q

from .models import PriceGuide, Task, Bid, Message
from payments.models import Transaction
from .serializers import (
    PriceGuideSerializer,
    TaskListSerializer,
    TaskDetailSerializer,
    TaskCreateSerializer,
    BidSerializer,
    MessageSerializer,
)


class PriceGuideView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, category=None):
        if category:
            guide = PriceGuide.objects.filter(category__iexact=category).first()
            if not guide:
                return Response({'error': f'No price guide found for category {category}'}, status=status.HTTP_404_NOT_FOUND)
            return Response(PriceGuideSerializer(guide).data)
        guides = PriceGuide.objects.all()
        return Response(PriceGuideSerializer(guides, many=True).data)


class TaskViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Task.objects.all().order_by('-created_at')
        category = self.request.query_params.get('category')
        task_status = self.request.query_params.get('status')
        search = self.request.query_params.get('search')
        my_tasks = self.request.query_params.get('my_tasks')

        if my_tasks:
            user = self.request.user
            qs = qs.filter(Q(household_owner=user) | Q(assigned_student=user))
        if category:
            qs = qs.filter(category__iexact=category)
        if task_status:
            qs = qs.filter(status=task_status)
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return TaskCreateSerializer
        if self.action == 'retrieve':
            return TaskDetailSerializer
        return TaskListSerializer

    def perform_create(self, serializer):
        user = self.request.user
        category = serializer.validated_data.get('category')
        rec_price = PriceGuide.get_recommended_price(category)
        serializer.save(
            household_owner=user,
            recommended_price=rec_price,
            status='Posted'
        )

    @action(detail=True, methods=['post'], url_path='bids')
    def submit_bid(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if not user.is_student():
            return Response({'error': 'Only students can submit bids.'}, status=status.HTTP_403_FORBIDDEN)

        if task.status not in ['Posted', 'Bidding']:
            return Response({'error': f'Bidding is closed for this task (status: {task.status}).'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if already bid
        existing_bid = Bid.objects.filter(task=task, student=user).first()
        if existing_bid:
            return Response({'error': 'You have already submitted a bid for this task.'}, status=status.HTTP_400_BAD_REQUEST)

        amount = request.data.get('amount')
        message = request.data.get('message', '')

        if not amount:
            return Response({'error': 'Please provide a bid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        bid = Bid.objects.create(
            task=task,
            student=user,
            amount=amount,
            message=message,
            status='Pending'
        )

        # Update task status to Bidding if it was Posted
        if task.status == 'Posted':
            task.status = 'Bidding'
            task.save(update_fields=['status'])

        return Response(BidSerializer(bid).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='accept-bid')
    def accept_bid(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if task.household_owner != user:
            return Response({'error': 'Only the task owner can accept bids.'}, status=status.HTTP_403_FORBIDDEN)

        bid_id = request.data.get('bid_id')
        if not bid_id:
            return Response({'error': 'bid_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            winning_bid = Bid.objects.get(id=bid_id, task=task)
        except Bid.DoesNotExist:
            return Response({'error': 'Bid not found for this task.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            winning_bid.status = 'Accepted'
            winning_bid.save()

            # Reject other bids
            task.bids.exclude(id=winning_bid.id).update(status='Rejected')

            # Assign student and update status to Assigned
            task.assigned_student = winning_bid.student
            task.status = 'Assigned'
            task.save()

            # Create or update Escrow Transaction
            escrow, _ = Transaction.objects.get_or_create(
                task=task,
                defaults={'amount': winning_bid.amount, 'status': 'PendingDeposit'}
            )
            escrow.amount = winning_bid.amount
            escrow.save()

        return Response({
            'message': f'Bid from {winning_bid.student.username} accepted. Ready for escrow deposit.',
            'task': TaskDetailSerializer(task).data,
            'escrow_id': escrow.id,
            'amount_due': escrow.amount
        })

    @action(detail=True, methods=['post'], url_path='complete')
    def mark_complete(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if user != task.household_owner and user != task.assigned_student:
            return Response({'error': 'Unauthorized to modify task status.'}, status=status.HTTP_403_FORBIDDEN)

        if user == task.assigned_student:
            task.status = 'InProgress'
            task.save(update_fields=['status', 'updated_at'])
            return Response({'message': 'Task marked in progress / awaiting household confirmation.', 'status': task.status})

        if user == task.household_owner:
            task.status = 'Completed'
            task.save(update_fields=['status', 'updated_at'])
            # Automatically release escrow funds if held
            if hasattr(task, 'escrow_transaction') and task.escrow_transaction.status == 'Held':
                task.escrow_transaction.release_funds()
            return Response({'message': 'Task marked as completed and escrow funds released.', 'status': task.status})

        return Response({'status': task.status})

    @action(detail=True, methods=['post'], url_path='dispute')
    def raise_dispute(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if user != task.household_owner and user != task.assigned_student:
            return Response({'error': 'Unauthorized.'}, status=status.HTTP_403_FORBIDDEN)

        task.status = 'Disputed'
        task.save(update_fields=['status', 'updated_at'])
        return Response({'message': 'Dispute raised. Admin will intervene.', 'status': task.status})

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def task_messages(self, request, pk=None):
        task = self.get_object()
        user = request.user

        if request.method == 'GET':
            messages = Message.objects.filter(task=task).order_by('timestamp')
            # Mark messages to me as read
            messages.filter(receiver=user).update(is_read=True)
            return Response(MessageSerializer(messages, many=True).data)

        if request.method == 'POST':
            content = request.data.get('content')
            if not content:
                return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

            # Determine recipient
            if user == task.household_owner:
                receiver = task.assigned_student
            elif user == task.assigned_student:
                receiver = task.household_owner
            else:
                receiver = None

            if not receiver:
                # If student is not yet assigned, allow messaging the task owner
                if user != task.household_owner:
                    receiver = task.household_owner
                else:
                    receiver_id = request.data.get('receiver_id')
                    if receiver_id:
                        receiver = task.bids.filter(student_id=receiver_id).first().student if task.bids.filter(student_id=receiver_id).exists() else None

            if not receiver:
                return Response({'error': 'No valid recipient found for this task chat.'}, status=status.HTTP_400_BAD_REQUEST)

            msg = Message.objects.create(
                task=task,
                sender=user,
                receiver=receiver,
                content=content
            )
            return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)
