"""
Tests for the new features:
  - Completion verification (start code, check-in, timestamps)
  - No-show detection
  - Cancellation policy (timing tiers)
  - Student cancellation (full refund + reliability penalty)
  - Disputes (raise, respond, admin resolve)
  - Double-refund idempotency
  - Auto-release (48h scheduled job)
  - Task deletion rules (funded/blocked statuses)
  - Wrong-user access
  - Ledger entries
  - State machine guards
"""

from datetime import date, time as dtime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import uuid

from django.utils import timezone as django_tz
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from users.models import CustomUser
from tasks.models import (
    PriceGuide, Task, TaskRequest, TaskCompletion,
    Dispute, CancellationPolicy, AuditLog,
)
from payments.models import Transaction, TransactionLedger
from tasks.matching import broadcast_task, accept_task_request
from tasks.task_transitions import transition, InvalidTransition
from tasks.management.commands.run_scheduled_tasks import Command as ScheduledCmd
from payments.refund_service import release_to_student, refund_to_household


# ---------------------------------------------------------------------------
# Always mock background threads to prevent daemon threads hanging test runner
# ---------------------------------------------------------------------------
_thread_patcher = patch('tasks.views.threading.Thread')
_matching_thread_patcher = patch('tasks.matching.threading.Thread')
_matching_timer_patcher = patch('tasks.matching.threading.Timer')
_matching_schedule_patcher = patch('tasks.matching._schedule_next_round')


def setUpModule():
    _thread_patcher.start()
    _matching_thread_patcher.start()
    _matching_timer_patcher.start()
    _matching_schedule_patcher.start()


def tearDownModule():
    _thread_patcher.stop()
    _matching_thread_patcher.stop()
    _matching_timer_patcher.stop()
    _matching_schedule_patcher.stop()


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class FeatureTestBase(APITestCase):
    """Creates one household, one student, and an optional PriceGuide."""

    def setUp(self):
        PriceGuide.objects.create(
            category='Cleaning', min_price=300, max_price=800, recommended_price=500
        )
        self.household = CustomUser.objects.create_user(
            username='hh_test', email='hh@test.com', password='Pass1234!',
            role='HOUSEHOLD', phone_number='254711000111',
        )
        hp = self.household.household_profile
        hp.location_lat = -1.2921
        hp.location_lng = 36.7856
        hp.verification_status = 'Verified'
        hp.save()
        self.hh_token = Token.objects.create(user=self.household).key

        self.student = CustomUser.objects.create_user(
            username='st_test', email='st@test.com', password='Pass1234!',
            role='STUDENT', phone_number='254722000222',
        )
        sp = self.student.student_profile
        sp.verification_status = 'Verified'
        sp.categories_offered = ['Cleaning']
        sp.location_lat = -1.2921
        sp.location_lng = 36.7856
        sp.save()
        self.st_token = Token.objects.create(user=self.student).key

        self.admin = CustomUser.objects.create_user(
            username='admin_test', email='admin@test.com', password='Pass1234!',
            role='ADMIN',
        )
        self.admin_token = Token.objects.create(user=self.admin).key

    def _make_task(self, status='Assigned', scheduled_date=None, scheduled_time=None):
        """Create a task in the given status with escrow Held."""
        task = Task.objects.create(
            household_owner=self.household,
            assigned_student=self.student,
            title='Test Cleaning',
            description='Test',
            category='Cleaning',
            posted_price=500,
            location_address='123 Test St, Kilimani, Nairobi',
            location_lat=-1.2921,
            location_lng=36.7856,
            status=status,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
        )
        # Create held escrow
        Transaction.objects.create(
            task=task, amount=500, status='Held',
            mpesa_reference='MOCK_REF', checkout_request_id='MOCK_CID',
            phone_number='254711000111',
        )
        return task

    def _make_assigned_task_with_completion(self):
        """Create an Assigned task that also has a TaskCompletion (start code) and consent."""
        task = self._make_task(status='Assigned')
        TaskCompletion.objects.create(task=task, start_code='1234')
        # Grant location consent so the checkin endpoint doesn't return 403
        from tasks.models import LocationConsent
        from tasks.geo import LOCATION_CONSENT_VERSION
        LocationConsent.objects.get_or_create(
            student=self.student,
            defaults={'version': LOCATION_CONSENT_VERSION},
        )
        return task


