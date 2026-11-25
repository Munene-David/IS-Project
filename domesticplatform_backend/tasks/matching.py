"""
Broadcast-matching service for the domestic jobs platform.

Replaces the manual bidding flow with a first-to-accept model:
  1. When a household posts a task, find_eligible_students() is called.
  2. broadcast_round() sends TaskRequest records to the top-N students.
  3. The first student to call accept_task_request() wins (atomic, select_for_update).
  4. After 10 min the household has a grace window to cancel before payment.
  5. If all rounds fail, the household is notified with options.

No Celery/Channels required — a background threading.Timer is used so the
project runs without additional infrastructure. This is production-swap-ready:
the _schedule_next_round() function signature is compatible with a Celery task.
"""

import math
import threading
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone as django_tz

from payments.models import Rating

# ---------------------------------------------------------------------------
# Configuration — override via Django settings if desired
# ---------------------------------------------------------------------------
ROUND_1_RADIUS_KM = getattr(settings, 'BROADCAST_ROUND1_RADIUS_KM', 5)
ROUND_2_RADIUS_KM = getattr(settings, 'BROADCAST_ROUND2_RADIUS_KM', 15)
ROUND_1_MIN_RATING = getattr(settings, 'BROADCAST_ROUND1_MIN_RATING', 4.0)
ROUND_2_MIN_RATING = getattr(settings, 'BROADCAST_ROUND2_ROUND2_MIN_RATING', 2.5)
ROUND_SIZE = getattr(settings, 'BROADCAST_ROUND_SIZE', 5)        # students per round
ROUND_TIMEOUT_SECONDS = getattr(settings, 'BROADCAST_ROUND_TIMEOUT', 600)   # 10 min
GRACE_WINDOW_SECONDS = getattr(settings, 'BROADCAST_GRACE_WINDOW', 600)     # 10 min


# ---------------------------------------------------------------------------
# Haversine distance helper
# ---------------------------------------------------------------------------

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Return great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlam = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# 1. find_eligible_students
# ---------------------------------------------------------------------------

