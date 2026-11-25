"""
State machine for Task status transitions.

Every status change must go through `transition(task, new_status, actor)`.
Illegal transitions raise `InvalidTransition`.  Every transition is recorded
in AuditLog automatically.
"""

from django.utils import timezone as django_tz

# ---------------------------------------------------------------------------
# Valid edges in the state machine
# ---------------------------------------------------------------------------
# (from_status, to_status) pairs that are permitted.
VALID_TRANSITIONS = {
    # Posting & broadcast
    ('Posted', 'Broadcasting'),
    ('Posted', 'Cancelled'),
    ('Bidding', 'Cancelled'),
    ('Broadcasting', 'Matched'),
    ('Broadcasting', 'Posted'),       # broadcast failure → back to Posted
    ('Broadcasting', 'Cancelled'),
    ('Matched', 'PaymentPending'),
    ('Matched', 'Reopened'),          # household cancels match / grace expires
    ('Matched', 'Cancelled'),
    ('PaymentPending', 'Assigned'),   # STK Push confirmed
    ('PaymentPending', 'Matched'),    # payment failed → revert
    ('PaymentPending', 'Reopened'),   # grace window expired
    # Active work
    ('Assigned', 'InProgress'),       # student checks in with start code
    ('Assigned', 'NoShow'),           # 30 min after scheduled time, no check-in
    ('Assigned', 'Cancelled'),        # student cancels (pre-checkin)
    ('Assigned', 'Reopened'),         # student cancels — triggers re-broadcast
    ('InProgress', 'AwaitingConfirmation'),  # student marks finished
    ('InProgress', 'Disputed'),
    # Confirmation window
    ('AwaitingConfirmation', 'Completed'),   # household confirms
    ('AwaitingConfirmation', 'Disputed'),    # household raises dispute
    ('AwaitingConfirmation', 'Completed'),   # auto-release after 48 h
    # Disputed
    ('Disputed', 'Completed'),        # admin resolves → release
    ('Disputed', 'Cancelled'),        # admin resolves → full refund
    # No-show resolution
    ('NoShow', 'Cancelled'),
    ('NoShow', 'Reopened'),
    # Re-broadcast path
    ('Reopened', 'Broadcasting'),
    ('Reopened', 'Cancelled'),
}


class InvalidTransition(Exception):
    """Raised when an illegal status transition is attempted."""
    def __init__(self, from_status, to_status):
        super().__init__(
            f"Cannot transition task from '{from_status}' to '{to_status}'."
        )
        self.from_status = from_status
        self.to_status = to_status


def can_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in VALID_TRANSITIONS


def transition(task, new_status: str, actor=None, notes: str = '') -> None:
    """
    Apply a status transition to `task`, log it in AuditLog, and save.
    Raises `InvalidTransition` if the edge is not in VALID_TRANSITIONS.
    """
    from .models import AuditLog  # local to avoid circular imports

    old_status = task.status
    if not can_transition(old_status, new_status):
        raise InvalidTransition(old_status, new_status)

    task.status = new_status
    task.updated_at = django_tz.now()
    task.save(update_fields=['status', 'updated_at'])

    AuditLog.log(
        task=task,
        actor=actor,
        action='transition',
        from_status=old_status,
        to_status=new_status,
        notes=notes,
    )


# Statuses that block deletion
DELETION_BLOCKED_STATUSES = {
    'InProgress', 'AwaitingConfirmation', 'Completed', 'Disputed',
}

# Statuses that require the cancellation-with-refund path instead of soft-delete
CANCEL_REQUIRED_STATUSES = {
    'Assigned', 'NoShow',
}

# Statuses where the household may cancel freely before payment
FREE_CANCEL_STATUSES = {
    'Posted', 'Bidding', 'Broadcasting', 'Matched', 'PaymentPending', 'Reopened',
}
