"""
Management command: run_scheduled_tasks

Processes time-sensitive task lifecycle events.  Run this via cron every 5–10 minutes:
    python manage.py run_scheduled_tasks

Events handled:
1. No-show detection  — if student has not checked in within 30 min of scheduled start
2. Confirmation reminders — 24 h and 40 h after student marks complete (AwaitingConfirmation)
3. Auto-release (48 h)  — release escrow if household has not confirmed/disputed in time

This command is idempotent: running it multiple times is safe.
"""

import uuid
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone as django_tz

from tasks.models import Task, TaskCompletion, AuditLog, CheckIn, Dispute, LocationPolicy
from tasks.task_transitions import transition, InvalidTransition
from payments import refund_service
from users.notifications import Notification

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable thresholds (can also be moved to Django settings)
# ---------------------------------------------------------------------------
NO_SHOW_MINUTES = 30          # minutes after scheduled start before flagging no-show
REMINDER_1_HOURS = 24         # first reminder after student marks complete
REMINDER_2_HOURS = 40         # second reminder
AUTO_RELEASE_HOURS = 48       # auto-release deadline


class Command(BaseCommand):
    help = 'Process scheduled task lifecycle events (no-show, reminders, auto-release).'

    def handle(self, *args, **options):
        now = django_tz.now()
        self.stdout.write(f'[run_scheduled_tasks] Running at {now.isoformat()}')

        self._handle_no_shows(now)
        self._handle_reminders(now)
        self._handle_auto_release(now)
        self._handle_location_retention(now)
        self._handle_stale_broadcasts(now)

        self.stdout.write(self.style.SUCCESS('[run_scheduled_tasks] Done.'))

    # ----------------------------------------------------------------
    # 1. No-show detection
    # ----------------------------------------------------------------
    def _handle_no_shows(self, now):
        """
        Flag tasks where the student has no VERIFIED check-in within 30 min
        of scheduled start.  A check-in that was accepted but flagged
        (out-of-range / low accuracy) still started the task, so those tasks
        are InProgress and never reach this check.  Task must be Assigned.
        """
        from datetime import datetime, timezone as dt_tz

        assigned_tasks = Task.objects.filter(
            status='Assigned',
            is_deleted=False,
            scheduled_date__isnull=False,
            scheduled_time__isnull=False,
        ).select_related('assigned_student', 'household_owner')

        for task in assigned_tasks:
            scheduled_dt = datetime.combine(
                task.scheduled_date, task.scheduled_time
            ).replace(tzinfo=dt_tz.utc)

            # Only flag after the no-show window has passed
            cutoff = scheduled_dt + timedelta(minutes=NO_SHOW_MINUTES)
            if now < cutoff:
                continue

            # Check if the student has a VERIFIED check-in on record
            has_verified = CheckIn.objects.filter(
                task=task,
                student=task.assigned_student,
                result='VERIFIED',
                type__in=('ARRIVAL', 'START'),
            ).exists()
            if has_verified:
                continue  # verified arrival on record

            # Legacy fallback: pre-geolocation tasks used start_code_verified
            try:
                completion = task.completion
                if completion.start_code_verified:
                    continue  # student is present (legacy check-in)
            except TaskCompletion.DoesNotExist:
                pass  # no check-in record at all — definitely a no-show

            logger.info(f'No-show detected for Task #{task.id}')

            try:
                transition(task, 'NoShow', actor=None,
                           notes=f'No check-in {NO_SHOW_MINUTES} min after scheduled start.')
            except InvalidTransition:
                continue  # already transitioned by another process

            # Penalty for student
            student = task.assigned_student
            if student and hasattr(student, 'student_profile'):
                student.student_profile.record_cancellation()

            # Notify household
            Notification.send(
                recipient=task.household_owner,
                notification_type='no_show',
                title='Student did not show up',
                message=(
                    f'The student did not check in for "{task.title}" within '
                    f'{NO_SHOW_MINUTES} minutes of the scheduled start. '
                    f'You can claim a full refund or re-broadcast the task.'
                ),
                task_id=task.id,
            )
            if student:
                Notification.send(
                    recipient=student,
                    notification_type='no_show',
                    title='No-show recorded',
                    message=(
                        f'You did not check in for "{task.title}". '
                        f'A no-show has been recorded and your reliability score has been lowered.'
                    ),
                    task_id=task.id,
                )

            AuditLog.log(
                task=task, actor=None, action='transition',
                from_status='Assigned', to_status='NoShow',
                notes=f'Auto no-show flag after {NO_SHOW_MINUTES} min.',
            )
            self.stdout.write(f'  -> Task #{task.id}: flagged NO_SHOW')

    # ----------------------------------------------------------------
    # 2. Confirmation reminders
    # ----------------------------------------------------------------
    def _handle_reminders(self, now):
        """
        Send 24-hour and 40-hour reminders to the household for tasks awaiting confirmation.
        """
        awaiting = Task.objects.filter(
            status='AwaitingConfirmation',
            is_deleted=False,
            confirmation_deadline__isnull=False,
        ).select_related('household_owner', 'assigned_student')

        for task in awaiting:
            deadline = task.confirmation_deadline
            hours_remaining = (deadline - now).total_seconds() / 3600

            # 40h reminder: deadline is between 7h and 9h away
            # (meaning 40h have passed since student finished)
            hours_elapsed = AUTO_RELEASE_HOURS - hours_remaining

            if REMINDER_1_HOURS <= hours_elapsed < REMINDER_1_HOURS + 0.25:
                # 24-hour reminder window (fires once per ~15-min cron run)
                self._send_confirmation_reminder(task, hours_remaining, is_final=False)

            elif REMINDER_2_HOURS <= hours_elapsed < REMINDER_2_HOURS + 0.25:
                # 40-hour reminder — payment releases in ~8 hours
                self._send_confirmation_reminder(task, hours_remaining, is_final=True)

    def _send_confirmation_reminder(self, task, hours_remaining, is_final):
        urgency = 'URGENT: ' if is_final else ''
        Notification.send(
            recipient=task.household_owner,
            notification_type='confirmation_reminder',
            title=f'{urgency}Please confirm task completion',
            message=(
                f'{urgency}"{task.title}" is waiting for your confirmation. '
                f'Payment will be released to the student automatically in '
                f'{hours_remaining:.0f} hours if no action is taken. '
                f'If there is a problem, raise a dispute now.'
            ),
            task_id=task.id,
        )
        self.stdout.write(f'  -> Task #{task.id}: confirmation reminder sent ({hours_remaining:.1f}h remaining)')

    # ----------------------------------------------------------------
    # 3. Auto-release after 48 h
    # ----------------------------------------------------------------
    def _handle_auto_release(self, now):
        """
        Auto-release escrow for tasks where the confirmation deadline has passed
        and the household has not confirmed or raised a dispute.
        """
        overdue = Task.objects.filter(
            status='AwaitingConfirmation',
            is_deleted=False,
            confirmation_deadline__lt=now,
        ).select_related('household_owner', 'assigned_student')

        for task in overdue:
            logger.info(f'Auto-releasing escrow for Task #{task.id}')
            idem_key = uuid.uuid5(
                uuid.NAMESPACE_OID, f'auto-release-task-{task.id}'
            )

            try:
                transition(task, 'Completed', actor=None,
                           notes='Auto-released after 48h confirmation window.')
            except InvalidTransition:
                continue

            ok, msg, _ = refund_service.release_to_student(
                task, actor=None, idempotency_key=idem_key
            )

            if ok:
                # Notify both parties
                Notification.send(
                    recipient=task.household_owner,
                    notification_type='auto_released',
                    title='Payment auto-released',
                    message=(
                        f'The 48-hour confirmation window for "{task.title}" has passed. '
                        f'Payment has been automatically released to the student.'
                    ),
                    task_id=task.id,
                )
                if task.assigned_student:
                    Notification.send(
                        recipient=task.assigned_student,
                        notification_type='auto_released',
                        title='Payment released! 💰',
                        message=(
                            f'Your payment for "{task.title}" has been automatically '
                            f'released after the 48-hour window.'
                        ),
                        task_id=task.id,
                    )
                AuditLog.log(
                    task=task, actor=None, action='payment_event',
                    notes='Auto-release after 48h timeout.',
                )
                self.stdout.write(f'  -> Task #{task.id}: auto-released')
            else:
                self.stdout.write(
                    self.style.WARNING(f'  -> Task #{task.id}: auto-release FAILED: {msg}')
                )

    # ----------------------------------------------------------------
    # 4. Location retention (privacy)
    # ----------------------------------------------------------------
    def _handle_location_retention(self, now):
        """
        Anonymise check-in coordinates older than LocationPolicy.retention_days
        (default 90 days).  Rows are kept for financial/audit integrity — only
        the position fields are nulled.  Check-ins on tasks with an OPEN
        dispute are retained until the dispute is resolved.

        Also clears the legacy TaskCompletion.checkin_lat/lng columns.
        """
        policy = LocationPolicy.get()
        cutoff = now - timedelta(days=policy.retention_days)

        stale = CheckIn.objects.filter(
            server_time__lt=cutoff,
            anonymised_at__isnull=True,
        ).exclude(lat__isnull=True, lng__isnull=True).select_related('task')

        anonymised = 0
        for checkin in stale:
            has_open_dispute = Dispute.objects.filter(
                task=checkin.task, resolved_at__isnull=True
            ).exists()
            if has_open_dispute:
                continue  # keep coordinates while a dispute is open

            checkin.lat = None
            checkin.lng = None
            checkin.accuracy_m = None
            checkin.anonymised_at = now
            checkin.save(update_fields=['lat', 'lng', 'accuracy_m', 'anonymised_at'])
            anonymised += 1

        # Legacy columns on TaskCompletion
        legacy = TaskCompletion.objects.filter(
            started_at__lt=cutoff,
        ).exclude(checkin_lat__isnull=True, checkin_lng__isnull=True)
        legacy.update(checkin_lat=None, checkin_lng=None)

        if anonymised:
            self.stdout.write(f'  -> {anonymised} check-in location(s) anonymised (retention {policy.retention_days}d)')

    # ----------------------------------------------------------------
    # 5. Stale broadcast refresh
    # ----------------------------------------------------------------
    def _handle_stale_broadcasts(self, now):
        """
        Re-broadcast tasks that are stuck in Broadcasting or Posted with no
        active requests — happens when the server restarts and daemon timers
        are lost, or when all round-1/2 requests expired with no acceptance.

        Skips students who declined or ignored. Re-opens expired requests.
        """
        from tasks.matching import rebroadcast_to_remaining
        from tasks.models import TaskRequest

        stale = Task.objects.filter(
            status__in=['Broadcasting', 'Posted'],
            is_deleted=False,
        )

        for task in stale:
            # Check if there are any still-open (SENT/VIEWED) requests
            open_reqs = TaskRequest.objects.filter(
                task=task, status__in=['SENT', 'VIEWED']
            ).count()

            if open_reqs > 0:
                continue  # still has active requests — not stale

            reached = rebroadcast_to_remaining(task)
            if reached > 0:
                self.stdout.write(
                    f'  -> Task #{task.id} "{task.title}": re-broadcast to {reached} student(s)'
                )
            else:
                self.stdout.write(
                    f'  -> Task #{task.id} "{task.title}": no new eligible students found'
                )
