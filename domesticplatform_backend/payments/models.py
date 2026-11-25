from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Avg


class Transaction(models.Model):
    STATUS_CHOICES = (
        ('PendingDeposit', 'Pending Deposit'),
        ('Held', 'Held in Escrow'),
        ('Released', 'Released to Student'),
        ('Refunded', 'Refunded to Household'),
    )

    task = models.OneToOneField(
        'tasks.Task',
        on_delete=models.CASCADE,
        related_name='escrow_transaction'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PendingDeposit')
    mpesa_reference = models.CharField(max_length=100, blank=True, null=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def initiate_deposit(self, checkout_id: str = None, phone: str = None):
        self.status = 'PendingDeposit'
        if checkout_id:
            self.checkout_request_id = checkout_id
        if phone:
            self.phone_number = phone
        self.save(update_fields=['status', 'checkout_request_id', 'phone_number', 'updated_at'])
        return True

    def mark_held(self, mpesa_ref: str):
        self.status = 'Held'
        self.mpesa_reference = mpesa_ref
        self.save(update_fields=['status', 'mpesa_reference', 'updated_at'])

    def release_funds(self):
        if self.status == 'Held':
            self.status = 'Released'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    def refund(self):
        if self.status == 'Held':
            self.status = 'Refunded'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    def __str__(self):
        return f"Escrow #{self.id} for Task '{self.task.title}' - KES {self.amount} [{self.status}]"


class Rating(models.Model):
    task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.CASCADE,
        related_name='ratings'
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_given'
    )
    rated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_received'
    )
    score = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A user can rate another user once per task
        unique_together = ('task', 'rater', 'rated_user')
        ordering = ['-created_at']

    @classmethod
    def calculate_average(cls, user):
        result = cls.objects.filter(rated_user=user).aggregate(avg_score=Avg('score'))
        return round(result['avg_score'] or 0.0, 1)

    def __str__(self):
        return f"Rating by {self.rater.username} for {self.rated_user.username}: {self.score}★"
