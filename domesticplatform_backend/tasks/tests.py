from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from users.models import CustomUser
from tasks.models import PriceGuide, Task, TaskRequest
from payments.models import Transaction, Rating
from tasks.matching import find_eligible_students, broadcast_task, accept_task_request, household_cancel_match
from users.models import BlockedStudent
from unittest.mock import patch, MagicMock
import json
import unittest


class MarketplaceEndToEndTests(APITestCase):
    """End-to-end flow using the broadcast (query) matching system."""

    @patch('tasks.views.threading')
    def setUp(self, mock_threading):
        mock_threading.Thread.return_value = MagicMock()
        PriceGuide.objects.create(
            category='Cleaning', min_price=300, max_price=800, recommended_price=500
        )

        self.household_user = CustomUser.objects.create_user(
            username='sarah_m', email='sarah@example.com', password='Password123!',
            role='HOUSEHOLD', phone_number='254711000111',
        )
        hp = self.household_user.household_profile
        hp.location_lat = -1.2921
        hp.location_lng = 36.7856
        hp.verification_status = 'Verified'
        hp.save()
        self.household_token = Token.objects.create(user=self.household_user).key

        self.student_user = CustomUser.objects.create_user(
            username='jane_w', email='jane@uon.ac.ke', password='Password123!',
            role='STUDENT', phone_number='254722000222',
        )
        sp = self.student_user.student_profile
        sp.verification_status = 'Verified'
        sp.categories_offered = ['Cleaning']
        sp.location_lat = -1.2921
        sp.location_lng = 36.7856
        sp.save()
        self.student_token = Token.objects.create(user=self.student_user).key

    @patch('tasks.views.threading')
    def test_full_marketplace_workflow(self, mock_threading):
        mock_threading.Thread.return_value = MagicMock()

        # Step 1: Price guide check
        response = self.client.get('/api/price-guide/Cleaning/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['recommended_price']), 500.0)

        # Step 2: Household posts a task
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        create_res = self.client.post('/api/tasks/', {
            'title': 'Living Room Cleaning',
            'description': 'Deep clean living room and sofa',
            'category': 'Cleaning',
            'posted_price': '500.00',
            'location_address': 'Kilimani, Nairobi',
            'location_lat': '-1.292100',
            'location_lng': '36.785600',
            'location_landmark': 'Near Yaya Centre',
            'geofence_radius_m': 150,
            'location_pin_confirmed': True,
        }, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        task_id = create_res.data['id']

        # Step 3: Manually create the TaskRequest (broadcast ran in background thread which is mocked)
        task = Task.objects.get(id=task_id)
        task.status = 'Broadcasting'
        task.save()
        req = TaskRequest.objects.create(
            task=task, student=self.student_user, status='SENT', broadcast_round=1
        )

        # Step 4: Student views available requests
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        inbox_res = self.client.get('/api/tasks/my-requests/')
        self.assertEqual(inbox_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(inbox_res.data), 1)

        # Step 5: Student accepts the request (atomic first-to-accept)
        accept_res = self.client.post('/api/tasks/accept-request/', {'request_id': req.id}, format='json')
        self.assertEqual(accept_res.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Matched')

        # Step 6: Household confirms match and pays via M-Pesa
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        confirm_res = self.client.post(f'/api/tasks/{task_id}/confirm-match/',
                                       {'phone_number': '254711000111'}, format='json')
        self.assertEqual(confirm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_res.data['task_status'], 'Assigned')

        # Step 7: Household sends a chat message
        msg_res = self.client.post(f'/api/tasks/{task_id}/messages/',
                                   {'content': 'Hi Jane! Funds are secured. See you at 3pm!'}, format='json')
        self.assertEqual(msg_res.status_code, status.HTTP_201_CREATED)

        # Step 8: Student starts the task
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        start_res = self.client.post(f'/api/tasks/{task_id}/complete/', format='json')
        self.assertEqual(start_res.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        # Step 9: Household marks task complete (releases escrow)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        complete_res = self.client.post(f'/api/tasks/{task_id}/complete/', format='json')
        self.assertEqual(complete_res.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Completed')

        # Step 10: Rate the student
        rate_res = self.client.post('/api/ratings/', {
            'task': task_id, 'rated_user': self.student_user.id,
            'score': 5, 'comment': 'Fantastic — very punctual!',
        }, format='json')
        self.assertEqual(rate_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Rating.calculate_average(self.student_user), 5.0)


class BroadcastFlowTestBase(APITestCase):
    """Shared setup for all broadcast-flow tests."""

    def setUp(self):
        PriceGuide.objects.create(
            category='Cleaning', min_price=300, max_price=800, recommended_price=500
        )

        # Household with location
        self.household = CustomUser.objects.create_user(
            username='sarah_m', email='sarah@test.com', password='Pass1234!',
            role='HOUSEHOLD', phone_number='254711000111',
        )
        hp = self.household.household_profile
        hp.address = 'Kilimani, Nairobi'
        hp.location_lat = -1.2921
        hp.location_lng = 36.7856
        hp.verification_status = 'Verified'
        hp.min_rating = 0
        hp.search_radius_km = 5
        hp.save()
        self.household_token = Token.objects.create(user=self.household).key

        # Create 3 verified students near the household
        self.students = []
        for i, (uname, phone, cats, lat, lng) in enumerate([
            ('jane_w', '254722000222', ['Cleaning', 'Cooking'], -1.2921, 36.7856),
            ('brian_k', '254733000333', ['Cleaning', 'Gardening'], -1.2950, 36.7800),
            ('mary_n', '254744000444', ['Cleaning', 'Childcare'], -1.2900, 36.7900),
        ]):
            s = CustomUser.objects.create_user(
                username=uname, email=f'{uname}@test.com', password='Pass1234!',
                role='STUDENT', phone_number=phone,
            )
            sp = s.student_profile
            sp.verification_status = 'Verified'
            sp.availability_status = True
            sp.categories_offered = cats
            sp.location_lat = lat
            sp.location_lng = lng
            sp.save()
            Token.objects.create(user=s)
            self.students.append(s)

        self.student_tokens = [Token.objects.get(user=s).key for s in self.students]


class TestFindEligibleStudents(BroadcastFlowTestBase):
    """Test 1: find_eligible_students ranking and filtering."""

    def test_finds_verified_active_students_offering_category(self):
        task = Task.objects.create(
            household_owner=self.household, title='House Cleaning',
            description='Deep clean', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        ranked = find_eligible_students(task, radius_km=5, min_rating=0)
        self.assertEqual(len(ranked), 3)
        for student, score, dist in ranked:
            self.assertIn('Cleaning', student.student_profile.categories_offered)

    def test_excludes_unverified_students(self):
        self.students[0].student_profile.verification_status = 'Pending'
        self.students[0].student_profile.save()
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        ranked = find_eligible_students(task, radius_km=15, min_rating=0)
        self.assertEqual(len(ranked), 2)
        self.assertNotIn(self.students[0], [r[0] for r in ranked])

    def test_excludes_students_not_offering_category(self):
        task = Task.objects.create(
            household_owner=self.household, title='Gardening',
            description='test', category='Gardening', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        ranked = find_eligible_students(task, radius_km=15, min_rating=0)
        # Only brian_k offers Gardening
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0][0].username, 'brian_k')

    def test_excludes_blocked_students(self):
        BlockedStudent.objects.create(household=self.household, student=self.students[0])
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        ranked = find_eligible_students(task, radius_km=15, min_rating=0)
        self.assertEqual(len(ranked), 2)
        self.assertNotIn(self.students[0], [r[0] for r in ranked])

    def test_excludes_students_outside_radius(self):
        # Move one student far away
        sp = self.students[0].student_profile
        sp.location_lat = -1.5000  # ~23 km away
        sp.location_lng = 36.9000
        sp.save()
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        ranked = find_eligible_students(task, radius_km=5, min_rating=0)
        # jane_w is now too far; only brian_k and mary_n remain
        self.assertEqual(len(ranked), 2)
        self.assertNotIn(self.students[0], [r[0] for r in ranked])


class TestBroadcastAndAccept(BroadcastFlowTestBase):
    """Test 2: broadcast creates TaskRequests, student accepts."""

    @patch('tasks.matching._schedule_next_round')
    def test_broadcast_creates_requests_for_top_n(self, mock_schedule):
        """broadcast_task should create SENT TaskRequests for eligible students."""
        mock_schedule.return_value = None  # don't actually schedule a timer
        task = Task.objects.create(
            household_owner=self.household, title='House Cleaning',
            description='Deep clean', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Broadcasting')
        self.assertEqual(task.broadcast_round, 1)
        requests = TaskRequest.objects.filter(task=task)
        self.assertEqual(requests.count(), 3)
        for req in requests:
            self.assertEqual(req.status, 'SENT')

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_student_accepts_task(self, mock_timer, mock_schedule):
        """First student to accept should get the task."""
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='House Cleaning',
            description='Deep clean', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        req = TaskRequest.objects.filter(task=task, student=self.students[0]).first()
        success, msg = accept_task_request(req.id, self.students[0])
        self.assertTrue(success)

        task.refresh_from_db()
        self.assertEqual(task.status, 'Matched')
        self.assertEqual(task.assigned_student, self.students[0])
        req.refresh_from_db()
        self.assertEqual(req.status, 'ACCEPTED')
        self.assertIsNotNone(req.responded_at)

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_my_requests_endpoint(self, mock_timer, mock_schedule):
        """Student should see their available requests via API."""
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='House Cleaning',
            description='Deep clean', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.get('/api/tasks/my-requests/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['task_title'], 'House Cleaning')
        # The request should be marked VIEWED after retrieval
        self.assertEqual(res.data[0]['status'], 'VIEWED')


class TestConcurrentAcceptanceRace(BroadcastFlowTestBase):
    """Test 3: Only one student can accept — atomic first-to-accept."""

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_second_student_cannot_accept_same_task(self, mock_timer, mock_schedule):
        """When student A accepts, student B's request becomes TAKEN and
        B cannot accept."""
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='House Cleaning',
            description='Deep clean', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        req_a = TaskRequest.objects.get(task=task, student=self.students[0])
        req_b = TaskRequest.objects.get(task=task, student=self.students[1])

        # Student A accepts first
        success_a, _ = accept_task_request(req_a.id, self.students[0])
        self.assertTrue(success_a)

        # Student B tries to accept — should fail
        success_b, msg_b = accept_task_request(req_b.id, self.students[1])
        self.assertFalse(success_b)
        self.assertIn('no longer available', msg_b.lower())

        # Verify state
        task.refresh_from_db()
        self.assertEqual(task.assigned_student, self.students[0])
        req_b.refresh_from_db()
        self.assertEqual(req_b.status, 'TAKEN')

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_api_accept_endpoint_returns_409_for_taken(self, mock_timer, mock_schedule):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        req_a = TaskRequest.objects.get(task=task, student=self.students[0])
        req_b = TaskRequest.objects.get(task=task, student=self.students[1])

        # Student A accepts via API
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res_a = self.client.post('/api/tasks/accept-request/', {'request_id': req_a.id}, format='json')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)

        # Student B tries via API — 409
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[1]}')
        res_b = self.client.post('/api/tasks/accept-request/', {'request_id': req_b.id}, format='json')
        self.assertEqual(res_b.status_code, status.HTTP_409_CONFLICT)


class TestDoubleBooking(BroadcastFlowTestBase):
    """Test 4: Student cannot accept two tasks at the same date/time."""

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_student_cannot_accept_overlapping_tasks(self, mock_timer, mock_schedule):
        """A student who accepted a task for a date should not appear in
        eligible students for another task on the same date."""
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None

        from datetime import date, time as dtime
        task1 = Task.objects.create(
            household_owner=self.household, title='Morning Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
            scheduled_date=date(2026, 12, 1),
            scheduled_time=dtime(9, 0),
        )
        broadcast_task(task1)

        req1 = TaskRequest.objects.get(task=task1, student=self.students[0])
        success, _ = accept_task_request(req1.id, self.students[0])
        self.assertTrue(success)

        # Create a second task on the same date
        task2 = Task.objects.create(
            household_owner=self.household, title='Afternoon Cleaning',
            description='test', category='Cleaning', posted_price=600,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
            scheduled_date=date(2026, 12, 1),
            scheduled_time=dtime(11, 0),
        )
        ranked = find_eligible_students(task2, radius_km=15, min_rating=0)
        student_ids = [s.id for s, _, _ in ranked]
        # Student 0 accepted task1 on the same date — should be excluded
        self.assertNotIn(self.students[0].id, student_ids)
        # Other students should still be eligible
        self.assertIn(self.students[1].id, student_ids)


class TestRequestExpiry(BroadcastFlowTestBase):
    """Test 5: Requests that aren't responded to expire after round timeout."""

    @patch('tasks.matching._schedule_next_round')
    def test_round1_requests_expire_in_round2(self, mock_schedule):
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        # All 3 requests should be SENT
        self.assertEqual(
            TaskRequest.objects.filter(task=task, status='SENT').count(), 3
        )

        # Simulate round 2 running (which expires round 1)
        from tasks.matching import _run_round_2
        _run_round_2(task.id)

        # Round 1 requests should now be EXPIRED
        self.assertEqual(
            TaskRequest.objects.filter(task=task, broadcast_round=1, status='EXPIRED').count(), 3
        )


class TestGraceWindowCancellation(BroadcastFlowTestBase):
    """Test 6: Household can cancel within grace window; re-broadcasts."""

    @patch('tasks.matching.broadcast_task')
    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_household_cancels_match(self, mock_timer, mock_schedule, mock_rebroadcast):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        mock_rebroadcast.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])
        task.refresh_from_db()
        self.assertEqual(task.status, 'Matched')

        # Household cancels
        success, msg = household_cancel_match(task, block_student=False)
        self.assertTrue(success)

        task.refresh_from_db()
        self.assertEqual(task.status, 'Reopened')
        self.assertIsNone(task.assigned_student)
        self.assertIsNone(task.grace_window_deadline)
        mock_rebroadcast.assert_called_once()

    @patch('tasks.matching.broadcast_task')
    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_household_cancels_and_blocks_student(self, mock_timer, mock_schedule, mock_rebroadcast):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        mock_rebroadcast.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])
        task.refresh_from_db()

        household_cancel_match(task, block_student=True)

        self.assertTrue(
            BlockedStudent.objects.filter(
                household=self.household, student=self.students[0]
            ).exists()
        )

    @patch('tasks.views.matching.household_cancel_match')
    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_cancel_match_via_api(self, mock_timer, mock_schedule, mock_cancel):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        mock_cancel.return_value = (True, 'Match cancelled and task re-broadcast.')
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        # Manually set task to Matched so the endpoint accepts it
        broadcast_task(task)
        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel-match/', {'block_student': False}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        mock_cancel.assert_called_once()


class TestStudentReliability(BroadcastFlowTestBase):
    """Test 7: Cancelling after acceptance lowers reliability and can flag."""

    @patch('tasks.views.matching.broadcast_task')
    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_student_cancel_lowers_reliability(self, mock_timer, mock_schedule, mock_rebroadcast):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        mock_rebroadcast.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)

        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])

        # Student cancels via API
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.post(f'/api/tasks/{task.id}/student-cancel/', format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        sp = self.students[0].student_profile
        sp.refresh_from_db()
        self.assertEqual(sp.cancellation_count, 1)
        self.assertLess(sp.reliability_score, 1.0)
        self.assertFalse(sp.is_flagged)

    @patch('tasks.views.matching.broadcast_task')
    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_three_cancellations_flags_student(self, mock_timer, mock_schedule, mock_rebroadcast):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        mock_rebroadcast.return_value = None

        # Accept and cancel 3 times
        for i in range(3):
            task = Task.objects.create(
                household_owner=self.household, title=f'Cleaning {i}',
                description='test', category='Cleaning', posted_price=500,
                location_lat=-1.2921, location_lng=36.7856, status='Posted',
            )
            broadcast_task(task)
            req = TaskRequest.objects.get(task=task, student=self.students[0])
            accept_task_request(req.id, self.students[0])

            self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
            self.client.post(f'/api/tasks/{task.id}/student-cancel/', format='json')

        sp = self.students[0].student_profile
        sp.refresh_from_db()
        self.assertEqual(sp.cancellation_count, 3)
        self.assertTrue(sp.is_flagged)


class TestPermissions(BroadcastFlowTestBase):
    """Test 8: Only the right users can access broadcast endpoints."""

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_student_cannot_confirm_match(self, mock_timer, mock_schedule):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)
        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])

        # Student tries to confirm match → 403
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.post(f'/api/tasks/{task.id}/confirm-match/',
                               {'phone_number': '254711000111'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_student_cannot_cancel_match(self, mock_timer, mock_schedule):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)
        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])

        # Student tries to cancel match → 403
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.post(f'/api/tasks/{task.id}/cancel-match/', format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('tasks.matching._schedule_next_round')
    def test_household_cannot_accept_request(self, mock_schedule):
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)
        req = TaskRequest.objects.get(task=task, student=self.students[0])

        # Household tries to accept a request → 403
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.post('/api/tasks/accept-request/', {'request_id': req.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('tasks.matching._schedule_next_round')
    def test_household_settings_endpoints(self, mock_schedule):
        mock_schedule.return_value = None
        # GET settings
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.get('/api/household/settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('min_rating', res.data)
        self.assertIn('search_radius_km', res.data)

        # PATCH settings
        res = self.client.patch('/api/household/settings/',
                                {'min_rating': 3.5}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['min_rating'], 3.5)

        # Student cannot access settings → 403
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.get('/api/household/settings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class TestAddressHiding(BroadcastFlowTestBase):
    """Test 9: Full address is hidden from students until payment."""

    @patch('tasks.matching._schedule_next_round')
    @patch('tasks.matching.threading.Timer')
    def test_student_does_not_see_full_address_before_payment(self, mock_timer, mock_schedule):
        mock_timer.return_value = MagicMock()
        mock_schedule.return_value = None
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_address='123 Sample Street, Kilimani, Nairobi',
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)
        req = TaskRequest.objects.get(task=task, student=self.students[0])
        accept_task_request(req.id, self.students[0])
        task.refresh_from_db()

        # Student retrieves task detail — full address should be null
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNone(res.data['location_address_full'])

        # Household retrieves same task — should see full address
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res2 = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['location_address_full'], '123 Sample Street, Kilimani, Nairobi')


class TestRequestActions(BroadcastFlowTestBase):
    """Test 10: students can accept, ignore or decline broadcast requests,
    and act on them straight from their notifications."""

    def _broadcast_task(self):
        task = Task.objects.create(
            household_owner=self.household, title='Cleaning',
            description='test', category='Cleaning', posted_price=500,
            location_lat=-1.2921, location_lng=36.7856, status='Posted',
        )
        broadcast_task(task)
        return task

    @patch('tasks.matching._schedule_next_round')
    def test_decline_request_via_api(self, mock_schedule):
        mock_schedule.return_value = None
        task = self._broadcast_task()
        req = TaskRequest.objects.get(task=task, student=self.students[0])

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.post('/api/tasks/decline-request/', {'request_id': req.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        req.refresh_from_db()
        self.assertEqual(req.status, 'DECLINED')
        self.assertIsNotNone(req.responded_at)

        # Declined requests disappear from the student's inbox
        res_inbox = self.client.get('/api/tasks/my-requests/')
        self.assertEqual(res_inbox.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_inbox.data), 0)

        # ...but remain visible in history
        res_history = self.client.get('/api/tasks/my-requests/history/')
        self.assertEqual(len(res_history.data), 1)
        self.assertEqual(res_history.data[0]['status'], 'DECLINED')

    @patch('tasks.matching._schedule_next_round')
    def test_ignore_request_via_api(self, mock_schedule):
        mock_schedule.return_value = None
        task = self._broadcast_task()
        req = TaskRequest.objects.get(task=task, student=self.students[0])

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.post('/api/tasks/ignore-request/', {'request_id': req.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        req.refresh_from_db()
        self.assertEqual(req.status, 'IGNORED')
        self.assertIsNotNone(req.responded_at)

        # Ignored requests disappear from the inbox but stay in history
        res_inbox = self.client.get('/api/tasks/my-requests/')
        self.assertEqual(len(res_inbox.data), 0)
        res_history = self.client.get('/api/tasks/my-requests/history/')
        self.assertEqual(len(res_history.data), 1)
        self.assertEqual(res_history.data[0]['status'], 'IGNORED')

        # The task itself stays live for the other students
        task.refresh_from_db()
        self.assertEqual(task.status, 'Broadcasting')

    @patch('tasks.matching._schedule_next_round')
    def test_ignored_request_cannot_be_accepted(self, mock_schedule):
        mock_schedule.return_value = None
        task = self._broadcast_task()
        req = TaskRequest.objects.get(task=task, student=self.students[0])

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        self.client.post('/api/tasks/ignore-request/', {'request_id': req.id}, format='json')

        # Trying to accept afterwards → conflict
        res = self.client.post('/api/tasks/accept-request/', {'request_id': req.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

        # Another student can still accept normally
        req_b = TaskRequest.objects.get(task=task, student=self.students[1])
        success, _ = accept_task_request(req_b.id, self.students[1])
        self.assertTrue(success)

    @patch('tasks.matching._schedule_next_round')
    def test_task_request_notification_carries_request_id(self, mock_schedule):
        mock_schedule.return_value = None
        task = self._broadcast_task()
        req = TaskRequest.objects.get(task=task, student=self.students[0])

        from users.notifications import Notification
        notif = Notification.objects.filter(
            recipient=self.students[0], notification_type='task_request'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.request_id, req.id)

        # The notifications endpoint exposes request_id + live request_status
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        notif_data = next(
            n for n in res.data['notifications'] if n['type'] == 'task_request'
        )
        self.assertEqual(notif_data['request_id'], req.id)
        self.assertEqual(notif_data['request_status'], 'SENT')

        # After ignoring, the same notification reflects the closed status
        self.client.post('/api/tasks/ignore-request/', {'request_id': req.id}, format='json')
        res = self.client.get('/api/notifications/')
        notif_data = next(
            n for n in res.data['notifications'] if n['type'] == 'task_request'
        )
        self.assertEqual(notif_data['request_status'], 'IGNORED')

    @patch('tasks.matching._schedule_next_round')
    def test_task_detail_exposes_my_request(self, mock_schedule):
        mock_schedule.return_value = None
        task = self._broadcast_task()
        req = TaskRequest.objects.get(task=task, student=self.students[0])

        # Student sees their own request on the task detail screen
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[0]}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['my_request']['id'], req.id)
        self.assertEqual(res.data['my_request']['status'], 'SENT')

        # The household (not a student) gets no my_request payload
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res2 = self.client.get(f'/api/tasks/{task.id}/')
        self.assertIsNone(res2.data['my_request'])


# ===========================================================================
# Geolocation verification: task pin, check-in results, anti-spoofing,
# privacy / access control, retention.  Requirement areas 1-10.
# ===========================================================================

from decimal import Decimal
from django.utils import timezone as django_tz
from django.core.management import call_command
from tasks import geo
from tasks.models import TaskCompletion, CheckIn, LocationConsent, LocationPolicy, Dispute


class GeoFlowTestBase(BroadcastFlowTestBase):
    """Shared setup for geolocation check-in tests."""

    def setUp(self):
        super().setUp()
        self.admin = CustomUser.objects.create_user(
            username='admin_geo', email='admin@test.com', password='Pass1234!',
            role='ADMIN',
        )
        self.admin_token = Token.objects.create(user=self.admin).key
        # Default student is self.students[0] (jane_w)
        self.student = self.students[0]
        self.student_token = self.student_tokens[0]

    def _make_assigned_task(self, lat=-1.292100, lng=36.785600, radius=150,
                             start_code='1234', with_escrow=True):
        task = Task.objects.create(
            household_owner=self.household,
            title='House cleaning',
            description='Clean the house',
            category='Cleaning',
            posted_price=Decimal('500.00'),
            location_address='123 Sample Street, Kilimani, Nairobi',
            location_lat=Decimal(str(lat)),
            location_lng=Decimal(str(lng)),
            location_landmark='Blue gate next to Yaya Centre',
            geofence_radius_m=radius,
            location_pin_confirmed=True,
            assigned_student=self.student,
            status='Assigned',
        )
        if with_escrow:
            Transaction.objects.create(
                task=task, amount=Decimal('500.00'), status='Held'
            )
        TaskCompletion.objects.create(task=task, start_code=start_code)
        return task

    def _consent(self, student=None):
        LocationConsent.objects.get_or_create(
            student=student or self.student,
            defaults={'version': geo.LOCATION_CONSENT_VERSION},
        )

    def _checkin(self, task, **overrides):
        """POST a check-in as the assigned student."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        payload = {
            'start_code': '1234',
            'lat': '-1.292100', 'lng': '36.785600',   # exactly on the pin
            'accuracy_m': 20,
            'device_time': django_tz.now().isoformat(),
        }
        payload.update(overrides)
        return self.client.post(f'/api/tasks/{task.id}/checkin/', payload, format='json')


class TestHaversine(unittest.TestCase):
    """Requirement 10a: distance calculation."""

    def test_zero_distance_at_same_point(self):
        self.assertAlmostEqual(geo.haversine_m(-1.2921, 36.7856, -1.2921, 36.7856), 0.0, places=6)

    def test_known_distance_one_degree_latitude(self):
        # One degree of latitude ≈ 111.19 km on a mean-radius sphere
        d = geo.haversine_m(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(d, 111195.0, delta=100.0)

    def test_known_distance_nairobi_points(self):
        # ~1.1 km apart (0.01 deg lat)
        d = geo.haversine_m(-1.2900, 36.7800, -1.2800, 36.7800)
        self.assertAlmostEqual(d, 1112.0, delta=15.0)

    def test_symmetry(self):
        self.assertAlmostEqual(
            geo.haversine_m(-1.29, 36.78, -1.30, 36.79),
            geo.haversine_m(-1.30, 36.79, -1.29, 36.78),
        )

    def test_approximate_coords_blur_deterministically(self):
        approx1 = geo.approximate_coords(-1.292100, 36.785600, 'task-1')
        approx2 = geo.approximate_coords(-1.292100, 36.785600, 'task-1')
        self.assertEqual(approx1, approx2)  # deterministic
        # Blurred by a meaningful amount (≥ 100 m from the pin)
        d = geo.haversine_m(-1.292100, 36.785600, *approx1)
        self.assertGreater(d, 50.0)
        # Different seeds give different blurred centres
        approx_other = geo.approximate_coords(-1.292100, 36.785600, 'task-2')
        self.assertNotEqual(approx1, approx_other)


class TestPinRequiredToPost(GeoFlowTestBase):
    """Requirement 1: a confirmed map pin is required to post a task."""

    @patch('tasks.views.threading')
    def test_post_without_pin_is_rejected(self, mock_threading):
        mock_threading.Thread.return_value = MagicMock()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.post('/api/tasks/', {
            'title': 'No pin task', 'description': 'x', 'category': 'Cleaning',
            'posted_price': '500.00', 'location_address': 'Kilimani, Nairobi',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('tasks.views.threading')
    def test_post_with_confirmed_pin_succeeds(self, mock_threading):
        mock_threading.Thread.return_value = MagicMock()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.post('/api/tasks/', {
            'title': 'Pinned task', 'description': 'x', 'category': 'Cleaning',
            'posted_price': '500.00', 'location_address': 'Kilimani, Nairobi',
            'location_lat': '-1.292100', 'location_lng': '36.785600',
            'location_landmark': 'Near Yaya', 'geofence_radius_m': 200,
            'location_pin_confirmed': True,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['geofence_radius_m'], 200)


class TestCheckInVerified(GeoFlowTestBase):
    """Requirement 2/10b: correct code + position inside the radius."""

    def test_verified_checkin_starts_task(self):
        task = self._make_assigned_task()
        self._consent()
        res = self._checkin(task)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['result'], 'VERIFIED')
        self.assertFalse(res.data['flagged'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        row = CheckIn.objects.get(task=task)
        self.assertEqual(row.type, 'START')
        self.assertEqual(row.result, 'VERIFIED')
        self.assertEqual(row.student, self.student)
        self.assertAlmostEqual(row.distance_m, 0.0, places=3)
        self.assertFalse(row.mock_location_flag)
        # Append-only audit fields captured
        self.assertIsNotNone(row.server_time)
        self.assertIsNotNone(row.device_time)

    def test_verified_checkin_within_radius(self):
        task = self._make_assigned_task(radius=200)
        self._consent()
        # ~30 m away (0.00027 deg lat)
        res = self._checkin(task, lat='-1.29237', lng='36.785600')
        self.assertEqual(res.data['result'], 'VERIFIED')
        row = CheckIn.objects.get(task=task)
        self.assertLess(row.distance_m, 200.0)


class TestCheckInOutOfRange(GeoFlowTestBase):
    """Requirement 2/10c: outside the radius → flagged, not hard-blocked."""

    def test_out_of_range_checkin_is_flagged_but_starts(self):
        task = self._make_assigned_task(radius=150)
        self._consent()
        # ~1.1 km away from the pin
        res = self._checkin(task, lat='-1.282100', lng='36.785600')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['result'], 'OUT_OF_RANGE')
        self.assertTrue(res.data['flagged'])
        self.assertTrue(res.data['retry_allowed'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        row = CheckIn.objects.get(task=task)
        self.assertEqual(row.result, 'OUT_OF_RANGE')
        self.assertGreater(row.distance_m, 150.0)
        self.assertLess(row.distance_m, 1300.0)

        # The household was told the location was flagged (no coordinates)
        from users.notifications import Notification
        notif = Notification.objects.filter(
            recipient=self.household, task_id=task.id
        ).latest('created_at')
        self.assertIn('flagged', notif.message)

    def test_flagged_checkin_can_retry_to_verified(self):
        task = self._make_assigned_task(radius=150)
        self._consent()
        res = self._checkin(task, lat='-1.282100', lng='36.785600')
        self.assertEqual(res.data['result'], 'OUT_OF_RANGE')
        # Retry with the right position while task is InProgress
        res2 = self._checkin(task)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['result'], 'VERIFIED')
        self.assertEqual(CheckIn.objects.filter(task=task).count(), 2)

        # The household summary now reports the upgraded result
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        detail = self.client.get(f'/api/tasks/{task.id}/').data
        self.assertTrue(detail['checkin_summary']['location_verified'])

    def test_no_retry_needed_after_verified(self):
        task = self._make_assigned_task()
        self._consent()
        self._checkin(task)
        res2 = self._checkin(task)
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)


class TestCheckInLowAccuracy(GeoFlowTestBase):
    """Requirement 2/10d: low GPS accuracy → flagged, not hard-blocked."""

    def test_low_accuracy_is_flagged_but_starts(self):
        task = self._make_assigned_task()
        self._consent()
        res = self._checkin(task, accuracy_m=500)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['result'], 'LOW_ACCURACY')
        self.assertTrue(res.data['flagged'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        row = CheckIn.objects.get(task=task)
        self.assertEqual(row.result, 'LOW_ACCURACY')
        self.assertEqual(row.accuracy_m, 500.0)


class TestCheckInDenied(GeoFlowTestBase):
    """Requirement 2/10e: denied permission blocks start unless the admin
    setting allows a flagged check-in."""

    def test_denied_permission_blocks_checkin(self):
        task = self._make_assigned_task()
        self._consent()
        res = self._checkin(task, lat=None, lng=None, accuracy_m=None)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['result'], 'LOCATION_DENIED')
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')   # NOT started
        row = CheckIn.objects.get(task=task)
        self.assertEqual(row.result, 'LOCATION_DENIED')
        self.assertIsNone(row.lat)

    def test_admin_setting_allows_flagged_checkin_when_denied(self):
        policy = LocationPolicy.get()
        policy.allow_flagged_when_denied = True
        policy.save()
        task = self._make_assigned_task()
        self._consent()
        res = self._checkin(task, lat=None, lng=None, accuracy_m=None)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['result'], 'LOCATION_DENIED')
        self.assertTrue(res.data['flagged'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')


class TestCheckInMockLocation(GeoFlowTestBase):
    """Requirement 5: mock/simulated locations are rejected and flagged."""

    def test_mock_location_is_rejected(self):
        task = self._make_assigned_task()
        self._consent()
        res = self._checkin(task, mock_location=True)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['result'], 'FLAGGED_MOCK')
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')   # NOT started
        row = CheckIn.objects.get(task=task)
        self.assertTrue(row.mock_location_flag)


class TestOfflineLateSync(GeoFlowTestBase):
    """Requirement 5/10f: offline queue syncs later and is flagged late."""

    def test_late_sync_flagged(self):
        task = self._make_assigned_task()
        self._consent()
        old_time = django_tz.now() - django_tz.timedelta(minutes=25)
        res = self._checkin(task, device_time=old_time.isoformat(), late_sync=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        row = CheckIn.objects.get(task=task)
        self.assertTrue(row.late_sync_flag)
        # device timestamp preserved for the audit trail
        self.assertAlmostEqual(
            (row.device_time - old_time).total_seconds(), 0.0, delta=1.0
        )

    def test_time_skew_recorded(self):
        task = self._make_assigned_task()
        self._consent()
        old_time = django_tz.now() - django_tz.timedelta(minutes=10)
        self._checkin(task, device_time=old_time.isoformat())
        row = CheckIn.objects.get(task=task)
        self.assertIsNotNone(row.time_skew_seconds)
        self.assertGreater(row.time_skew_seconds, 590)  # ~10 minutes


class TestImpossibleJump(GeoFlowTestBase):
    """Requirement 5: implausible jumps between check-ins are flagged."""

    def test_impossible_jump_flagged(self):
        task = self._make_assigned_task()
        self._consent()
        # Previous check-in for the same student on another task,
        # 50 km away, recorded moments ago
        other = Task.objects.create(
            household_owner=self.household, title='Other', description='x',
            category='Cleaning', posted_price=Decimal('100.00'),
            assigned_student=self.student, status='Completed',
        )
        CheckIn.objects.create(
            task=other, student=self.student, type='ARRIVAL',
            lat=Decimal('-1.7000'), lng=Decimal('36.7000'),  # ~52 km away
            result='VERIFIED',
        )
        res = self._checkin(task)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        row = CheckIn.objects.get(task=task)
        self.assertTrue(row.impossible_jump_flag)


class TestWrongCodeWithCorrectLocation(GeoFlowTestBase):
    """Requirement 10g: wrong code with a correct location."""

    def test_wrong_code_records_attempt_but_does_not_start(self):
        task = self._make_assigned_task(start_code='4321')
        self._consent()
        res = self._checkin(task, start_code='9999')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['result'], 'WRONG_CODE')
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')
        row = CheckIn.objects.get(task=task)
        self.assertEqual(row.result, 'WRONG_CODE')
        # Location of the attempt is still recorded for the audit trail
        self.assertIsNotNone(row.lat)
        self.assertAlmostEqual(row.distance_m, 0.0, places=3)


class TestConsentRequired(GeoFlowTestBase):
    """Requirement 4: consent must be recorded before the first check-in."""

    def test_checkin_blocked_without_consent(self):
        task = self._make_assigned_task()
        res = self._checkin(task)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data['code'], 'consent_required')
        self.assertEqual(res.data['consent_version'], geo.LOCATION_CONSENT_VERSION)
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_consent_endpoint_records_and_reports(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        res = self.client.get('/api/geo/consent/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['consented'])
        self.assertEqual(res.data['version'], geo.LOCATION_CONSENT_VERSION)
        self.assertIn('GPS position', res.data['text'])

        res2 = self.client.post('/api/geo/consent/', {'version': geo.LOCATION_CONSENT_VERSION}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        res3 = self.client.get('/api/geo/consent/')
        self.assertTrue(res3.data['consented'])

        # Check-in now works
        task = self._make_assigned_task()
        res4 = self._checkin(task)
        self.assertEqual(res4.status_code, status.HTTP_200_OK)


class TestLocationAccessControl(GeoFlowTestBase):
    """Requirement 8/10h: access control on location data."""

    def test_student_sees_approximate_location_until_paid(self):
        task = self._make_assigned_task(with_escrow=False)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['location_exact'])
        self.assertIsNone(res.data['location_landmark'])
        self.assertIsNone(res.data['location_address_full'])
        self.assertNotEqual(str(task.location_lat), res.data['location_lat'])
        # Blurred centre is close-ish but not the pin
        d = geo.haversine_m(task.location_lat, task.location_lng,
                            res.data['location_lat'], res.data['location_lng'])
        self.assertGreater(d, 50.0)
        # Approximate area label shown instead of the full address
        self.assertEqual(res.data['location_area'], 'Kilimani, Nairobi')
        # The address field itself is masked to the area label too — the full
        # text ('Yaya Centre, Kilimani, Nairobi') could name the building.
        self.assertEqual(res.data['location_address'], 'Kilimani, Nairobi')

        # Household still sees the full address text
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res_hh = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(
            res_hh.data['location_address'],
            '123 Sample Street, Kilimani, Nairobi',
        )

    def test_student_sees_exact_location_after_payment(self):
        task = self._make_assigned_task()  # escrow Held
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertTrue(res.data['location_exact'])
        self.assertEqual(float(res.data['location_lat']), float(task.location_lat))
        self.assertEqual(res.data['location_landmark'], 'Blue gate next to Yaya Centre')

    def test_household_sees_exact_location(self):
        task = self._make_assigned_task()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertTrue(res.data['location_exact'])
        self.assertEqual(float(res.data['location_lat']), float(task.location_lat))

    def test_unrelated_student_sees_approximate_in_list(self):
        task = self._make_assigned_task()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_tokens[1]}')
        res = self.client.get('/api/tasks/')
        row = next(t for t in res.data if t['id'] == task.id)
        self.assertFalse(row['location_exact'])
        self.assertNotEqual(row['location_lat'], str(task.location_lat))
        # Address text masked to the area label in the list too
        self.assertEqual(row['location_address'], 'Kilimani, Nairobi')

    def test_household_summary_has_no_raw_coordinates(self):
        task = self._make_assigned_task()
        self._consent()
        self._checkin(task)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        summary = res.data['checkin_summary']
        self.assertTrue(summary['location_verified'])
        self.assertEqual(summary['result'], 'VERIFIED')
        # No coordinate keys anywhere in the summary
        self.assertNotIn('lat', summary)
        self.assertNotIn('lng', summary)
        # Legacy completion payload no longer leaks coordinates either
        self.assertNotIn('checkin_lat', res.data['completion_timestamps'])

    def test_location_audit_is_admin_only(self):
        task = self._make_assigned_task()
        self._consent()
        self._checkin(task, accuracy_m=300)

        # Student: forbidden
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Household: forbidden
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin: allowed, with raw coordinates, distance, accuracy, flags
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res.data['task']['location_lat']), float(task.location_lat))
        self.assertEqual(res.data['task']['geofence_radius_m'], 150)
        self.assertEqual(len(res.data['checkins']), 1)
        ci = res.data['checkins'][0]
        self.assertEqual(ci['result'], 'LOW_ACCURACY')
        self.assertIsNotNone(ci['distance_m'])
        self.assertIsNotNone(ci['accuracy_m'])
        self.assertIn('device_info', ci)
        # Complaint and chat history are included for the dispute view
        self.assertIn('dispute', res.data)
        self.assertIn('messages', res.data)


class TestNoShowRequiresVerified(GeoFlowTestBase):
    """Requirement 7: no VERIFIED check-in within 30 min → NO_SHOW."""

    def _schedule_task_in_past(self, task):
        from datetime import time as dt_time
        task.scheduled_date = (django_tz.now() - django_tz.timedelta(hours=2)).date()
        task.scheduled_time = dt_time(
            (django_tz.now() - django_tz.timedelta(hours=2)).hour, 0
        )
        task.save()

    def test_wrong_code_attempts_still_count_as_no_show(self):
        task = self._make_assigned_task(start_code='4321')
        self._schedule_task_in_past(task)
        self._consent()
        res = self._checkin(task, start_code='9999')  # WRONG_CODE attempt only
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        call_command('run_scheduled_tasks', verbosity=0)
        task.refresh_from_db()
        self.assertEqual(task.status, 'NoShow')

    def test_verified_checkin_prevents_no_show(self):
        task = self._make_assigned_task()
        self._schedule_task_in_past(task)
        self._consent()
        self._checkin(task)  # VERIFIED → task InProgress
        call_command('run_scheduled_tasks', verbosity=0)
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')


class TestLocationRetentionJob(GeoFlowTestBase):
    """Requirement 8/10i: retention job anonymises old coordinates."""

    def _old_checkin(self, task, days_old=100):
        self._consent()
        self._checkin(task)
        row = CheckIn.objects.get(task=task)
        CheckIn.objects.filter(id=row.id).update(
            server_time=django_tz.now() - django_tz.timedelta(days=days_old)
        )
        return CheckIn.objects.get(id=row.id)

    def test_old_coordinates_are_anonymised(self):
        task = self._make_assigned_task()
        row = self._old_checkin(task)
        self.assertIsNotNone(row.lat)

        call_command('run_scheduled_tasks', verbosity=0)

        row.refresh_from_db()
        self.assertIsNone(row.lat)
        self.assertIsNone(row.lng)
        self.assertIsNone(row.accuracy_m)
        self.assertIsNotNone(row.anonymised_at)
        # The row itself is kept (append-only audit trail) with the verdict
        self.assertEqual(row.result, 'VERIFIED')

    def test_coordinates_kept_while_dispute_is_open(self):
        task = self._make_assigned_task()
        row = self._old_checkin(task)
        Dispute.objects.create(
            task=task, raised_by=self.household, reason='did_not_show',
            description='Student claims to have arrived but was not there.',
        )

        call_command('run_scheduled_tasks', verbosity=0)

        row.refresh_from_db()
        self.assertIsNotNone(row.lat)      # retained: dispute open
        self.assertIsNone(row.anonymised_at)

    def test_recent_coordinates_are_kept(self):
        task = self._make_assigned_task()
        row = self._old_checkin(task, days_old=10)

        call_command('run_scheduled_tasks', verbosity=0)

        row.refresh_from_db()
        self.assertIsNotNone(row.lat)

    def test_retention_period_is_configurable(self):
        policy = LocationPolicy.get()
        policy.retention_days = 30
        policy.save()
        task = self._make_assigned_task()
        row = self._old_checkin(task, days_old=45)

        call_command('run_scheduled_tasks', verbosity=0)

        row.refresh_from_db()
        self.assertIsNone(row.lat)


class TestLocationPolicyEndpoint(GeoFlowTestBase):
    """Requirement 2/8: admin-configurable location policy."""

    def test_get_policy(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        res = self.client.get('/api/location-policy/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['retention_days'], 90)
        self.assertFalse(res.data['allow_flagged_when_denied'])

    def test_patch_policy_admin_only(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        res = self.client.patch('/api/location-policy/',
                                 {'retention_days': 120}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.patch('/api/location-policy/',
                                 {'retention_days': 120}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['retention_days'], 120)
