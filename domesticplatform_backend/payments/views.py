import uuid
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action

from .models import Transaction, Rating
from tasks.models import Task
from .serializers import TransactionSerializer, RatingSerializer


class InitiateEscrowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        task_id = request.data.get('task_id')
        phone_number = request.data.get('phone_number')

        if not task_id or not phone_number:
            return Response(
                {'error': 'Both task_id and phone_number are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        if task.household_owner != request.user:
            return Response({'error': 'Only the household owner can deposit escrow funds.'}, status=status.HTTP_403_FORBIDDEN)

        # Get or create escrow transaction
        escrow, _ = Transaction.objects.get_or_create(
            task=task,
            defaults={'amount': task.posted_price, 'status': 'PendingDeposit'}
        )

        # Generate reference
        simulated_mpesa_ref = f"WS{uuid.uuid4().hex[:8].upper()}"
        checkout_request_id = f"ws_CO_{uuid.uuid4().hex[:12]}"

        # Mark deposit as Held in escrow
        escrow.phone_number = phone_number
        escrow.checkout_request_id = checkout_request_id
        escrow.mark_held(mpesa_ref=simulated_mpesa_ref)

        # Update task status to InProgress
        task.status = 'InProgress'
        task.save(update_fields=['status', 'updated_at'])

        return Response({
            'message': 'M-Pesa payment simulated and verified. Funds are now secured in escrow.',
            'transaction': TransactionSerializer(escrow).data,
            'task_status': task.status
        })


class ReleaseEscrowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        task_id = request.data.get('task_id')
        if not task_id:
            return Response({'error': 'task_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        if task.household_owner != request.user:
            return Response({'error': 'Only the household owner can release escrow funds.'}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(task, 'escrow_transaction'):
            return Response({'error': 'No escrow transaction found for this task.'}, status=status.HTTP_404_NOT_FOUND)

        escrow = task.escrow_transaction
        if escrow.status != 'Held':
            return Response({'error': f'Escrow is not in Held state (current: {escrow.status}).'}, status=status.HTTP_400_BAD_REQUEST)

        escrow.release_funds()
        task.status = 'Completed'
        task.save(update_fields=['status', 'updated_at'])

        return Response({
            'message': 'Escrow funds successfully released to student via M-Pesa payout.',
            'transaction': TransactionSerializer(escrow).data,
            'task_status': task.status
        })


class MpesaCallbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # M-Pesa Daraja STK Push callback endpoint
        data = request.data
        result_code = data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
        checkout_id = data.get('Body', {}).get('stkCallback', {}).get('CheckoutRequestID')

        if checkout_id:
            transaction_obj = Transaction.objects.filter(checkout_request_id=checkout_id).first()
            if transaction_obj:
                if result_code == 0:
                    transaction_obj.status = 'Held'
                    transaction_obj.task.status = 'InProgress'
                    transaction_obj.task.save(update_fields=['status'])
                    transaction_obj.save()
                else:
                    transaction_obj.status = 'PendingDeposit'
                    transaction_obj.save()

        return Response({'ResultDesc': 'Accepted', 'ResultCode': 0})


class RatingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = RatingSerializer

    def get_queryset(self):
        qs = Rating.objects.all()
        user_id = self.request.query_params.get('user_id')
        task_id = self.request.query_params.get('task_id')
        if user_id:
            qs = qs.filter(rated_user_id=user_id)
        if task_id:
            qs = qs.filter(task_id=task_id)
        return qs

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')
        user = self.request.user

        # Auto-determine rated_user if not specified
        rated_user = serializer.validated_data.get('rated_user')
        if not rated_user:
            if user == task.household_owner:
                rated_user = task.assigned_student
            else:
                rated_user = task.household_owner

        serializer.save(rater=user, rated_user=rated_user)

    @action(detail=False, methods=['get'], url_path='summary/(?P<user_id>[^/.]+)')
    def user_summary(self, request, user_id=None):
        from users.models import CustomUser
        try:
            target_user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        avg_score = Rating.calculate_average(target_user)
        total_reviews = Rating.objects.filter(rated_user=target_user).count()
        recent_ratings = RatingSerializer(Rating.objects.filter(rated_user=target_user)[:5], many=True).data

        return Response({
            'user_id': target_user.id,
            'username': target_user.username,
            'average_rating': avg_score,
            'total_reviews': total_reviews,
            'recent_ratings': recent_ratings
        })