def find_eligible_students(task, radius_km=None, min_rating=None):
    """
    Return a ranked list of (student_user, score, distance_km) tuples
    of students eligible for the given task.

    Eligibility criteria:
    - Verified student (verification_status == 'Verified')
    - Active (is_active, availability_status, not flagged)
    - Offers the task category (categories_offered contains category, case-insensitive)
    - Free at the task date/time (no overlapping ACCEPTED TaskRequest for another task)
    - Within radius_km of the task location
    - Average rating >= min_rating (new students with 0 ratings are allowed)
    - Not blocked by the household

    Ranking score (higher = better):
    - 50% weight: rating (normalised 0-5 → 0-50)
    - 30% weight: distance (inverse, closer = higher score)
    - 20% weight: reliability_score multiplier
    - New-student boost: +5 pts if 0 completed tasks (encourages new joiners)
    """
    from .models import Task, TaskRequest  # local import avoids circular refs
    from users.models import BlockedStudent

    if radius_km is None:
        radius_km = float(task.search_radius_km or ROUND_1_RADIUS_KM)
    if min_rating is None:
        min_rating = float(
            task.household_owner.household_profile.min_rating
            if hasattr(task.household_owner, 'household_profile')
            else 0
        )

    from users.models import CustomUser, StudentProfile

    # --- Base queryset: verified, active students --------------------
    candidates = CustomUser.objects.filter(
        role='STUDENT',
        is_active=True,
        student_profile__verification_status='Verified',
        student_profile__availability_status=True,
        student_profile__is_flagged=False,
    ).select_related('student_profile')

    # --- Exclude household's block list -----------------------------
    blocked_ids = BlockedStudent.objects.filter(
        household=task.household_owner
    ).values_list('student_id', flat=True)
    candidates = candidates.exclude(id__in=blocked_ids)

    # --- Filter by category -----------------------------------------
    task_cat = (task.category or '').lower()
    # JSONField filter: student has declared the category in categories_offered
    # We fall back to accepting students with an EMPTY list (they serve all categories)
    # so early-stage platforms work before students fill in their profile.
    eligible = []
    for student in candidates:
        sp = student.student_profile
        cats = [c.lower() for c in (sp.categories_offered or [])]
        if cats and task_cat not in cats:
            continue

        # --- Double-booking check: no overlapping accepted task -----
        if task.scheduled_date and task.scheduled_time:
            scheduled_dt = datetime.combine(task.scheduled_date, task.scheduled_time)
            scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
            overlap = TaskRequest.objects.filter(
                student=student,
                status='ACCEPTED',
                task__scheduled_date=task.scheduled_date,
            ).filter(
                task__scheduled_time__gte=(
                    datetime.combine(task.scheduled_date, task.scheduled_time)
                    - timedelta(hours=2)
                ).time()
            ).filter(
                task__scheduled_time__lte=(
                    datetime.combine(task.scheduled_date, task.scheduled_time)
                    + timedelta(hours=4)
                ).time()
            ).exists()
            if overlap:
                continue

        # --- Distance filter ----------------------------------------
        if (task.location_lat and task.location_lng
                and sp.location_lat and sp.location_lng):
            dist = haversine_km(
                task.location_lat, task.location_lng,
                sp.location_lat, sp.location_lng
            )
            if dist > radius_km:
                continue
        else:
            # No coordinates on student — treat as max radius
            dist = float(radius_km)

        # --- Rating filter -------------------------------------------
        avg_rating = Rating.calculate_average(student)
        if avg_rating > 0 and avg_rating < min_rating:
            continue

        eligible.append((student, avg_rating, dist))

    # --- Scoring & ranking ------------------------------------------
    scored = []
    for (student, avg_rating, dist) in eligible:
        # Rating component (0 → 50 points)
        rating_score = (avg_rating / 5.0) * 50 if avg_rating > 0 else 25  # neutral for new students

        # Distance component (0 → 30 points, closer = more)
        if dist < radius_km:
            distance_score = 30 * (1 - dist / radius_km)
        else:
            distance_score = 0

        # Reliability multiplier (default 1.0, reduced on cancellations)
        reliability = float(student.student_profile.reliability_score)
        reliability_score = reliability * 20

        # New-student boost
        from payments.models import Rating as RatingModel
        completed = RatingModel.objects.filter(rated_user=student).count()
        new_student_boost = 5 if completed == 0 else 0

        total = (rating_score + distance_score + reliability_score + new_student_boost)
        scored.append((student, total, dist))

    scored.sort(key=lambda x: -x[1])
    return scored  # [(student, score, distance_km), ...]


# ---------------------------------------------------------------------------
# 2. Broadcast helpers
# ---------------------------------------------------------------------------

def _send_requests_to_students(task, students, broadcast_round):
    """Create TaskRequest rows and send notifications."""
    from .models import TaskRequest
    from users.notifications import Notification

    for (student, score, dist) in students:
        # unique_together guard: skip if already sent
        try:
            req, _created = TaskRequest.objects.get_or_create(
                task=task,
                student=student,
                defaults={
                    'status': 'SENT',
                    'broadcast_round': broadcast_round,
                    'rank_score': score,
                }
            )
            Notification.send(
                recipient=student,
                notification_type='task_request',
                title='New task available for you!',
                message=(
                    f'A "{task.category}" task is available near you: '
                    f'"{task.title}" for KES {task.posted_price}. '
                    f'Open the app to accept.'
                ),
                task_id=task.id,
                request_id=req.id,
            )
        except Exception:
            pass  # already sent (race guard)


def broadcast_task(task):
    """
    Entry point. Called right after a task is posted (or reopened).
    Sends round-1 requests (top ROUND_SIZE students within tight radius).
    Schedules round-2 and failure notification via threading.Timer.
    """
    from .models import Task

    # Refresh from DB
    task = Task.objects.get(pk=task.pk)
    task.status = 'Broadcasting'
    task.broadcast_round = 1
    task.save(update_fields=['status', 'broadcast_round', 'updated_at'])

    ranked = find_eligible_students(task, radius_km=ROUND_1_RADIUS_KM,
                                     min_rating=ROUND_1_MIN_RATING)
    batch = ranked[:ROUND_SIZE]

    if batch:
        _send_requests_to_students(task, batch, broadcast_round=1)
        # Schedule round-2 to run after ROUND_TIMEOUT_SECONDS
        _schedule_next_round(task.id, delay=ROUND_TIMEOUT_SECONDS)
    else:
        # No eligible students at all — skip to round 2 immediately
        _run_round_2(task.id)


