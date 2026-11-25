import uuid
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action

from .models import Transaction, Rating
from tasks.models import Task
from .serializers import TransactionSerializer, RatingSerializer
from .mpesa_service import mpesa_service
import logging

logger = logging.getLogger(__name__)


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
            return Response(
                {'error': 'Only the household owner can deposit escrow funds.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get or create escrow transaction
        escrow, _ = Transaction.objects.get_or_create(
            task=task,
            defaults={'amount': task.posted_price, 'status': 'PendingDeposit'}
        )

        # Initiate real M-Pesa STK Push
        logger.info(f"Initiating M-Pesa STK Push for Task {task.id}, Amount: {escrow.amount}")
        
        mpesa_response = mpesa_service.stk_push(
            phone_number=phone_number,
            amount=float(escrow.amount),
            account_reference=f"Task{task.id}",
            transaction_desc=f"Escrow for {task.title[:20]}"
        )

        if mpesa_response.get('success'):
            # Store checkout request ID for status tracking
            escrow.phone_number = phone_number
            escrow.checkout_request_id = mpesa_response.get('CheckoutRequestID')
            escrow.status = 'Held'
            escrow.save()
            # Update task status to InProgress in mock mode
            task.status = 'InProgress'
            task.save(update_fields=['status', 'updated_at'])

            logger.info(f"STK Push sent successfully: {escrow.checkout_request_id}")

            return Response({
                'success': True,
                'message': 'Payment request sent to your phone. Please enter your M-Pesa PIN.',
                'checkout_request_id': escrow.checkout_request_id,
                'customer_message': mpesa_response.get('CustomerMessage'),
                'transaction': TransactionSerializer(escrow).data,
                'task_status': task.status
            })
        else:
            logger.error(f"STK Push failed: {mpesa_response.get('error')}")
            return Response({
                'success': False,
                'error': mpesa_response.get('error', 'Failed to initiate payment'),
                'message': 'Payment initiation failed. Please try again.'
            }, status=status.HTTP_400_BAD_REQUEST)


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
            return Response(
                {'error': 'Only the household owner can release escrow funds.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not hasattr(task, 'escrow_transaction'):
            return Response(
                {'error': 'No escrow transaction found for this task.'},
                status=status.HTTP_404_NOT_FOUND
            )

        escrow = task.escrow_transaction
        
        if escrow.status != 'Held':
            return Response(
                {'error': f'Escrow is not in Held state (current: {escrow.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get student's phone number
        student = task.assigned_student
        if not student or not student.phone_number:
            return Response(
                {'error': 'Student phone number not available for payment.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Initiate B2C payment to student
        logger.info(f"Releasing escrow for Task {task.id} to student {student.username}")
        
        b2c_response = mpesa_service.b2c_payment(
            phone_number=student.phone_number,
            amount=float(escrow.amount),
            occasion=f"Payment for Task {task.id}"
        )

        if b2c_response.get('success'):
            # Mark escrow as released
            escrow.status = 'Released'
            escrow.save(update_fields=['status', 'updated_at'])
            
            # Update task status
            task.status = 'Completed'
            task.save(update_fields=['status', 'updated_at'])

            logger.info(f"B2C payment initiated successfully for Task {task.id}")

            return Response({
                'success': True,
                'message': 'Payment sent to student via M-Pesa.',
                'conversation_id': b2c_response.get('ConversationID'),
                'transaction': TransactionSerializer(escrow).data,
                'task_status': task.status
            })
        else:
            logger.error(f"B2C payment failed: {b2c_response.get('error')}")
            return Response({
                'success': False,
                'error': b2c_response.get('error', 'Failed to process payment'),
                'message': 'Payment failed. Please try again or contact support.'
            }, status=status.HTTP_400_BAD_REQUEST)


class MpesaCallbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        """
        Handle M-Pesa STK Push callback
        Called by Safaricom when payment is completed/cancelled
        """
        callback_data = request.data
        logger.info(f"M-Pesa callback received: {callback_data}")

        # Validate callback
        if not mpesa_service.validate_callback(callback_data):
            logger.warning("Invalid M-Pesa callback received")
            return Response({
                'ResultCode': 1,
                'ResultDesc': 'Invalid callback'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Extract data from callback
            stk_callback = callback_data.get('Body', {}).get('stkCallback', {})
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')
            checkout_id = stk_callback.get('CheckoutRequestID')

            if not checkout_id:
                logger.error("No CheckoutRequestID in callback")
                return Response({
                    'ResultCode': 1,
                    'ResultDesc': 'Missing CheckoutRequestID'
                })

            # Find transaction
            try:
                transaction = Transaction.objects.get(checkout_request_id=checkout_id)
            except Transaction.DoesNotExist:
                logger.error(f"Transaction not found for checkout: {checkout_id}")
                return Response({
                    'ResultCode': 0,
                    'ResultDesc': 'Accepted'  # Still acknowledge to M-Pesa
                })

            # Process based on result code
            if result_code == 0:
                # Success - extract M-Pesa receipt
                callback_metadata = stk_callback.get('CallbackMetadata', {})
                items = callback_metadata.get('Item', [])
                
                mpesa_receipt = None
                for item in items:
                    if item.get('Name') == 'MpesaReceiptNumber':
                        mpesa_receipt = item.get('Value')
                        break

                # Mark escrow as held
                transaction.status = 'Held'
                transaction.mpesa_reference = mpesa_receipt or f"MP{checkout_id[:10]}"
                transaction.save(update_fields=['status', 'mpesa_reference', 'updated_at'])

                # Update task status to InProgress
                task = transaction.task
                task.status = 'InProgress'
                task.save(update_fields=['status', 'updated_at'])

                # Notify the student that escrow is deposited and work can begin
                from users.notifications import Notification
                if task.assigned_student:
                    Notification.send(
                        recipient=task.assigned_student,
                        notification_type='escrow_deposited',
                        title='Escrow deposited — you can start!',
                        message=f'KES {transaction.amount} has been secured in escrow for "{task.title}". You can now begin work.',
                        task_id=task.id,
                    )

                logger.info(f"Payment successful: {mpesa_receipt} for Task {task.id}")

            else:
                # Payment failed or cancelled
                transaction.status = 'PendingDeposit'
                transaction.save(update_fields=['status', 'updated_at'])
                
                logger.warning(f"Payment failed for Task {transaction.task.id}: {result_desc}")

            return Response({
                'ResultCode': 0,
                'ResultDesc': 'Accepted'
            })

        except Exception as e:
            logger.error(f"Error processing M-Pesa callback: {str(e)}")
            return Response({
                'ResultCode': 0,
                'ResultDesc': 'Accepted'  # Always acknowledge to M-Pesa
            })


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



class CheckPaymentStatusView(APIView):
    """Check the status of an M-Pesa STK Push payment"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        checkout_request_id = request.data.get('checkout_request_id')
        
        if not checkout_request_id:
            return Response(
                {'error': 'checkout_request_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            transaction = Transaction.objects.get(checkout_request_id=checkout_request_id)
        except Transaction.DoesNotExist:
            return Response(
                {'error': 'Transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user owns this transaction
        if transaction.task.household_owner != request.user:
            return Response(
                {'error': 'Unauthorized'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Query M-Pesa for status
        status_response = mpesa_service.query_stk_status(checkout_request_id)

        if status_response.get('success'):
            result_code = status_response.get('ResultCode')
            
            # Update local status if needed
            if result_code == '0' and transaction.status == 'PendingDeposit':
                # Payment successful but callback might have been missed
                transaction.status = 'Held'
                transaction.save()
                transaction.task.status = 'InProgress'
                transaction.task.save()

            return Response({
                'success': True,
                'status': transaction.status,
                'result_code': result_code,
                'result_description': status_response.get('ResultDesc'),
                'transaction': TransactionSerializer(transaction).data
            })
        else:
            return Response({
                'success': False,
                'error': status_response.get('error'),
                'status': transaction.status,
                'transaction': TransactionSerializer(transaction).data
            })
