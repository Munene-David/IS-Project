from django.db import models
from django.conf import settings


class Notification(models.Model):
    TYPE_CHOICES = (
        ('bid_accepted', 'Bid Accepted'),
        ('bid_submitted', 'New Bid'),
        ('payment_received', 'Payment Received'),
        ('task_completed', 'Task Completed'),
        ('escrow_deposited', 'Escrow Deposited'),
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient.username}: {self.title}"

    @classmethod
    def send(cls, recipient, notification_type, title, message, task_id=None):
        """Helper to create a notification."""
        return cls.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            task_id=task_id,
        )
