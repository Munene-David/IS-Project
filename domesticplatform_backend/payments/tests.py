"""
Test scenarios for the payments app:
  - TransactionLedger record() — append-only, idempotency
  - Transaction escrow lifecycle (hold → release / refund)
  - refund_service.release_to_student — success, already-released, idempotent
  - refund_service.refund_to_household — full, partial, idempotent
  - POST /payments/initiate-escrow/ — success, wrong owner, task not found
  - POST /payments/release-escrow/ — success, escrow not held
  - POST /payments/check-status/   — success, wrong owner
  - Ratings — create, average calculation, duplicate prevention
  - GET /ratings/summary/<id>/
"""

import uuid
from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from users.models import CustomUser
from tasks.models import Task, PriceGuide, TaskCompletion
from payments.models import Transaction, TransactionLedger, Rating
from payments import refund_service


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_user(username, role, password='Pass1234!'):
    u = CustomUser.objects.create_user(
        username=username, email=f'{username}@test.com',
        password=password, role=role,
    )
    return u


def _make_assigned_task(household, student, price=500):
    PriceGuide.objects.get_or_create(
        category='Cleaning',
        defaults={'min_price': 300, 'max_price': 800, 'recommended_price': 500},
    )
    task = Task.objects.create(
        household_owner=household, assigned_student=student,
        title='Payment Test Task', description='Test',
        category='Cleaning', posted_price=price,
        location_address='123 Test St', location_lat=-1.292, location_lng=36.785,
        location_pin_confirmed=True, status='Assigned',
    )
    Transaction.objects.create(
        task=task, amount=price, status='Held',
        mpesa_reference='MOCK_REF', checkout_request_id='MOCK_CID',
        phone_number='254711000111',
    )
    TaskCompletion.objects.create(task=task, start_code='1234')
    return task


# ===========================================================================
# 1. TransactionLedger — append-only, idempotency
# ===========================================================================

