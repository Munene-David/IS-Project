import random
import string
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone as django_tz


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_start_code():
    """Return a random 4-digit string, e.g. '7391'."""
    return ''.join(random.choices(string.digits, k=4))


PHOTO_UPLOAD_PATH = 'task_photos/'
PHOTO_MAX_SIZE_MB = 5
ALLOWED_PHOTO_CONTENT_TYPES = ('image/jpeg', 'image/png', 'image/webp')


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
        ('Broadcasting', 'Broadcasting'),
        ('Matched', 'Matched'),
        ('PaymentPending', 'Payment Pending'),
        ('Assigned', 'Assigned'),
        ('InProgress', 'In Progress'),
        ('AwaitingConfirmation', 'Awaiting Confirmation'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
        ('Disputed', 'Disputed'),
        ('Reopened', 'Reopened'),
        ('NoShow', 'No Show'),
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
    # Geolocation verification: household confirms a map pin before posting
    location_landmark = models.CharField(
        max_length=200, blank=True,
        help_text='Optional landmark to help the student find the place.'
    )
    geofence_radius_m = models.PositiveIntegerField(
        default=150,
        help_text='Radius in metres around the pin where check-in is accepted.'
    )
    location_pin_confirmed = models.BooleanField(
        default=False,
        help_text='Household confirmed the map pin. Required to post a task.'
    )
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='Posted')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Broadcast-matching fields
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_time = models.TimeField(null=True, blank=True)
    broadcast_round = models.IntegerField(default=0)
    search_radius_km = models.DecimalField(max_digits=5, decimal_places=1, default=5)
    grace_window_deadline = models.DateTimeField(null=True, blank=True)

    # Soft-delete fields (task removal)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Confirmation window (48 h from student marking complete)
    confirmation_deadline = models.DateTimeField(null=True, blank=True)

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


class TaskCompletion(models.Model):
    """
    Tracks the lifecycle of an in-progress task: start code, timestamps, GPS,
    and optional before/after photos.  One record per task.
    """
    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='completion')

    # Start-code (shown to household, entered by student on arrival)
    start_code = models.CharField(max_length=4, default=_generate_start_code)
    start_code_verified = models.BooleanField(default=False)

    # Timestamps
    arrived_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # Optional GPS at check-in
    checkin_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    checkin_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Optional photos (stored as file uploads)
    before_photo = models.ImageField(
        upload_to=PHOTO_UPLOAD_PATH, null=True, blank=True,
        help_text='Before-work photo (JPEG/PNG/WebP, max 5 MB)'
    )
    after_photo = models.ImageField(
        upload_to=PHOTO_UPLOAD_PATH, null=True, blank=True,
        help_text='After-work photo (JPEG/PNG/WebP, max 5 MB)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Completion for Task #{self.task_id} [verified={self.start_code_verified}]"


class CheckIn(models.Model):
    """
    Append-only record of every location check-in attempt.

    One row is created per submitted position (start-code attempt, retry,
    or finish).  Rows are NEVER updated except by the retention job, which
    anonymises coordinates after the retention period.  Location is
    captured ONLY at explicit check-in/finish events — the app never
    tracks students continuously in the background.
    """
    TYPE_CHOICES = (
        ('ARRIVAL', 'Arrival attempt / retry'),
        ('START', 'Accepted check-in that started the task'),
        ('FINISH', 'Check-out when the student marks work finished'),
    )
    RESULT_CHOICES = (
        ('VERIFIED', 'Inside geofence with acceptable accuracy'),
        ('OUT_OF_RANGE', 'Outside the geofence radius'),
        ('LOW_ACCURACY', 'GPS accuracy worse than the policy threshold'),
        ('LOCATION_DENIED', 'Location permission denied or unavailable'),
        ('WRONG_CODE', 'Start code did not match'),
        ('FLAGGED_MOCK', 'Mock/simulated location detected'),
    )

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name='checkins'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, related_name='checkins'
    )
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='ARRIVAL')

    # Position at the moment of the check-in event
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.FloatField(null=True, blank=True)
    distance_m = models.FloatField(null=True, blank=True, help_text='Haversine distance to the task pin')

    # Timing: device clock vs server clock (anti-spoofing)
    device_time = models.DateTimeField(null=True, blank=True)
    server_time = models.DateTimeField(auto_now_add=True)
    time_skew_seconds = models.IntegerField(null=True, blank=True)

    result = models.CharField(max_length=20, choices=RESULT_CHOICES)

    # Anti-spoofing flags
    mock_location_flag = models.BooleanField(default=False)
    late_sync_flag = models.BooleanField(default=False, help_text='Submitted from the offline queue after the event')
    impossible_jump_flag = models.BooleanField(
        default=False,
        help_text='Implied speed from the previous check-in exceeds the policy limit'
    )

    device_info = models.JSONField(default=dict, blank=True)

    # Set by the retention job once coordinates have been anonymised
    anonymised_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['server_time']
        verbose_name = 'Location Check-in'

    def __str__(self):
        return f"CheckIn #{self.id} Task #{self.task_id} {self.type} [{self.result}]"