def _schedule_next_round(task_id, delay=ROUND_TIMEOUT_SECONDS):
    """Schedule _run_round_2 after `delay` seconds using threading.Timer."""
    t = threading.Timer(delay, _run_round_2, args=[task_id])
    t.daemon = True
    t.start()


def _run_round_2(task_id):
    """
    Called after round-1 timeout.
    If still unmatched → widen radius + lower min_rating → round 2.
    If matched → do nothing.
    """
    from .models import Task, TaskRequest
    from users.notifications import Notification

    try:
        task = Task.objects.get(pk=task_id)
    except Exception:
        return

    if task.status != 'Broadcasting':
        return  # already matched or cancelled

    # Expire round-1 requests that weren't responded to
    TaskRequest.objects.filter(
        task=task, broadcast_round=1, status__in=['SENT', 'VIEWED']
    ).update(status='EXPIRED')

    # Widen search
    ranked = find_eligible_students(task, radius_km=ROUND_2_RADIUS_KM,
                                     min_rating=ROUND_2_MIN_RATING)
    # Exclude students who already got round-1
    already_sent_ids = set(
        TaskRequest.objects.filter(task=task).values_list('student_id', flat=True)
    )
    batch = [s for s in ranked if s[0].id not in already_sent_ids][:ROUND_SIZE]

    if batch:
        task.broadcast_round = 2
        task.search_radius_km = ROUND_2_RADIUS_KM
        task.save(update_fields=['broadcast_round', 'search_radius_km', 'updated_at'])
        _send_requests_to_students(task, batch, broadcast_round=2)
        # After round-2 timeout → notify household of failure
        t = threading.Timer(ROUND_TIMEOUT_SECONDS, _handle_broadcast_failure, args=[task_id])
        t.daemon = True
        t.start()
    else:
        _handle_broadcast_failure(task_id)


def _handle_broadcast_failure(task_id):
    """All rounds exhausted with no acceptance. Notify the household."""
    from .models import Task, TaskRequest
    from users.notifications import Notification

    try:
        task = Task.objects.get(pk=task_id)
    except Exception:
        return

    if task.status != 'Broadcasting':
        return  # matched in the meantime

    # Expire remaining round-2 requests
    TaskRequest.objects.filter(
        task=task, broadcast_round=2, status__in=['SENT', 'VIEWED']
    ).update(status='EXPIRED')

    task.status = 'Posted'
    task.save(update_fields=['status', 'updated_at'])

    Notification.send(
        recipient=task.household_owner,
        notification_type='general',
        title='No students available',
        message=(
            f'No students could be found for "{task.title}". '
            f'You can raise the budget, change the time, or allow the task to expire.'
        ),
        task_id=task.id,
    )


# ---------------------------------------------------------------------------
# 3. Atomic first-to-accept
# ---------------------------------------------------------------------------

