"""
Test scenarios for the users app:
  - Student registration
  - Household registration
  - Login (username, email, wrong password, inactive user)
  - /auth/me/ — GET current user, PATCH update profile
  - Notifications — list, mark-all-read
  - Household settings — GET/PATCH
  - Block / unblock student
  - Reliability score and flagging (record_cancellation)
  - Role-based access guards
"""

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from users.models import CustomUser, StudentProfile, HouseholdProfile, BlockedStudent
from users.notifications import Notification


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _make_student(username='s1', password='Pass1234!', verified=True):
    u = CustomUser.objects.create_user(
        username=username, email=f'{username}@test.com',
        password=password, role='STUDENT', phone_number='254700000001',
    )
    sp = u.student_profile
    if verified:
        sp.verification_status = 'Verified'
        sp.categories_offered = ['Cleaning']
        sp.location_lat = -1.292
        sp.location_lng = 36.785
        sp.save()
    return u


def _make_household(username='hh1', password='Pass1234!', verified=True):
    u = CustomUser.objects.create_user(
        username=username, email=f'{username}@test.com',
        password=password, role='HOUSEHOLD', phone_number='254700000002',
    )
    hp = u.household_profile
    if verified:
        hp.verification_status = 'Verified'
        hp.address = '123 Test St, Nairobi'
        hp.location_lat = -1.292
        hp.location_lng = 36.785
        hp.save()
    return u


# ===========================================================================
# 1. Registration
# ===========================================================================