class LocationConsent(models.Model):
    """
    Records that a student accepted the location-collection notice.
    Required before the student's first check-in; version is stored so a
    re-consent can be demanded when the notice materially changes.
    """
    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, related_name='location_consent'
    )
    version = models.CharField(max_length=20)
    consented_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} consented to location v{self.version}"


class LocationPolicy(models.Model):
    """
    Admin-configurable geolocation policy (single-row singleton).
    Use LocationPolicy.get() to retrieve.
    """
    # Allow a flagged check-in to start the task even when the student
    # denied location permission entirely.
    allow_flagged_when_denied = models.BooleanField(
        default=False,
        help_text='If on, a student who denied location permission may still check in (flagged).'
    )
    # Retention period for check-in coordinates (days)
    retention_days = models.PositiveIntegerField(
        default=90,
        help_text='Check-in coordinates are anonymised after this many days (longer while a dispute is open).'
    )
    # GPS accuracy worse than this (metres) is flagged as LOW_ACCURACY
    low_accuracy_threshold_m = models.PositiveIntegerField(default=100)
    # Allowed clock drift between device and server (seconds)
    max_time_skew_seconds = models.PositiveIntegerField(default=300)
    # Implied travel speed above which a check-in jump is flagged (m/s; 55 ≈ 200 km/h)
    max_speed_mps = models.PositiveIntegerField(default=55)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Location Policy'
        verbose_name_plural = 'Location Policies'

    @classmethod
    def get(cls):
        """Return the single policy row, creating defaults if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return (
            f"LocationPolicy: retention={self.retention_days}d, "
            f"low-acc>{self.low_accuracy_threshold_m}m, "
            f"denied-allowed={self.allow_flagged_when_denied}"
        )


class CancellationPolicy(models.Model):
    """
    Configurable cancellation refund policy (single-row singleton).
    Use CancellationPolicy.get() to retrieve.
    """
    # Hours before scheduled start at which a free cancellation window ends
    free_before_hours = models.IntegerField(
        default=24,
        help_text='Cancellation is free (full refund) if >N hours before scheduled start.'
    )
    # Refund percentage when cancelling within the free window (0-100)
    partial_refund_pct = models.IntegerField(
        default=80,
        help_text='Percentage refunded when household cancels within the free-before window.'
    )
    # Student cancellation always gives full refund to household (student penalty applied)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cancellation Policy'
        verbose_name_plural = 'Cancellation Policies'

    @classmethod
    def get(cls):
        """Return the single policy row, creating defaults if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return (
            f"CancellationPolicy: free if >{self.free_before_hours}h, "
            f"partial={self.partial_refund_pct}% otherwise"
        )


class Dispute(models.Model):
    """
    One dispute per task (enforced by OneToOneField).
    Household raises it; student responds; admin resolves.
    """
    REASON_CHOICES = (
        ('not_completed', 'Work not completed'),
        ('poor_quality', 'Poor quality'),
        ('did_not_show', 'Student did not show up'),
        ('damaged_property', 'Damaged property'),
        ('other', 'Other'),
    )
    OUTCOME_CHOICES = (
        ('full_refund', 'Full refund to household'),
        ('partial_refund', 'Partial refund to household'),
        ('release', 'Release payment to student'),
    )

    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='dispute')
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='disputes_raised'
    )
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField()

    student_response = models.TextField(blank=True)
    student_responded_at = models.DateTimeField(null=True, blank=True)

    # Admin resolution
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='disputes_resolved'
    )
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    # partial refund amount when outcome == 'partial_refund'
    partial_refund_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    admin_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dispute on Task #{self.task_id}: {self.reason} [{self.outcome or 'pending'}]"


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


class TaskRequest(models.Model):
    """Delivery record for a broadcast task sent to an individual student."""
    STATUS_CHOICES = (
        ('SENT', 'Sent'),
        ('VIEWED', 'Viewed'),
        ('ACCEPTED', 'Accepted'),
        ('DECLINED', 'Declined'),
        ('IGNORED', 'Ignored'),
        ('TAKEN', 'Taken by another'),
        ('EXPIRED', 'Expired'),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='requests')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_requests'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SENT')
    sent_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    broadcast_round = models.IntegerField(default=1)
    rank_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('task', 'student')
        ordering = ['-sent_at']

    def __str__(self):
        return (
            f"TaskRequest [{self.status}] {self.student.username} → "
            f"'{self.task.title}' (round {self.broadcast_round})"
        )


class AuditLog(models.Model):
    """
    Append-only audit log for every task-status transition and admin decision.
    Never update or delete rows.
    """
    ACTION_CHOICES = (
        ('transition', 'Status Transition'),
        ('admin_decision', 'Admin Decision'),
        ('payment_event', 'Payment Event'),
        ('dispute_event', 'Dispute Event'),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_actions'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_status = models.CharField(max_length=25, blank=True)
    to_status = models.CharField(max_length=25, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return (
            f"[{self.action}] Task #{self.task_id}: "
            f"{self.from_status} → {self.to_status} by {self.actor}"
        )

    @classmethod
    def log(cls, task, actor, action, from_status='', to_status='', notes=''):
        return cls.objects.create(
            task=task,
            actor=actor,
            action=action,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
        )