def accept_task_request(task_request_id, student):
    """
    Atomic first-to-accept:
    1. select_for_update on the TaskRequest to prevent races.
    2. If still SENT/VIEWED → accept; mark all others TAKEN; set task Matched.
    3. Start 10-min grace window.
    4. Return (success, message).
    """
    from .models import Task, TaskRequest
    from users.notifications import Notification

    with db_transaction.atomic():
        try:
            req = TaskRequest.objects.select_for_update().get(
                pk=task_request_id, student=student
            )
        except TaskRequest.DoesNotExist:
            return False, 'Request not found.'

        if req.status not in ('SENT', 'VIEWED'):
            return False, f'This request is no longer available ({req.status}).'

        # Check task is still unmatched
        task = Task.objects.select_for_update().get(pk=req.task_id)
        if task.status != 'Broadcasting':
            return False, 'This task has already been matched.'

        # Accept this request
        req.status = 'ACCEPTED'
        req.responded_at = django_tz.now()
        req.save(update_fields=['status', 'responded_at'])

        # Mark all other open requests as TAKEN
        TaskRequest.objects.filter(
            task=task,
        ).exclude(pk=req.pk).filter(
            status__in=['SENT', 'VIEWED']
        ).update(status='TAKEN')

        # Assign student, set grace window
        task.assigned_student = student
        task.status = 'Matched'
        task.grace_window_deadline = django_tz.now() + timedelta(seconds=GRACE_WINDOW_SECONDS)
        task.save(update_fields=['assigned_student', 'status', 'grace_window_deadline', 'updated_at'])

    # Notify other students who were TAKEN
    taken_requests = TaskRequest.objects.filter(
        task=task, status='TAKEN'
    ).select_related('student')
    for tr in taken_requests:
        Notification.send(
            recipient=tr.student,
            notification_type='request_taken',
            title='Task has been taken',
            message=f'"{task.title}" has been accepted by another student. Keep an eye out for more!',
            task_id=task.id,
        )

    # Notify the winning student (hide exact address until payment)
    Notification.send(
        recipient=student,
        notification_type='task_matched',
        title='You got the job! ✅',
        message=(
            f'You have been matched with "{task.title}" '
            f'for KES {task.posted_price}. '
            f'The household will confirm and pay within 10 minutes.'
        ),
        task_id=task.id,
    )

    # Notify the household
    Notification.send(
        recipient=task.household_owner,
        notification_type='task_matched',
        title='Match found!',
        message=(
            f'{student.first_name or student.username} accepted your task '
            f'"{task.title}". You have 10 minutes to confirm and pay. '
            f'Full address will be shared after payment.'
        ),
        task_id=task.id,
    )

    # Schedule grace-window expiry check
    t = threading.Timer(GRACE_WINDOW_SECONDS + 60, _check_grace_window_expired, args=[task.id])
    t.daemon = True
    t.start()

    return True, 'Task accepted successfully.'


def _check_grace_window_expired(task_id):
    """
    If the household has not confirmed payment within the grace window,
    cancel the match and re-broadcast.
    """
    from .models import Task
    from users.notifications import Notification

    try:
        task = Task.objects.get(pk=task_id)
    except Exception:
        return

    if task.status not in ('Matched', 'PaymentPending'):
        return  # household acted in time

    student = task.assigned_student

    task.assigned_student = None
    task.status = 'Reopened'
    task.grace_window_deadline = None
    task.broadcast_round = 0
    task.save(update_fields=['assigned_student', 'status', 'grace_window_deadline',
                              'broadcast_round', 'updated_at'])

    if student:
        Notification.send(
            recipient=student,
            notification_type='general',
            title='Household did not confirm in time',
            message=(
                f'The household for "{task.title}" did not complete payment in time. '
                f'The task has been reopened.'
            ),
            task_id=task.id,
        )

    Notification.send(
        recipient=task.household_owner,
        notification_type='general',
        title='Grace window expired — task reopened',
        message=(
            f'You did not confirm payment for "{task.title}" within 10 minutes. '
            f'The task has been reopened and new students will be notified.'
        ),
        task_id=task.id,
    )

    # Re-broadcast
    broadcast_task(task)


# ---------------------------------------------------------------------------
# 6. Rebroadcast to remaining eligible students
#    - Skips students who already DECLINED or IGNORED
#    - Re-opens EXPIRED requests so those students get a fresh chance
#    - Sends to brand-new eligible students who were never notified
# ---------------------------------------------------------------------------