# ===========================================================================
# 1. COMPLETION VERIFICATION — Start code & check-in
# ===========================================================================

class TestStartCode(FeatureTestBase):

    def test_household_can_view_start_code_when_assigned(self):
        task = self._make_assigned_task_with_completion()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/tasks/{task.id}/start-code/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['start_code'], '1234')

    def test_student_cannot_view_start_code(self):
        task = self._make_assigned_task_with_completion()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.get(f'/api/tasks/{task.id}/start-code/')
        self.assertEqual(res.status_code, 403)

    def test_start_code_not_visible_before_assigned(self):
        task = self._make_task(status='Posted')
        TaskCompletion.objects.create(task=task, start_code='9999')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/tasks/{task.id}/start-code/')
        self.assertEqual(res.status_code, 400)

    def test_student_checkin_with_correct_code_moves_to_inprogress(self):
        task = self._make_assigned_task_with_completion()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/checkin/',
                               {'start_code': '1234',
                                'lat': '-1.2921', 'lng': '36.7856',
                                'accuracy_m': 10.0}, format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        completion = task.completion
        self.assertTrue(completion.start_code_verified)
        self.assertIsNotNone(completion.arrived_at)
        self.assertIsNotNone(completion.started_at)

    def test_student_checkin_with_wrong_code_rejected(self):
        task = self._make_assigned_task_with_completion()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/checkin/',
                               {'start_code': '0000',
                                'lat': '-1.2921', 'lng': '36.7856',
                                'accuracy_m': 10.0}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Incorrect', res.data['error'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')  # unchanged

    def test_checkin_records_gps_coordinates(self):
        task = self._make_assigned_task_with_completion()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/checkin/',
                               {'start_code': '1234', 'lat': '-1.2921', 'lng': '36.7856',
                                'accuracy_m': 10.0},
                               format='json')
        self.assertEqual(res.status_code, 200)
        completion = task.completion
        completion.refresh_from_db()
        self.assertIsNotNone(completion.checkin_lat)

    def test_wrong_student_cannot_checkin(self):
        task = self._make_assigned_task_with_completion()
        other = CustomUser.objects.create_user(
            username='other_st', email='other@test.com', password='Pass1234!',
            role='STUDENT',
        )
        other_token = Token.objects.create(user=other).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token}')
        res = self.client.post(f'/api/tasks/{task.id}/checkin/',
                               {'start_code': '1234'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_student_marks_complete_moves_to_awaiting_confirmation(self):
        task = self._make_task(status='InProgress')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/student-complete/', format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'AwaitingConfirmation')
        self.assertIsNotNone(task.confirmation_deadline)

        completion = task.completion
        self.assertIsNotNone(completion.finished_at)

    def test_household_confirms_completion_releases_escrow(self):
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() + timedelta(hours=24)
        task.save()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/confirm-completion/', format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Completed')
        # Escrow should be Released
        task.escrow_transaction.refresh_from_db()
        self.assertEqual(task.escrow_transaction.status, 'Released')

    def test_household_confirmation_creates_ledger_release_entry(self):
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() + timedelta(hours=24)
        task.save()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        self.client.post(f'/api/tasks/{task.id}/confirm-completion/', format='json')
        self.assertTrue(
            TransactionLedger.objects.filter(task=task, transaction_type='RELEASE').exists()
        )

    def test_audit_log_records_every_transition(self):
        task = self._make_task(status='InProgress')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        self.client.post(f'/api/tasks/{task.id}/student-complete/', format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        task.refresh_from_db()
        task.confirmation_deadline = django_tz.now() + timedelta(hours=24)
        task.save()
        self.client.post(f'/api/tasks/{task.id}/confirm-completion/', format='json')

        logs = AuditLog.objects.filter(task=task).values_list('from_status', 'to_status')
        transitions = list(logs)
        self.assertIn(('InProgress', 'AwaitingConfirmation'), transitions)
        self.assertIn(('AwaitingConfirmation', 'Completed'), transitions)


# ===========================================================================
# 2. NO-SHOW DETECTION
# ===========================================================================

class TestNoShow(FeatureTestBase):

    def test_no_show_flagged_when_student_does_not_check_in(self):
        """ScheduledCmd should flag no-show 30 min after scheduled start."""
        past_time = (django_tz.now() - timedelta(minutes=35)).time()
        past_date = django_tz.now().date()
        task = self._make_task(
            status='Assigned',
            scheduled_date=past_date,
            scheduled_time=past_time,
        )
        # No TaskCompletion (no check-in)

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_no_shows(django_tz.now())

        task.refresh_from_db()
        self.assertEqual(task.status, 'NoShow')

        # Student reliability should be penalised
        self.student.student_profile.refresh_from_db()
        self.assertLess(self.student.student_profile.reliability_score, 1.0)

    def test_no_show_not_flagged_before_window(self):
        """Do not flag if the window hasn't passed yet."""
        future_time = (django_tz.now() + timedelta(minutes=5)).time()
        task = self._make_task(
            status='Assigned',
            scheduled_date=django_tz.now().date(),
            scheduled_time=future_time,
        )
        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_no_shows(django_tz.now())
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')  # unchanged

    def test_no_show_not_flagged_if_student_checked_in(self):
        """Don't flag if the student already verified the start code."""
        past_time = (django_tz.now() - timedelta(minutes=40)).time()
        task = self._make_task(
            status='InProgress',  # already in progress = checked in
            scheduled_date=django_tz.now().date(),
            scheduled_time=past_time,
        )
        TaskCompletion.objects.create(task=task, start_code='1234', start_code_verified=True)
        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_no_shows(django_tz.now())
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')  # unchanged


# ===========================================================================
# 3. CANCELLATION POLICY — timing tiers
# ===========================================================================

class TestCancellationPolicy(FeatureTestBase):

    def test_cancellation_free_before_payment(self):
        """Cancelling a Posted task has no charge."""
        task = Task.objects.create(
            household_owner=self.household,
            title='Free Cancel', description='test', category='Cleaning',
            posted_price=500, status='Posted',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel/', format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Cancelled')
        self.assertEqual(res.data['refund_amount'], 0)

    def test_cancellation_full_refund_gt_free_hours(self):
        """Household cancels Assigned task >24h before scheduled start → full refund."""
        future_date = (django_tz.now() + timedelta(hours=36)).date()
        future_time = (django_tz.now() + timedelta(hours=36)).time()
        task = self._make_task(
            status='Assigned',
            scheduled_date=future_date,
            scheduled_time=future_time,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel/', format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Full refund', res.data['message'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'Cancelled')
        self.assertTrue(
            TransactionLedger.objects.filter(task=task, transaction_type='REFUND').exists()
        )

    def test_cancellation_partial_refund_lt_free_hours(self):
        """Household cancels Assigned task <24h before scheduled start → partial refund."""
        near_date = (django_tz.now() + timedelta(hours=10)).date()
        near_time = (django_tz.now() + timedelta(hours=10)).time()
        task = self._make_task(
            status='Assigned',
            scheduled_date=near_date,
            scheduled_time=near_time,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel/', format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Partial refund', res.data['message'])
        # 80% of 500 = 400
        self.assertEqual(Decimal(res.data['refund_amount']), Decimal('400.00'))
        self.assertTrue(
            TransactionLedger.objects.filter(task=task, transaction_type='PARTIAL_REFUND').exists()
        )

    def test_cancellation_blocked_in_progress(self):
        """Cannot cancel an InProgress task."""
        task = self._make_task(status='InProgress')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel/', format='json')
        self.assertEqual(res.status_code, 400)

    def test_cancellation_blocked_disputed(self):
        task = self._make_task(status='Disputed')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel/', format='json')
        self.assertEqual(res.status_code, 400)

    def test_student_cancel_full_refund_and_reliability_penalty(self):
        """Student cancels → full refund + reliability lowered."""
        task = self._make_task(status='Assigned')
        initial_reliability = self.student.student_profile.reliability_score
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/student-cancel/', format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Reopened')
        self.assertIsNone(task.assigned_student)

        self.student.student_profile.refresh_from_db()
        self.assertLess(self.student.student_profile.reliability_score, initial_reliability)
        self.assertEqual(self.student.student_profile.cancellation_count, 1)

        # Escrow should be refunded
        task.escrow_transaction.refresh_from_db()
        self.assertEqual(task.escrow_transaction.status, 'Refunded')
        self.assertTrue(
            TransactionLedger.objects.filter(task=task, transaction_type='REFUND').exists()
        )

    def test_cancellation_policy_configurable(self):
        """Admin can update the cancellation policy."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.patch('/api/cancellation-policy/',
                                {'free_before_hours': 48, 'partial_refund_pct': 70},
                                format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['free_before_hours'], 48)
        self.assertEqual(res.data['partial_refund_pct'], 70)

    def test_non_admin_cannot_update_policy(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.patch('/api/cancellation-policy/',
                                {'free_before_hours': 1}, format='json')
        self.assertEqual(res.status_code, 403)


# ===========================================================================
# 4. DISPUTES
# ===========================================================================

class TestDisputes(FeatureTestBase):

    def _make_awaiting_task(self):
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() + timedelta(hours=24)
        task.save()
        return task

    def test_household_raises_dispute(self):
        task = self._make_awaiting_task()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute/',
                               {'reason': 'poor_quality', 'description': 'Work was not done properly.'},
                               format='json')
        self.assertEqual(res.status_code, 201)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Disputed')
        self.assertTrue(Dispute.objects.filter(task=task).exists())

    def test_one_dispute_per_task(self):
        task = self._make_awaiting_task()
        # Pre-create a dispute AND keep the task in AwaitingConfirmation so the
        # status guard passes; only the duplicate guard should fire.
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='First dispute.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute/',
                               {'reason': 'other', 'description': 'Second attempt.'},
                               format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('already been raised', res.data['error'])

    def test_student_cannot_raise_dispute(self):
        task = self._make_awaiting_task()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute/',
                               {'reason': 'poor_quality', 'description': 'Test.'},
                               format='json')
        self.assertEqual(res.status_code, 403)

    def test_dispute_requires_reason_and_description(self):
        task = self._make_awaiting_task()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute/',
                               {'reason': 'poor_quality'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_student_can_respond_to_dispute(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='Not done.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute-response/',
                               {'response': 'I completed the work as agreed.'}, format='json')
        self.assertEqual(res.status_code, 200)
        dispute = Dispute.objects.get(task=task)
        self.assertIsNotNone(dispute.student_responded_at)
        self.assertEqual(dispute.student_response, 'I completed the work as agreed.')

    def test_student_cannot_respond_twice(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(
            task=task, raised_by=self.household,
            reason='poor_quality', description='Not done.',
            student_response='Already responded.',
            student_responded_at=django_tz.now(),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute-response/',
                               {'response': 'Trying again.'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_admin_resolves_full_refund(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='did_not_show', description='No show.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute-resolve/',
                               {'outcome': 'full_refund', 'admin_notes': 'No evidence of work.'},
                               format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Cancelled')
        task.escrow_transaction.refresh_from_db()
        self.assertEqual(task.escrow_transaction.status, 'Refunded')
        self.assertTrue(
            TransactionLedger.objects.filter(task=task, transaction_type='REFUND').exists()
        )

    def test_admin_resolves_release_to_student(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='Minor issue.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute-resolve/',
                               {'outcome': 'release', 'admin_notes': 'Work completed.'},
                               format='json')
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Completed')
        task.escrow_transaction.refresh_from_db()
        self.assertEqual(task.escrow_transaction.status, 'Released')

    def test_non_admin_cannot_resolve_dispute(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='Test.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute-resolve/',
                               {'outcome': 'full_refund'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_dispute_detail_accessible_to_parties(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='Test.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/tasks/{task.id}/dispute-detail/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['reason'], 'poor_quality')

    def test_dispute_detail_blocked_for_third_party(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='Test.')
        other = CustomUser.objects.create_user(
            username='third_party', email='tp@test.com', password='Pass1234!', role='HOUSEHOLD',
        )
        other_token = Token.objects.create(user=other).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token}')
        res = self.client.get(f'/api/tasks/{task.id}/dispute-detail/')
        self.assertEqual(res.status_code, 403)


# ===========================================================================
# 5. DOUBLE-REFUND IDEMPOTENCY
# ===========================================================================

class TestIdempotency(FeatureTestBase):

    def test_double_refund_is_idempotent(self):
        """Calling refund_to_household twice with the same idempotency key
        returns the existing entry without creating a duplicate."""
        task = self._make_task(status='Assigned')
        idem_key = uuid.uuid4()

        ok1, msg1, entry1 = refund_to_household(task, actor=self.household,
                                                idempotency_key=idem_key,
                                                notes='First call')
        self.assertTrue(ok1)

        # Revert escrow status so second call would succeed if not for idempotency
        # (escrow is now Refunded from the first call — the idempotency guard fires before
        # the escrow check on a second call with same key)
        ok2, msg2, entry2 = refund_to_household(task, actor=self.household,
                                                idempotency_key=idem_key,
                                                notes='Second call (should be no-op)')
        self.assertTrue(ok2)
        self.assertIn('idempotent', msg2.lower())

        # Only one ledger entry should exist for this key
        count = TransactionLedger.objects.filter(idempotency_key=idem_key).count()
        self.assertEqual(count, 1)

    def test_double_release_is_idempotent(self):
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() + timedelta(hours=10)
        task.save()
        idem_key = uuid.uuid4()

        ok1, _, entry1 = release_to_student(task, actor=self.household,
                                            idempotency_key=idem_key)
        self.assertTrue(ok1)

        ok2, msg2, entry2 = release_to_student(task, actor=self.household,
                                               idempotency_key=idem_key)
        self.assertTrue(ok2)
        self.assertIn('idempotent', msg2.lower())

        count = TransactionLedger.objects.filter(idempotency_key=idem_key).count()
        self.assertEqual(count, 1)


# ===========================================================================
# 6. AUTO-RELEASE (48h scheduled job)
# ===========================================================================

class TestAutoRelease(FeatureTestBase):

    def test_auto_release_completes_overdue_awaiting_confirmation(self):
        """ScheduledCmd should release payment for overdue AwaitingConfirmation tasks."""
        task = self._make_task(status='AwaitingConfirmation')
        # Set deadline in the past
        task.confirmation_deadline = django_tz.now() - timedelta(hours=1)
        task.save()

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_auto_release(django_tz.now())

        task.refresh_from_db()
        self.assertEqual(task.status, 'Completed')
        task.escrow_transaction.refresh_from_db()
        self.assertEqual(task.escrow_transaction.status, 'Released')
        self.assertTrue(
            TransactionLedger.objects.filter(task=task, transaction_type='RELEASE').exists()
        )

    def test_auto_release_does_not_affect_non_overdue(self):
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() + timedelta(hours=10)
        task.save()

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_auto_release(django_tz.now())

        task.refresh_from_db()
        self.assertEqual(task.status, 'AwaitingConfirmation')  # unchanged

    def test_auto_release_is_idempotent_via_uuid5(self):
        """Running auto-release twice on same task should not double-release."""
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() - timedelta(hours=1)
        task.save()

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_auto_release(django_tz.now())
        # Second run: task is now Completed — transition guard blocks it
        cmd._handle_auto_release(django_tz.now())

        count = TransactionLedger.objects.filter(
            task=task, transaction_type='RELEASE'
        ).count()
        self.assertEqual(count, 1)


# ===========================================================================
# 7. TASK DELETION / REMOVAL
# ===========================================================================

class TestTaskRemoval(FeatureTestBase):

    def test_household_can_soft_delete_posted_task(self):
        task = Task.objects.create(
            household_owner=self.household, assigned_student=None,
            title='Delete Me', description='test', category='Cleaning',
            posted_price=500, status='Posted',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 204)
        task.refresh_from_db()
        self.assertTrue(task.is_deleted)
        self.assertIsNotNone(task.deleted_at)

    def test_soft_deleted_task_not_in_list(self):
        task = Task.objects.create(
            household_owner=self.household, assigned_student=None,
            title='Invisible', description='test', category='Cleaning',
            posted_price=500, status='Posted', is_deleted=True,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get('/api/tasks/?my_tasks=true')
        ids = [t['id'] for t in res.data]
        self.assertNotIn(task.id, ids)

    def test_cannot_delete_funded_task(self):
        """Deleting a task with Held escrow must be blocked (via CANCEL_REQUIRED_STATUSES)."""
        task = self._make_task(status='Assigned')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 400)
        # Either 'escrow' (pure escrow check) or 'cancel' (assigned student path) must appear
        error_lower = res.data['error'].lower()
        self.assertTrue(
            'escrow' in error_lower or 'cancel' in error_lower,
            f"Expected 'escrow' or 'cancel' in: {error_lower}"
        )
        task.refresh_from_db()
        self.assertFalse(task.is_deleted)

    def test_cannot_delete_inprogress_task(self):
        task = self._make_task(status='InProgress')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('InProgress', res.data['status'])

    def test_cannot_delete_awaiting_confirmation_task(self):
        task = self._make_task(status='AwaitingConfirmation')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 400)

    def test_cannot_delete_completed_task(self):
        task = self._make_task(status='Completed')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 400)

    def test_cannot_delete_disputed_task(self):
        task = self._make_task(status='Disputed')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 400)

    def test_other_user_cannot_delete_task(self):
        task = Task.objects.create(
            household_owner=self.household, assigned_student=None,
            title='Not Mine', description='test', category='Cleaning',
            posted_price=500, status='Posted',
        )
        other = CustomUser.objects.create_user(
            username='other_hh', email='otherhh@test.com', password='Pass1234!',
            role='HOUSEHOLD',
        )
        other_token = Token.objects.create(user=other).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 403)
        task.refresh_from_db()
        self.assertFalse(task.is_deleted)

    def test_delete_withdraws_pending_requests_and_notifies(self):
        task = Task.objects.create(
            household_owner=self.household, assigned_student=None,
            title='Withdraw Test', description='test', category='Cleaning',
            posted_price=500, status='Broadcasting',
        )
        TaskRequest.objects.create(task=task, student=self.student, status='SENT')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        self.client.delete(f'/api/tasks/{task.id}/')

        req = TaskRequest.objects.get(task=task, student=self.student)
        self.assertEqual(req.status, 'EXPIRED')

        from users.models import Notification
        notif = Notification.objects.filter(
            recipient=self.student, notification_type='task_deleted'
        ).first()
        self.assertIsNotNone(notif)

    def test_assigned_task_requires_cancel_not_delete(self):
        """Assigned tasks (no escrow yet) should redirect to cancel path."""
        task = Task.objects.create(
            household_owner=self.household, assigned_student=self.student,
            title='Assigned No Pay', description='test', category='Cleaning',
            posted_price=500, status='Assigned',
        )
        # No escrow — but status is Assigned which is in CANCEL_REQUIRED_STATUSES
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.delete(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cancel', res.data['error'].lower())


# ===========================================================================
# 8. WRONG-USER ACCESS
# ===========================================================================

class TestWrongUserAccess(FeatureTestBase):

    def test_student_cannot_confirm_completion(self):
        task = self._make_task(status='AwaitingConfirmation')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/confirm-completion/', format='json')
        self.assertEqual(res.status_code, 403)

    def test_household_cannot_checkin(self):
        task = self._make_assigned_task_with_completion()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/checkin/',
                               {'start_code': '1234'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_household_cannot_respond_to_dispute(self):
        task = self._make_task(status='Disputed')
        Dispute.objects.create(task=task, raised_by=self.household,
                               reason='poor_quality', description='Test.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post(f'/api/tasks/{task.id}/dispute-response/',
                               {'response': 'I am the household.'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_student_cannot_cancel_household_task(self):
        task = Task.objects.create(
            household_owner=self.household, assigned_student=None,
            title='Not Mine', description='test', category='Cleaning',
            posted_price=500, status='Posted',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel/', format='json')
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_user_cannot_access_task(self):
        task = self._make_task(status='Assigned')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 401)


# ===========================================================================
# 9. STATE MACHINE GUARDS
# ===========================================================================

class TestStateMachine(FeatureTestBase):

    def test_invalid_transition_raises(self):
        task = self._make_task(status='Completed')
        with self.assertRaises(InvalidTransition):
            transition(task, 'InProgress')

    def test_valid_transition_saves_and_logs(self):
        task = self._make_task(status='InProgress')
        transition(task, 'AwaitingConfirmation', actor=self.student, notes='Test')
        task.refresh_from_db()
        self.assertEqual(task.status, 'AwaitingConfirmation')
        log = AuditLog.objects.filter(task=task, to_status='AwaitingConfirmation').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.student)

    def test_state_machine_blocks_direct_assigned_to_completed(self):
        """Cannot skip AwaitingConfirmation → Completed directly from Assigned."""
        task = self._make_task(status='Assigned')
        with self.assertRaises(InvalidTransition):
            transition(task, 'Completed')


# ===========================================================================
# 10. LEDGER COMPLETENESS
# ===========================================================================

class TestLedger(FeatureTestBase):

    def test_ledger_entries_visible_to_household(self):
        task = self._make_task(status='AwaitingConfirmation')
        task.confirmation_deadline = django_tz.now() + timedelta(hours=10)
        task.save()
        # Create a release ledger entry
        TransactionLedger.record(task=task, transaction_type='HOLD', amount=500,
                                 actor=self.household, notes='Test hold.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/tasks/{task.id}/ledger/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['transaction_type'], 'HOLD')

    def test_ledger_not_visible_to_student(self):
        task = self._make_task(status='Assigned')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.get(f'/api/tasks/{task.id}/ledger/')
        self.assertEqual(res.status_code, 403)

    def test_ledger_entries_never_deleted(self):
        """Soft-deleting the task should not destroy ledger entries."""
        task = Task.objects.create(
            household_owner=self.household, assigned_student=None,
            title='Ledger Test', description='test', category='Cleaning',
            posted_price=500, status='Posted',
        )
        TransactionLedger.record(task=task, transaction_type='HOLD', amount=0,
                                 notes='Pre-delete entry.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        self.client.delete(f'/api/tasks/{task.id}/')
        # Ledger entries must still exist
        self.assertEqual(TransactionLedger.objects.filter(task=task).count(), 1)
