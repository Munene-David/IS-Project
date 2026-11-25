from django.db import models
from django.conf import settings


class Notification(models.Model):
    TYPE_CHOICES = (
        ('bid_accepted', 'Bid Accepted'),
        ('bid_submitted', 'New Bid'),
        ('payment_received', 'Payment Received'),
        ('task_completed', 'Task Completed'),
        ('escrow_deposited', 'Escrow Deposited'),
        # Broadcast-flow
        ('task_request', 'Task Request'),
        ('task_matched', 'Task Matched'),
        ('request_taken', 'Request Taken'),
        ('grace_window', 'Grace Window'),
        ('payment_failed', 'Payment Failed'),
        ('student_flagged', 'Student Flagged'),
        # Completion verification
        ('start_code', 'Start Code'),
        ('awaiting_confirmation', 'Awaiting Confirmation'),
        ('confirmation_reminder', 'Confirmation Reminder'),
        ('auto_released', 'Payment Auto-Released'),
        # Cancellation & refunds
        ('cancellation', 'Task Cancelled'),
        ('refund', 'Refund Issued'),
        # No-show
        ('no_show', 'No Show'),
        # Disputes
        ('dispute_raised', 'Dispute Raised'),
        ('dispute_response', 'Dispute Response'),
        ('dispute_resolved', 'Dispute Resolved'),
        # Task removal
        ('task_deleted', 'Task Deleted'),
        ('general', 'General'),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='general')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    task_id = models.IntegerField(null=True, blank=True)  # link back to task
    request_id = models.IntegerField(null=True, blank=True)  # link back to TaskRequest (task_request type)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient.username}: {self.title}"

    @classmethod
    def send(cls, recipient, notification_type, title, message, task_id=None, request_id=None):
        """Helper to create a notification."""
        return cls.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            task_id=task_id,
            request_id=request_id,
        )