def rebroadcast_to_remaining(task):
    """
    Push a fresh broadcast to every eligible student who has not explicitly
    opted out (DECLINED / IGNORED) or already won (ACCEPTED / TAKEN).

    Re-opens EXPIRED requests (timed-out round) and sends to new students.
    Returns the number of students reached.
    """
    from .models import Task, TaskRequest
    from users.notifications import Notification

    task = Task.objects.get(pk=task.pk)

    SKIP_STATUSES = {'DECLINED', 'IGNORED', 'ACCEPTED', 'TAKEN'}

    # Re-open expired requests → give those students another chance
    expired_qs = TaskRequest.objects.filter(task=task, status='EXPIRED')
    reopened_ids = list(expired_qs.values_list('student_id', flat=True))
    expired_qs.update(status='SENT')

    # Find all eligible students at wide radius
    ranked = find_eligible_students(task, radius_km=ROUND_2_RADIUS_KM,
                                    min_rating=ROUND_2_MIN_RATING)

    # Skip students who opted out or already won
    skip_ids = set(
        TaskRequest.objects.filter(task=task, status__in=SKIP_STATUSES)
        .values_list('student_id', flat=True)
    )
    # Skip students who already have an active (non-expired) request
    active_ids = set(
        TaskRequest.objects.filter(task=task)
        .exclude(status='EXPIRED')
        .values_list('student_id', flat=True)
    )

    new_batch = [
        (s, score, dist) for s, score, dist in ranked
        if s.id not in skip_ids and s.id not in active_ids
    ]

    # Send to brand-new students
    if new_batch:
        next_round = (task.broadcast_round or 1) + 1
        _send_requests_to_students(task, new_batch, broadcast_round=next_round)
        task.broadcast_round = next_round
        task.status = 'Broadcasting'
        task.save(update_fields=['broadcast_round', 'status', 'updated_at'])

    # Re-notify students whose EXPIRED requests were just reopened
    for student_id in reopened_ids:
        if student_id in skip_ids:
            continue
        try:
            req = TaskRequest.objects.get(task=task, student_id=student_id)
            from users.models import CustomUser
            student = CustomUser.objects.get(pk=student_id)
            Notification.send(
                recipient=student,
                notification_type='task_request',
                title='Task available again!',
                message=(
                    f'A "{task.category}" task is still looking for a student: '
                    f'"{task.title}" for KES {task.posted_price}. '
                    f'Open Available Tasks to accept.'
                ),
                task_id=task.id,
                request_id=req.id,
            )
        except Exception:
            pass

    total = len(new_batch) + len([i for i in reopened_ids if i not in skip_ids])
    return total
# ---------------------------------------------------------------------------
# 4. Household cancellation within grace window
# ---------------------------------------------------------------------------

def household_cancel_match(task, block_student=False):
    """
    Household cancels within the grace window.
    Optionally blocks the student. Re-broadcasts.
    """
    from users.notifications import Notification
    from users.models import BlockedStudent

    if task.status not in ('Matched', 'PaymentPending'):
        return False, 'No active match to cancel.'

    if task.grace_window_deadline and django_tz.now() > task.grace_window_deadline:
        return False, 'Grace window has expired. Payment cannot be cancelled at this stage.'

    student = task.assigned_student

    if block_student and student:
        BlockedStudent.objects.get_or_create(
            household=task.household_owner,
            student=student,
        )

    task.assigned_student = None
    task.status = 'Reopened'
    task.grace_window_deadline = None
    task.broadcast_round = 0
    task.save(update_fields=['assigned_student', 'status', 'grace_window_deadline',
                              'broadcast_round', 'updated_at'])

    if student:
        Notification.send(
            recipient=student,
            notification_type='general',
            title='Household cancelled the match',
            message=f'The household cancelled the match for "{task.title}".',
            task_id=task.id,
        )

    # Re-broadcast to find another student
    broadcast_task(task)
    return True, 'Match cancelled and task re-broadcast.'


# ---------------------------------------------------------------------------
# 5. Post-payment failure handler
# ---------------------------------------------------------------------------

def handle_payment_failure(task):
    """Called when M-Pesa payment fails or times out after the grace window."""
    from users.notifications import Notification
    from payments.models import Transaction

    student = task.assigned_student

    task.assigned_student = None
    task.status = 'Reopened'
    task.grace_window_deadline = None
    task.broadcast_round = 0
    task.save(update_fields=['assigned_student', 'status', 'grace_window_deadline',
                              'broadcast_round', 'updated_at'])

    # Clean up any pending transaction
    try:
        txn = task.escrow_transaction
        if txn.status == 'PendingDeposit':
            txn.status = 'Refunded'
            txn.save(update_fields=['status', 'updated_at'])
    except Exception:
        pass

    if student:
        Notification.send(
            recipient=student,
            notification_type='payment_failed',
            title='Payment failed — task reopened',
            message=(
                f'Payment for "{task.title}" failed. The task has been reopened.'
            ),
            task_id=task.id,
        )

    Notification.send(
        recipient=task.household_owner,
        notification_type='payment_failed',
        title='Payment failed — task reopened',
        message=(
            f'Payment for "{task.title}" could not be processed. '
            f'The task has been reopened and new students will be notified.'
        ),
        task_id=task.id,
    )

    broadcast_task(task)
