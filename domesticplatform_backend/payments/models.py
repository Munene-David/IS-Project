import uuid

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Avg


class Transaction(models.Model):
    """
    Single escrow record per task (kept for backward compatibility).
    Use TransactionLedger for the full financial history.
    """
    STATUS_CHOICES = (
        ('PendingDeposit', 'Pending Deposit'),
        ('Held', 'Held in Escrow'),
        ('Released', 'Released to Student'),
        ('Refunded', 'Refunded to Household'),
        ('PartialRefund', 'Partial Refund'),
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


class TransactionLedger(models.Model):
    """
    Append-only financial ledger.  NEVER update or delete rows.
    Every monetary event (deposit, hold, release, refund) is recorded here.
    Refunds / payouts are idempotent — guard with the idempotency_key field.
    """
    TYPE_CHOICES = (
        ('DEPOSIT', 'Deposit'),
        ('HOLD', 'Hold in Escrow'),
        ('RELEASE', 'Release to Student'),
        ('REFUND', 'Full Refund to Household'),
        ('PARTIAL_REFUND', 'Partial Refund to Household'),
        ('PENALTY', 'Cancellation Penalty'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('SIMULATED', 'Simulated (sandbox)'),
    )

    task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.CASCADE,
        related_name='ledger_entries'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    mpesa_reference = models.CharField(max_length=100, blank=True)
    # Idempotency key: caller supplies a UUID so duplicate submissions are ignored
    idempotency_key = models.UUIDField(unique=True, default=uuid.uuid4)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ledger_entries'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return (
            f"[{self.transaction_type}] Task #{self.task_id} "
            f"KES {self.amount} [{self.status}] @ {self.created_at:%Y-%m-%d %H:%M}"
        )

    @classmethod
    def record(cls, task, transaction_type, amount, actor=None,
               mpesa_reference='', notes='', idempotency_key=None, status='COMPLETED'):
        """
        Create a ledger entry.  If `idempotency_key` already exists, return
        the existing row without creating a duplicate (idempotent).
        """
        if idempotency_key:
            existing = cls.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False
        kwargs = dict(
            task=task,
            transaction_type=transaction_type,
            amount=amount,
            actor=actor,
            mpesa_reference=mpesa_reference,
            notes=notes,
            status=status,
        )
        if idempotency_key:
            kwargs['idempotency_key'] = idempotency_key
        entry = cls.objects.create(**kwargs)
        return entry, True


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
        unique_together = ('task', 'rater', 'rated_user')
        ordering = ['-created_at']

    @classmethod
    def calculate_average(cls, user):
        result = cls.objects.filter(rated_user=user).aggregate(avg_score=Avg('score'))
        return round(result['avg_score'] or 0.0, 1)

    def __str__(self):
        return f"Rating by {self.rater.username} for {self.rated_user.username}: {self.score}★"