class TestStudentRegistration(APITestCase):

    def test_register_student_returns_token(self):
        res = self.client.post('/api/auth/register/student/', {
            'username': 'newstudent',
            'email': 'newstudent@uon.ac.ke',
            'password': 'Pass1234!',
            'phone_number': '254711000001',
            'university_id': 'UON/001',
            'university_name': 'University of Nairobi',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', res.data)
        self.assertEqual(res.data['user']['role'], 'STUDENT')
        # Profile created automatically
        u = CustomUser.objects.get(username='newstudent')
        self.assertTrue(hasattr(u, 'student_profile'))

    def test_duplicate_username_rejected(self):
        _make_student(username='dupuser')
        res = self.client.post('/api/auth/register/student/', {
            'username': 'dupuser', 'email': 'dup2@test.com',
            'password': 'Pass1234!', 'phone_number': '254700000099',
            'university_id': 'X1', 'university_name': 'Test U',
        }, format='json')
        self.assertNotEqual(res.status_code, status.HTTP_201_CREATED)

    def test_register_household_returns_token(self):
        res = self.client.post('/api/auth/register/household/', {
            'username': 'newhousehold',
            'email': 'hh@test.com',
            'password': 'Pass1234!',
            'phone_number': '254711000002',
            'address': '45 Westlands Road, Nairobi',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', res.data)
        self.assertEqual(res.data['user']['role'], 'HOUSEHOLD')


# ===========================================================================
# 2. Login
# ===========================================================================

class TestLogin(APITestCase):

    def setUp(self):
        self.student = _make_student('login_st')
        self.household = _make_household('login_hh')

    def test_login_with_username(self):
        res = self.client.post('/api/auth/login/', {
            'username': 'login_st', 'password': 'Pass1234!',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('token', res.data)
        self.assertEqual(res.data['user']['username'], 'login_st')

    def test_login_with_email(self):
        res = self.client.post('/api/auth/login/', {
            'username': 'login_st@test.com', 'password': 'Pass1234!',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('token', res.data)

    def test_wrong_password_rejected(self):
        res = self.client.post('/api/auth/login/', {
            'username': 'login_st', 'password': 'WrongPass!',
        }, format='json')
        self.assertIn(res.status_code, [400, 401])
        self.assertNotIn('token', res.data)

    def test_nonexistent_user_rejected(self):
        res = self.client.post('/api/auth/login/', {
            'username': 'nobody', 'password': 'Pass1234!',
        }, format='json')
        self.assertIn(res.status_code, [400, 401])

    def test_inactive_user_rejected(self):
        self.student.is_active = False
        self.student.save()
        res = self.client.post('/api/auth/login/', {
            'username': 'login_st', 'password': 'Pass1234!',
        }, format='json')
        self.assertNotEqual(res.status_code, 200)

    def test_unauthenticated_cannot_access_me(self):
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, 401)

    def test_authenticated_can_access_me(self):
        token = Token.objects.create(user=self.student).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['username'], 'login_st')
        self.assertIn('student_profile', res.data)


# ===========================================================================
# 3. Profile update (PATCH /auth/me/)
# ===========================================================================

class TestProfileUpdate(APITestCase):

    def setUp(self):
        self.student = _make_student('update_st')
        self.token = Token.objects.create(user=self.student).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_update_first_name(self):
        res = self.client.patch('/api/auth/me/', {'first_name': 'Jane'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Jane')

    def test_update_phone_number(self):
        res = self.client.patch('/api/auth/me/', {'phone_number': '254799000001'}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_household_cannot_change_own_role(self):
        hh = _make_household('update_hh')
        tok = Token.objects.create(user=hh).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {tok}')
        # role is stripped server-side — the update silently ignores it
        self.client.patch('/api/auth/me/', {'role': 'ADMIN'}, format='json')
        hh.refresh_from_db()
        self.assertEqual(hh.role, 'HOUSEHOLD')  # unchanged


# ===========================================================================
# 4. Notifications
# ===========================================================================

class TestNotifications(APITestCase):

    def setUp(self):
        self.user = _make_student('notif_st')
        self.token = Token.objects.create(user=self.user).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        # Create some notifications
        for i in range(5):
            Notification.send(self.user, 'general', f'Title {i}', f'Msg {i}')
        # Mark 2 as read using pks to avoid sliced-queryset error
        pks = list(Notification.objects.filter(
            recipient=self.user).order_by('id').values_list('id', flat=True)[:2])
        Notification.objects.filter(pk__in=pks).update(is_read=True)

    def test_list_notifications_returns_all(self):
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['notifications']), 5)

    def test_unread_count_is_correct(self):
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.data['unread_count'], 3)

    def test_mark_all_read(self):
        self.client.patch('/api/notifications/')
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.data['unread_count'], 0)

    def test_notifications_require_auth(self):
        self.client.credentials()
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.status_code, 401)


# ===========================================================================
# 5. Household settings
# ===========================================================================

class TestHouseholdSettings(APITestCase):

    def setUp(self):
        self.hh = _make_household('settings_hh')
        self.hh_token = Token.objects.create(user=self.hh).key
        self.student = _make_student('settings_st')
        self.st_token = Token.objects.create(user=self.student).key

    def test_household_can_get_settings(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get('/api/household/settings/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('min_rating', res.data)
        self.assertIn('search_radius_km', res.data)

    def test_student_cannot_get_household_settings(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.get('/api/household/settings/')
        self.assertEqual(res.status_code, 403)

    def test_update_min_rating(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.patch('/api/household/settings/', {'min_rating': 4.0}, format='json')
        self.assertEqual(res.status_code, 200)
        self.hh.household_profile.refresh_from_db()
        self.assertEqual(float(self.hh.household_profile.min_rating), 4.0)

    def test_update_search_radius(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.patch('/api/household/settings/', {'search_radius_km': 10}, format='json')
        self.assertEqual(res.status_code, 200)


# ===========================================================================
# 6. Block / unblock student
# ===========================================================================

class TestBlockStudent(APITestCase):

    def setUp(self):
        self.hh = _make_household('block_hh')
        self.hh_token = Token.objects.create(user=self.hh).key
        self.student = _make_student('block_st')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')

    def test_block_student(self):
        res = self.client.post('/api/household/block/',
                               {'student_id': self.student.id}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(BlockedStudent.objects.filter(
            household=self.hh, student=self.student).exists())

    def test_unblock_student(self):
        BlockedStudent.objects.create(household=self.hh, student=self.student)
        res = self.client.delete('/api/household/block/',
                                 {'student_id': self.student.id}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(BlockedStudent.objects.filter(
            household=self.hh, student=self.student).exists())

    def test_block_same_student_twice_is_idempotent(self):
        self.client.post('/api/household/block/',
                         {'student_id': self.student.id}, format='json')
        self.client.post('/api/household/block/',
                         {'student_id': self.student.id}, format='json')
        self.assertEqual(BlockedStudent.objects.filter(
            household=self.hh, student=self.student).count(), 1)

    def test_student_cannot_block(self):
        st_token = Token.objects.create(user=self.student).key
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {st_token}')
        res = self.client.post('/api/household/block/',
                               {'student_id': self.student.id}, format='json')
        # Must be forbidden or 400 — not 200
        self.assertNotEqual(res.status_code, 200)


# ===========================================================================
# 7. Reliability score and flagging
# ===========================================================================

class TestReliabilityScore(APITestCase):

    def setUp(self):
        self.student = _make_student('rel_st')

    def test_initial_reliability_is_1(self):
        sp = self.student.student_profile
        self.assertEqual(sp.reliability_score, 1.0)
        self.assertEqual(sp.cancellation_count, 0)
        self.assertFalse(sp.is_flagged)

    def test_one_cancellation_lowers_score(self):
        sp = self.student.student_profile
        sp.record_cancellation()
        self.assertEqual(sp.cancellation_count, 1)
        self.assertLess(sp.reliability_score, 1.0)
        self.assertFalse(sp.is_flagged)

    def test_three_cancellations_flags_student(self):
        sp = self.student.student_profile
        for _ in range(3):
            sp.record_cancellation()
        self.assertEqual(sp.cancellation_count, 3)
        self.assertTrue(sp.is_flagged)

    def test_score_floor_is_0_3(self):
        sp = self.student.student_profile
        for _ in range(50):   # many cancellations
            sp.record_cancellation()
        self.assertGreaterEqual(sp.reliability_score, 0.3)

    def test_flagged_student_excluded_from_eligible(self):
        """A flagged student must not appear in find_eligible_students."""
        from tasks.models import Task, PriceGuide
        from tasks.matching import find_eligible_students
        PriceGuide.objects.get_or_create(
            category='Cleaning',
            defaults={'min_price': 300, 'max_price': 800, 'recommended_price': 500},
        )
        hh = _make_household('excl_hh')
        task = Task.objects.create(
            household_owner=hh, title='Test', description='T',
            category='Cleaning', posted_price=500,
            location_lat=-1.292, location_lng=36.785,
            location_pin_confirmed=True, status='Posted',
        )
        sp = self.student.student_profile
        sp.is_flagged = True
        sp.save()
        eligible = find_eligible_students(task, radius_km=50, min_rating=0)
        self.assertNotIn(self.student, [r[0] for r in eligible])
