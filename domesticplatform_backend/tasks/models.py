from django.conf import settings
from django.db import models


class PriceGuide(models.Model):
    category = models.CharField(max_length=100, unique=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_price = models.DecimalField(max_digits=10, decimal_places=2)
    recommended_price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_recommended_price(cls, category: str):
        guide = cls.objects.filter(category__iexact=category).first()
        if guide:
            return guide.recommended_price
        return None

    def __str__(self):
        return f"{self.category}: KES {self.recommended_price} (range {self.min_price} - {self.max_price})"


class Task(models.Model):
    STATUS_CHOICES = (
        ('Posted', 'Posted'),
        ('Bidding', 'Bidding'),
        ('Assigned', 'Assigned'),
        ('InProgress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
        ('Disputed', 'Disputed'),
    )

    household_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posted_tasks'
    )
    assigned_student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=100)
    recommended_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    posted_price = models.DecimalField(max_digits=10, decimal_places=2)
    location_address = models.CharField(max_length=255, blank=True)
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Posted')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def cancel_task(self):
        if self.status in ['Posted', 'Bidding']:
            self.status = 'Cancelled'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    def mark_complete(self):
        self.status = 'Completed'
        self.save(update_fields=['status', 'updated_at'])

    def __str__(self):
        return f"{self.title} ({self.category}) - KES {self.posted_price} [{self.status}]"


class Bid(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Withdrawn', 'Withdrawn'),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='bids')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submitted_bids'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def withdraw_bid(self):
        if self.status == 'Pending':
            self.status = 'Withdrawn'
            self.save(update_fields=['status'])
            return True
        return False

    def __str__(self):
        return f"Bid by {self.student.username} on '{self.task.title}' - KES {self.amount} ({self.status})"


class Message(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Msg from {self.sender.username} to {self.receiver.username} on {self.task.title}"