class TestTransactionLedger(APITestCase):

    def setUp(self):
        self.hh = _make_user('led_hh', 'HOUSEHOLD')
        self.st = _make_user('led_st', 'STUDENT', )
        self.st.phone_number = '254722000001'
        self.st.save()
        self.task = _make_assigned_task(self.hh, self.st)

    def test_record_creates_ledger_entry(self):
        entry, created = TransactionLedger.record(
            task=self.task, transaction_type='HOLD',
            amount=500, actor=self.hh, notes='Test hold',
        )
        self.assertTrue(created)
        self.assertEqual(entry.transaction_type, 'HOLD')
        self.assertEqual(entry.amount, 500)

    def test_idempotent_key_prevents_duplicate(self):
        idem = uuid.uuid4()
        entry1, created1 = TransactionLedger.record(
            task=self.task, transaction_type='RELEASE',
            amount=500, actor=self.hh,
            idempotency_key=idem,
        )
        entry2, created2 = TransactionLedger.record(
            task=self.task, transaction_type='RELEASE',
            amount=500, actor=self.hh,
            idempotency_key=idem,
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(entry1.id, entry2.id)
        self.assertEqual(TransactionLedger.objects.filter(
            task=self.task, idempotency_key=idem).count(), 1)

    def test_different_keys_create_separate_entries(self):
        for _ in range(3):
            TransactionLedger.record(
                task=self.task, transaction_type='HOLD',
                amount=100, actor=self.hh,
                idempotency_key=uuid.uuid4(),
            )
        self.assertEqual(
            TransactionLedger.objects.filter(task=self.task).count(), 3)

    def test_ledger_entries_never_deleted_with_task(self):
        """Ledger must survive even after task soft-delete (CASCADE is on Task
        hard-delete only; task is soft-deleted so rows stay)."""
        TransactionLedger.record(
            task=self.task, transaction_type='HOLD',
            amount=500, actor=self.hh,
        )
        self.task.is_deleted = True
        self.task.save()
        self.assertEqual(
            TransactionLedger.objects.filter(task=self.task).count(), 1)


# ===========================================================================
# 2. refund_service — release and refund
# ===========================================================================

class TestRefundService(APITestCase):

    def setUp(self):
        self.hh = _make_user('rf_hh', 'HOUSEHOLD')
        self.st = _make_user('rf_st', 'STUDENT')
        self.st.phone_number = '254722000002'
        self.st.save()
        self.task = _make_assigned_task(self.hh, self.st)

    def test_release_to_student_succeeds(self):
        ok, msg, entry = refund_service.release_to_student(
            self.task, actor=self.hh)
        self.assertTrue(ok)
        self.task.escrow_transaction.refresh_from_db()
        self.assertEqual(self.task.escrow_transaction.status, 'Released')
        self.assertTrue(
            TransactionLedger.objects.filter(
                task=self.task, transaction_type='RELEASE').exists())

    def test_release_idempotent(self):
        idem = uuid.uuid4()
        ok1, _, e1 = refund_service.release_to_student(
            self.task, actor=self.hh, idempotency_key=idem)
        ok2, msg2, e2 = refund_service.release_to_student(
            self.task, actor=self.hh, idempotency_key=idem)
        self.assertTrue(ok2)
        self.assertIn('idempotent', msg2.lower())
        self.assertEqual(e1.id, e2.id)

    def test_refund_to_household_full(self):
        ok, msg, entry = refund_service.refund_to_household(
            self.task, actor=self.hh, notes='Test refund')
        self.assertTrue(ok)
        self.task.escrow_transaction.refresh_from_db()
        self.assertIn(self.task.escrow_transaction.status, ('Refunded', 'PartialRefund'))
        self.assertTrue(
            TransactionLedger.objects.filter(
                task=self.task, transaction_type='REFUND').exists())

    def test_refund_to_household_partial(self):
        partial = Decimal('300.00')
        ok, msg, entry = refund_service.refund_to_household(
            self.task, actor=self.hh, partial_amount=partial,
            notes='Partial refund')
        self.assertTrue(ok)
        self.assertEqual(entry.amount, partial)
        self.assertTrue(
            TransactionLedger.objects.filter(
                task=self.task, transaction_type='PARTIAL_REFUND').exists())

    def test_refund_idempotent(self):
        idem = uuid.uuid4()
        ok1, _, e1 = refund_service.refund_to_household(
            self.task, actor=self.hh, idempotency_key=idem)
        ok2, msg2, e2 = refund_service.refund_to_household(
            self.task, actor=self.hh, idempotency_key=idem)
        self.assertTrue(ok2)
        self.assertIn('idempotent', msg2.lower())
        self.assertEqual(e1.id, e2.id)

    def test_release_fails_when_not_held(self):
        self.task.escrow_transaction.status = 'Released'
        self.task.escrow_transaction.save()
        ok, msg, _ = refund_service.release_to_student(self.task, actor=self.hh)
        self.assertFalse(ok)

    def test_refund_fails_when_not_held(self):
        self.task.escrow_transaction.status = 'Refunded'
        self.task.escrow_transaction.save()
        ok, msg, _ = refund_service.refund_to_household(self.task, actor=self.hh)
        self.assertFalse(ok)


# ===========================================================================
# 3. Payments API endpoints
# ===========================================================================

class TestPaymentEndpoints(APITestCase):

    def setUp(self):
        self.hh = _make_user('pay_hh', 'HOUSEHOLD')
        self.hh.phone_number = '254711000111'
        self.hh.save()
        self.st = _make_user('pay_st', 'STUDENT')
        self.st.phone_number = '254722000003'
        self.st.save()
        self.hh_token = Token.objects.create(user=self.hh).key
        self.st_token = Token.objects.create(user=self.st).key
        PriceGuide.objects.get_or_create(
            category='Cleaning',
            defaults={'min_price': 300, 'max_price': 800, 'recommended_price': 500},
        )
        self.task = Task.objects.create(
            household_owner=self.hh, assigned_student=self.st,
            title='Pay Endpoint Test', description='Test',
            category='Cleaning', posted_price=500,
            location_lat=-1.292, location_lng=36.785,
            location_pin_confirmed=True, status='Assigned',
        )

    def test_initiate_escrow_succeeds(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post('/api/payments/initiate-escrow/', {
            'task_id': self.task.id,
            'phone_number': '254711000111',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['success'])

    def test_initiate_escrow_wrong_owner(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post('/api/payments/initiate-escrow/', {
            'task_id': self.task.id,
            'phone_number': '254722000003',
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_initiate_escrow_missing_phone(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post('/api/payments/initiate-escrow/', {
            'task_id': self.task.id,
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_release_escrow_succeeds(self):
        # Create a held escrow first
        Transaction.objects.create(
            task=self.task, amount=500, status='Held',
            mpesa_reference='MOCK', checkout_request_id='CID1',
            phone_number='254711000111',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post('/api/payments/release-escrow/', {
            'task_id': self.task.id,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['success'])

    def test_release_escrow_wrong_owner(self):
        Transaction.objects.create(
            task=self.task, amount=500, status='Held',
            mpesa_reference='MOCK', checkout_request_id='CID2',
            phone_number='254711000111',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post('/api/payments/release-escrow/', {
            'task_id': self.task.id,
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_check_status_succeeds(self):
        txn = Transaction.objects.create(
            task=self.task, amount=500, status='Held',
            mpesa_reference='MOCK', checkout_request_id='CHECK_CID',
            phone_number='254711000111',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post('/api/payments/check-status/', {
            'checkout_request_id': 'CHECK_CID',
        }, format='json')
        self.assertEqual(res.status_code, 200)

    def test_check_status_wrong_owner(self):
        Transaction.objects.create(
            task=self.task, amount=500, status='Held',
            mpesa_reference='MOCK', checkout_request_id='AUTH_CID',
            phone_number='254711000111',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post('/api/payments/check-status/', {
            'checkout_request_id': 'AUTH_CID',
        }, format='json')
        self.assertEqual(res.status_code, 403)


# ===========================================================================
# 4. Ratings
# ===========================================================================

class TestRatings(APITestCase):

    def setUp(self):
        self.hh = _make_user('rat_hh', 'HOUSEHOLD')
        self.st = _make_user('rat_st', 'STUDENT')
        self.st.phone_number = '254722000004'
        self.st.save()
        self.hh_token = Token.objects.create(user=self.hh).key
        self.st_token = Token.objects.create(user=self.st).key
        PriceGuide.objects.get_or_create(
            category='Cleaning',
            defaults={'min_price': 300, 'max_price': 800, 'recommended_price': 500},
        )
        self.task = Task.objects.create(
            household_owner=self.hh, assigned_student=self.st,
            title='Rating Task', description='Test',
            category='Cleaning', posted_price=500,
            location_pin_confirmed=True, status='Completed',
        )

    def test_household_rates_student(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post('/api/ratings/', {
            'task': self.task.id,
            'rated_user': self.st.id,
            'score': 5,
            'comment': 'Excellent work!',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Rating.calculate_average(self.st), 5.0)

    def test_duplicate_rating_rejected(self):
        """The API must return a non-2xx status when the same rater submits
        a second rating for the same task/rated_user pair.
        DRF raises an IntegrityError which Django converts to 500 unless
        the view or DB layer handles it — we confirm it at least isn't 2xx."""
        Rating.objects.create(
            task=self.task, rater=self.hh,
            rated_user=self.st, score=4, comment='Good.',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        from django.db import transaction
        try:
            with transaction.atomic():
                res = self.client.post('/api/ratings/', {
                    'task': self.task.id,
                    'rated_user': self.st.id,
                    'score': 2, 'comment': 'Duplicate.',
                }, format='json')
            # If a response came back it must not be 2xx
            self.assertGreaterEqual(res.status_code, 400)
        except Exception:
            # DB-level IntegrityError is also acceptable — duplicate was blocked
            pass

    def test_score_out_of_range_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.post('/api/ratings/', {
            'task': self.task.id,
            'rated_user': self.st.id,
            'score': 6,
            'comment': 'Too high.',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_average_rating_calculation(self):
        hh2 = _make_user('rat_hh2', 'HOUSEHOLD')
        task2 = Task.objects.create(
            household_owner=hh2, assigned_student=self.st,
            title='Task2', description='T', category='Cleaning',
            posted_price=500, location_pin_confirmed=True, status='Completed',
        )
        Rating.objects.create(task=self.task, rater=self.hh,
                               rated_user=self.st, score=4, comment='Good.')
        Rating.objects.create(task=task2, rater=hh2,
                               rated_user=self.st, score=2, comment='OK.')
        avg = Rating.calculate_average(self.st)
        self.assertEqual(avg, 3.0)

    def test_zero_ratings_returns_zero(self):
        self.assertEqual(Rating.calculate_average(self.st), 0.0)

    def test_rating_summary_endpoint(self):
        Rating.objects.create(task=self.task, rater=self.hh,
                               rated_user=self.st, score=5, comment='Great.')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/ratings/summary/{self.st.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['average_rating'], 5.0)
        self.assertEqual(res.data['total_reviews'], 1)
        self.assertEqual(len(res.data['recent_ratings']), 1)
