"""
Geolocation verification tests.

Covers every scenario from the specification:
  1.  Haversine distance calculation
  2.  Inside the geofence — VERIFIED
  3.  Outside the geofence — OUT_OF_RANGE (allowed, flagged)
  4.  Low GPS accuracy — LOW_ACCURACY (allowed, flagged)
  5.  Permission denied (no coordinates) — LOCATION_DENIED
  6.  Mock / simulated location — FLAGGED_MOCK (rejected)
  7.  Offline / late sync — submitted after a delay, flagged
  8.  Wrong start code with a correct location
  9.  Access control: only the assigned student may check in
  10. Impossible jump detection (anti-spoofing)
  11. Time skew detection (anti-spoofing)
  12. Approximate-coords privacy: non-privileged viewers see a blurred pin
  13. Retention job: anonymises coordinates, skips open disputes
  14. Consent gate: check-in rejected until student accepts the notice
  15. Retry after a flagged check-in
  16. Location audit endpoint access control
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.utils import timezone as django_tz
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from users.models import CustomUser
from tasks.models import (
    PriceGuide, Task, TaskCompletion, TaskRequest,
    CheckIn, LocationConsent, LocationPolicy, Dispute, AuditLog,
)
from payments.models import Transaction
from tasks import geo
from tasks.management.commands.run_scheduled_tasks import Command as ScheduledCmd


# ---------------------------------------------------------------------------
# Silence broadcast daemon threads across all tests in this module
# ---------------------------------------------------------------------------
_thread_patcher = patch('tasks.views.threading.Thread')
_matching_thread = patch('tasks.matching.threading.Thread')
_matching_timer = patch('tasks.matching.threading.Timer')
_matching_sched = patch('tasks.matching._schedule_next_round')


def setUpModule():
    _thread_patcher.start()
    _matching_thread.start()
    _matching_timer.start()
    _matching_sched.start()


def tearDownModule():
    _thread_patcher.stop()
    _matching_thread.stop()
    _matching_timer.stop()
    _matching_sched.stop()


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

# Kilimani, Nairobi (approximate)
TASK_LAT = Decimal('-1.292100')
TASK_LNG = Decimal('36.785600')
GEOFENCE_M = 150


class GeoTestBase(APITestCase):
    """Creates one household (task owner) and one student."""

    def setUp(self):
        PriceGuide.objects.create(
            category='Cleaning', min_price=300, max_price=800, recommended_price=500
        )
        self.household = CustomUser.objects.create_user(
            username='hh_geo', email='hh_geo@test.com', password='Pass1234!',
            role='HOUSEHOLD', phone_number='254711000111',
        )
        hp = self.household.household_profile
        hp.location_lat = TASK_LAT
        hp.location_lng = TASK_LNG
        hp.verification_status = 'Verified'
        hp.save()
        self.hh_token = Token.objects.create(user=self.household).key

        self.student = CustomUser.objects.create_user(
            username='st_geo', email='st_geo@test.com', password='Pass1234!',
            role='STUDENT', phone_number='254722000222',
        )
        sp = self.student.student_profile
        sp.verification_status = 'Verified'
        sp.categories_offered = ['Cleaning']
        sp.location_lat = TASK_LAT
        sp.location_lng = TASK_LNG
        sp.save()
        self.st_token = Token.objects.create(user=self.student).key

        self.admin = CustomUser.objects.create_user(
            username='admin_geo', email='admin_geo@test.com', password='Pass1234!',
            role='ADMIN',
        )
        self.admin_token = Token.objects.create(user=self.admin).key

    def _make_assigned_task(self, geofence_m=GEOFENCE_M):
        """Create a fully-funded (Assigned) task with start code and consent recorded."""
        task = Task.objects.create(
            household_owner=self.household,
            assigned_student=self.student,
            title='Geo Test Task',
            description='Test',
            category='Cleaning',
            posted_price=500,
            location_address='123 Test St, Kilimani, Nairobi',
            location_lat=TASK_LAT,
            location_lng=TASK_LNG,
            geofence_radius_m=geofence_m,
            location_pin_confirmed=True,
            status='Assigned',
        )
        Transaction.objects.create(
            task=task, amount=500, status='Held',
            mpesa_reference='MOCK_REF', checkout_request_id='MOCK_CID',
            phone_number='254711000111',
        )
        TaskCompletion.objects.create(task=task, start_code='4321')
        # Record consent so the consent gate does not block check-in
        LocationConsent.objects.get_or_create(
            student=self.student,
            defaults={'version': geo.LOCATION_CONSENT_VERSION},
        )
        return task

    def _checkin(self, task, payload, token=None):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {token or self.st_token}'
        )
        return self.client.post(
            f'/api/tasks/{task.id}/checkin/', payload, format='json'
        )


# ===========================================================================
# 1. Haversine distance calculation
# ===========================================================================

class TestHaversine(GeoTestBase):

    def test_distance_to_itself_is_zero(self):
        d = geo.haversine_m(TASK_LAT, TASK_LNG, TASK_LAT, TASK_LNG)
        self.assertAlmostEqual(d, 0.0, delta=0.001)

    def test_distance_nairobi_to_kisumu(self):
        # Nairobi (-1.286, 36.820) → Kisumu (-0.091, 34.767) ≈ 265 km
        d = geo.haversine_m(-1.286389, 36.817223, -0.091702, 34.767956)
        self.assertAlmostEqual(d / 1000, 265, delta=10)

    def test_exactly_100_metres_north(self):
        # Moving ~100 m north: 100 m / 111_320 m/deg ≈ 0.000898 deg
        new_lat = float(TASK_LAT) + 0.000898
        d = geo.haversine_m(TASK_LAT, TASK_LNG, new_lat, float(TASK_LNG))
        self.assertAlmostEqual(d, 100.0, delta=2.0)

    def test_haversine_accepts_decimal_inputs(self):
        d = geo.haversine_m(
            Decimal('-1.292100'), Decimal('36.785600'),
            Decimal('-1.292100'), Decimal('36.785600'),
        )
        self.assertAlmostEqual(d, 0.0, delta=0.001)


# ===========================================================================
# 2. Inside the geofence → VERIFIED
# ===========================================================================

class TestVerifiedCheckin(GeoTestBase):

    def test_checkin_inside_geofence_is_verified(self):
        task = self._make_assigned_task()
        # Student is at the same point as the task pin (distance ≈ 0)
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
            'device_time': django_tz.now().isoformat(),
            'mock_location': False,
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'VERIFIED')
        self.assertFalse(res.data['flagged'])

        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        ci = CheckIn.objects.get(task=task, type='START')
        self.assertEqual(ci.result, 'VERIFIED')
        self.assertAlmostEqual(ci.distance_m, 0.0, delta=5.0)
        self.assertFalse(ci.mock_location_flag)

    def test_checkin_moves_task_to_inprogress(self):
        task = self._make_assigned_task()
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 20.0,
            'device_time': django_tz.now().isoformat(),
        })
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

    def test_checkin_records_arrival_timestamp(self):
        task = self._make_assigned_task()
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        completion = TaskCompletion.objects.get(task=task)
        self.assertIsNotNone(completion.arrived_at)
        self.assertIsNotNone(completion.started_at)
        self.assertTrue(completion.start_code_verified)

    def test_checkin_at_edge_of_geofence_still_verified(self):
        # 149 m away — just inside a 150-m geofence
        new_lat = float(TASK_LAT) + 0.001339  # ~149 m north
        task = self._make_assigned_task(geofence_m=150)
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': new_lat,
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'VERIFIED')


# ===========================================================================
# 3. Outside the geofence → OUT_OF_RANGE (allowed, flagged)
# ===========================================================================

class TestOutOfRange(GeoTestBase):

    def test_checkin_outside_geofence_is_flagged_but_allowed(self):
        # Move student 500 m away (well outside 150 m geofence)
        far_lat = float(TASK_LAT) + 0.0045  # ~500 m north
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': far_lat,
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'OUT_OF_RANGE')
        self.assertTrue(res.data['flagged'])
        self.assertTrue(res.data['retry_allowed'])

        # Task still moves to InProgress (check-in is accepted)
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        ci = CheckIn.objects.get(task=task, type='START')
        self.assertEqual(ci.result, 'OUT_OF_RANGE')
        self.assertGreater(ci.distance_m, 150.0)

    def test_audit_log_records_flagged_checkin(self):
        far_lat = float(TASK_LAT) + 0.0045
        task = self._make_assigned_task()
        self._checkin(task, {
            'start_code': '4321',
            'lat': far_lat,
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        log = AuditLog.objects.filter(
            task=task, to_status='InProgress'
        ).first()
        self.assertIsNotNone(log)
        self.assertIn('OUT_OF_RANGE', log.notes)


# ===========================================================================
# 4. Low GPS accuracy → LOW_ACCURACY (allowed, flagged)
# ===========================================================================

class TestLowAccuracy(GeoTestBase):

    def test_low_accuracy_is_flagged_but_allowed(self):
        policy = LocationPolicy.get()
        policy.low_accuracy_threshold_m = 50
        policy.save()

        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 200.0,  # worse than 50 m threshold
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'LOW_ACCURACY')
        self.assertTrue(res.data['flagged'])

    def test_good_accuracy_passes(self):
        policy = LocationPolicy.get()
        policy.low_accuracy_threshold_m = 100
        policy.save()

        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 15.0,  # well within 100 m threshold
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'VERIFIED')

    def test_missing_accuracy_does_not_block(self):
        """accuracy_m is optional — absent accuracy should not cause LOW_ACCURACY."""
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            # accuracy_m intentionally omitted
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'VERIFIED')


# ===========================================================================
# 5. Location permission denied (no coordinates) → LOCATION_DENIED
# ===========================================================================

class TestLocationDenied(GeoTestBase):

    def test_no_coordinates_produces_location_denied(self):
        """Submitting a check-in without coordinates means permission was denied."""
        policy = LocationPolicy.get()
        policy.allow_flagged_when_denied = False
        policy.save()

        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            # lat / lng intentionally absent
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['result'], 'LOCATION_DENIED')
        # Task must NOT have moved
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')

    def test_location_denied_allowed_when_policy_permits(self):
        """Admin can enable flagged check-ins even when permission is denied."""
        policy = LocationPolicy.get()
        policy.allow_flagged_when_denied = True
        policy.save()

        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            # no coordinates
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'LOCATION_DENIED')
        self.assertTrue(res.data['flagged'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')


# ===========================================================================
# 6. Mock / simulated location → FLAGGED_MOCK (rejected, 400)
# ===========================================================================

class TestMockLocation(GeoTestBase):

    def test_mock_location_is_rejected(self):
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 5.0,
            'mock_location': True,  # Android: isMockLocationEnabled
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['result'], 'FLAGGED_MOCK')
        # Task must remain Assigned
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')

    def test_mock_location_flag_stored_in_checkin(self):
        task = self._make_assigned_task()
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'mock_location': True,
        })
        ci = CheckIn.objects.filter(task=task).first()
        self.assertIsNotNone(ci)
        self.assertTrue(ci.mock_location_flag)
        self.assertEqual(ci.result, 'FLAGGED_MOCK')

    def test_mock_flag_false_does_not_block(self):
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
            'mock_location': False,
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'VERIFIED')


# ===========================================================================
# 7. Offline / late sync
# ===========================================================================

class TestLateSync(GeoTestBase):

    def test_late_sync_flag_is_stored(self):
        """Check-in submitted with late_sync=True should be flagged in the DB."""
        task = self._make_assigned_task()
        # Use a device_time well in the past (simulate offline queue)
        past_device_time = (django_tz.now() - timedelta(hours=2)).isoformat()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 20.0,
            'device_time': past_device_time,
            'late_sync': True,
        })
        self.assertEqual(res.status_code, 200)
        ci = CheckIn.objects.get(task=task, type='START')
        self.assertTrue(ci.late_sync_flag)

    def test_large_time_skew_triggers_late_sync_even_without_flag(self):
        """A device time >max_skew seconds in the past counts as a late sync."""
        policy = LocationPolicy.get()
        policy.max_time_skew_seconds = 300
        policy.save()

        task = self._make_assigned_task()
        past_device_time = (django_tz.now() - timedelta(minutes=10)).isoformat()
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 20.0,
            'device_time': past_device_time,
            'late_sync': False,  # client did not flag it
        })
        ci = CheckIn.objects.get(task=task, type='START')
        # The server computes late_sync from skew
        self.assertTrue(ci.late_sync_flag)


# ===========================================================================
# 8. Wrong start code with a correct location
# ===========================================================================

class TestWrongCode(GeoTestBase):

    def test_wrong_code_rejected_even_with_correct_location(self):
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '0000',  # wrong
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 5.0,
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['result'], 'WRONG_CODE')
        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')  # unchanged

    def test_wrong_code_stored_in_checkin_with_location(self):
        task = self._make_assigned_task()
        self._checkin(task, {
            'start_code': '9999',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 5.0,
        })
        ci = CheckIn.objects.filter(task=task).first()
        self.assertIsNotNone(ci)
        self.assertEqual(ci.result, 'WRONG_CODE')
        self.assertIsNotNone(ci.lat)  # location was submitted and stored

    def test_multiple_wrong_codes_all_recorded(self):
        task = self._make_assigned_task()
        for _ in range(3):
            self._checkin(task, {'start_code': '1111'})
        self.assertEqual(CheckIn.objects.filter(task=task, result='WRONG_CODE').count(), 3)


# ===========================================================================
# 9. Access control: only the assigned student may check in
# ===========================================================================

class TestCheckinAccessControl(GeoTestBase):

    def test_household_cannot_checkin(self):
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
        }, token=self.hh_token)
        self.assertEqual(res.status_code, 403)

    def test_other_student_cannot_checkin(self):
        other = CustomUser.objects.create_user(
            username='other_st', email='other@test.com', password='Pass1234!',
            role='STUDENT',
        )
        other_token = Token.objects.create(user=other).key
        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
        }, token=other_token)
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_cannot_checkin(self):
        task = self._make_assigned_task()
        self.client.credentials()  # clear token
        res = self.client.post(
            f'/api/tasks/{task.id}/checkin/',
            {'start_code': '4321'},
            format='json',
        )
        self.assertEqual(res.status_code, 401)

    def test_location_audit_requires_admin(self):
        task = self._make_assigned_task()
        # Household — denied
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, 403)
        # Student — denied
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, 403)
        # Admin — allowed
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, 200)

    def test_location_audit_includes_checkin_data(self):
        task = self._make_assigned_task()
        # Place a check-in
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        res = self.client.get(f'/api/tasks/{task.id}/location-audit/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['checkins']), 1)
        self.assertEqual(res.data['checkins'][0]['result'], 'VERIFIED')
        # Admin sees exact task pin coordinates
        self.assertIsNotNone(res.data['task']['location_lat'])
        self.assertIsNotNone(res.data['task']['location_lng'])


# ===========================================================================
# 10. Impossible jump detection
# ===========================================================================

class TestImpossibleJump(GeoTestBase):

    def test_impossible_jump_flag_set_when_speed_exceeds_policy(self):
        """
        Plant a previous check-in far from the task location with a
        server_time 1 second ago, then check in at the task location.
        Mombasa → Nairobi ≈ 480 km in 1 second = impossible.
        """
        policy = LocationPolicy.get()
        policy.max_speed_mps = 55  # 200 km/h max
        policy.save()

        task = self._make_assigned_task()

        # Backdate the previous check-in to 1 second ago so the implied
        # travel speed is enormous
        one_sec_ago = django_tz.now() - timedelta(seconds=1)
        ci_prev = CheckIn.objects.create(
            task=task,
            student=self.student,
            type='ARRIVAL',
            lat=Decimal('-4.043477'),  # Mombasa
            lng=Decimal('39.668207'),
            accuracy_m=10.0,
            distance_m=50.0,
            result='WRONG_CODE',
        )
        # Force server_time back to 1 second ago
        CheckIn.objects.filter(pk=ci_prev.pk).update(server_time=one_sec_ago)

        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        ci = CheckIn.objects.filter(task=task, type='START').first()
        self.assertIsNotNone(ci)
        self.assertTrue(ci.impossible_jump_flag)


# ===========================================================================
# 11. Time skew detection
# ===========================================================================

class TestTimeSkew(GeoTestBase):

    def test_time_skew_stored_in_checkin(self):
        task = self._make_assigned_task()
        # Provide a device time 90 seconds in the past
        device_time = (django_tz.now() - timedelta(seconds=90)).isoformat()
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
            'device_time': device_time,
        })
        ci = CheckIn.objects.get(task=task, type='START')
        # Skew should be approximately 90 seconds
        self.assertIsNotNone(ci.time_skew_seconds)
        self.assertAlmostEqual(ci.time_skew_seconds, 90, delta=10)


# ===========================================================================
# 12. Approximate-coords privacy
# ===========================================================================

class TestApproximateCoords(GeoTestBase):

    def test_approximate_coords_differ_from_true_pin(self):
        approx_lat, approx_lng = geo.approximate_coords(TASK_LAT, TASK_LNG, seed='test-1')
        self.assertNotAlmostEqual(float(approx_lat), float(TASK_LAT), places=3)

    def test_approximate_coords_are_deterministic(self):
        a1 = geo.approximate_coords(TASK_LAT, TASK_LNG, seed='same-seed')
        a2 = geo.approximate_coords(TASK_LAT, TASK_LNG, seed='same-seed')
        self.assertEqual(a1, a2)

    def test_different_seeds_give_different_offsets(self):
        a1 = geo.approximate_coords(TASK_LAT, TASK_LNG, seed='seed-A')
        a2 = geo.approximate_coords(TASK_LAT, TASK_LNG, seed='seed-B')
        self.assertNotEqual(a1, a2)

    def test_approximate_offset_is_within_bounds(self):
        approx_lat, approx_lng = geo.approximate_coords(TASK_LAT, TASK_LNG, seed='bounds-test')
        dist = geo.haversine_m(TASK_LAT, TASK_LNG, approx_lat, approx_lng)
        # Must be at least 200 m away (minimum blur) and no more than 400 m away
        self.assertGreaterEqual(dist, geo.APPROX_MIN_OFFSET_M - 10)  # allow rounding
        self.assertLessEqual(dist, geo.APPROX_MAX_OFFSET_M + 100)

    def test_non_privileged_viewer_sees_blurred_coords(self):
        """A student who is NOT yet assigned sees approximate coordinates."""
        task = Task.objects.create(
            household_owner=self.household,
            title='Privacy Test Task',
            description='Test',
            category='Cleaning',
            posted_price=500,
            location_address='123 Test St, Kilimani, Nairobi',
            location_lat=TASK_LAT,
            location_lng=TASK_LNG,
            geofence_radius_m=150,
            location_pin_confirmed=True,
            status='Broadcasting',
        )
        # Student with no assignment retrieves task detail
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 200)
        # location_lat / location_lng should be blurred (not equal to true pin at 6 decimal places)
        lat = res.data.get('location_lat')
        self.assertIsNotNone(lat)
        # True pin is -1.292100; blurred must differ by at least 0.001 degrees (~110 m)
        self.assertFalse(
            abs(float(lat) - float(TASK_LAT)) < 0.001,
            f"Expected blurred lat to differ from {TASK_LAT} by >0.001, got {lat}"
        )
        # location_address_full must be hidden
        self.assertIsNone(res.data.get('location_address_full'))

    def test_household_owner_sees_exact_coords(self):
        task = Task.objects.create(
            household_owner=self.household,
            title='Exact Coords Test',
            description='Test',
            category='Cleaning',
            posted_price=500,
            location_address='123 Test St, Kilimani, Nairobi',
            location_lat=TASK_LAT,
            location_lng=TASK_LNG,
            geofence_radius_m=150,
            location_pin_confirmed=True,
            status='Posted',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.hh_token}')
        res = self.client.get(f'/api/tasks/{task.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertAlmostEqual(float(res.data['location_lat']), float(TASK_LAT), places=4)
        self.assertEqual(res.data.get('location_address_full'), '123 Test St, Kilimani, Nairobi')


# ===========================================================================
# 13. Retention job: anonymises coordinates, skips open disputes
# ===========================================================================

class TestRetentionJob(GeoTestBase):

    def _checkin_row(self, task, result='VERIFIED', days_ago=0):
        ci = CheckIn.objects.create(
            task=task,
            student=self.student,
            type='START',
            lat=TASK_LAT,
            lng=TASK_LNG,
            accuracy_m=10.0,
            distance_m=0.0,
            result=result,
        )
        if days_ago:
            # Backdate server_time
            past = django_tz.now() - timedelta(days=days_ago)
            CheckIn.objects.filter(pk=ci.pk).update(server_time=past)
        return ci

    def test_old_coordinates_are_anonymised(self):
        policy = LocationPolicy.get()
        policy.retention_days = 30
        policy.save()

        task = self._make_assigned_task()
        ci = self._checkin_row(task, days_ago=31)  # 31 days old — past cutoff

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_location_retention(django_tz.now())

        ci.refresh_from_db()
        self.assertIsNone(ci.lat)
        self.assertIsNone(ci.lng)
        self.assertIsNotNone(ci.anonymised_at)

    def test_recent_coordinates_are_not_anonymised(self):
        policy = LocationPolicy.get()
        policy.retention_days = 90
        policy.save()

        task = self._make_assigned_task()
        ci = self._checkin_row(task, days_ago=10)  # only 10 days old

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_location_retention(django_tz.now())

        ci.refresh_from_db()
        self.assertIsNotNone(ci.lat)
        self.assertIsNone(ci.anonymised_at)

    def test_open_dispute_delays_anonymisation(self):
        policy = LocationPolicy.get()
        policy.retention_days = 30
        policy.save()

        task = self._make_assigned_task()
        # Place old check-in
        ci = self._checkin_row(task, days_ago=31)
        # Create an OPEN dispute (no resolved_at)
        Dispute.objects.create(
            task=task,
            raised_by=self.household,
            reason='poor_quality',
            description='Not done.',
            # resolved_at intentionally not set
        )

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_location_retention(django_tz.now())

        ci.refresh_from_db()
        # Coordinates should be retained while the dispute is open
        self.assertIsNotNone(ci.lat)

    def test_resolved_dispute_allows_anonymisation(self):
        policy = LocationPolicy.get()
        policy.retention_days = 30
        policy.save()

        task = self._make_assigned_task()
        ci = self._checkin_row(task, days_ago=31)
        # Create a RESOLVED dispute
        Dispute.objects.create(
            task=task,
            raised_by=self.household,
            reason='poor_quality',
            description='Not done.',
            resolved_at=django_tz.now(),  # resolved
        )

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_location_retention(django_tz.now())

        ci.refresh_from_db()
        self.assertIsNone(ci.lat)
        self.assertIsNotNone(ci.anonymised_at)

    def test_idempotent_retention_does_not_double_anonymise(self):
        policy = LocationPolicy.get()
        policy.retention_days = 1
        policy.save()

        task = self._make_assigned_task()
        ci = self._checkin_row(task, days_ago=2)

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_location_retention(django_tz.now())
        cmd._handle_location_retention(django_tz.now())  # run again

        self.assertEqual(
            CheckIn.objects.filter(task=task, anonymised_at__isnull=False).count(), 1
        )


# ===========================================================================
# 14. Consent gate
# ===========================================================================

class TestConsentGate(GeoTestBase):

    def test_checkin_blocked_without_consent(self):
        # Remove any consent that the base class set up
        LocationConsent.objects.filter(student=self.student).delete()

        task = self._make_assigned_task()
        # _make_assigned_task also re-creates consent — delete it again
        LocationConsent.objects.filter(student=self.student).delete()

        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
        })
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data.get('code'), 'consent_required')

    def test_checkin_allowed_after_consent(self):
        # Grant consent via the API
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        self.client.post(
            '/api/geo/consent/',
            {'version': geo.LOCATION_CONSENT_VERSION},
            format='json',
        )

        task = self._make_assigned_task()
        res = self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        self.assertEqual(res.status_code, 200)

    def test_consent_endpoint_records_version(self):
        LocationConsent.objects.filter(student=self.student).delete()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.post(
            '/api/geo/consent/',
            {'version': '1.0'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['consented'])
        consent = LocationConsent.objects.get(student=self.student)
        self.assertEqual(consent.version, '1.0')

    def test_consent_get_returns_notice_text(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.st_token}')
        res = self.client.get('/api/geo/consent/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text', res.data)
        self.assertTrue(len(res.data['text']) > 50)
        self.assertIn('version', res.data)


# ===========================================================================
# 15. Retry after a flagged check-in
# ===========================================================================

class TestRetryCheckin(GeoTestBase):

    def test_student_can_retry_after_out_of_range(self):
        """After a flagged check-in (OUT_OF_RANGE), student can retry with
        a better position (no start code needed on retry)."""
        task = self._make_assigned_task()
        # First check-in: out of range
        far_lat = float(TASK_LAT) + 0.0045
        self._checkin(task, {
            'start_code': '4321',
            'lat': far_lat,
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        task.refresh_from_db()
        self.assertEqual(task.status, 'InProgress')

        # Retry at the correct location (no start_code needed)
        res = self._checkin(task, {
            'start_code': '',  # empty on retry
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['result'], 'VERIFIED')
        self.assertFalse(res.data['started'])  # already started, not re-transitioned

    def test_retry_blocked_when_already_verified(self):
        task = self._make_assigned_task()
        # First check-in: verified
        self._checkin(task, {
            'start_code': '4321',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
            'accuracy_m': 10.0,
        })
        # Attempt retry
        task.refresh_from_db()
        # Build a checkin_summary-like state: checkins(type=START, result=VERIFIED)
        res = self._checkin(task, {
            'start_code': '',
            'lat': float(TASK_LAT),
            'lng': float(TASK_LNG),
        })
        self.assertEqual(res.status_code, 400)


# ===========================================================================
# 16. evaluate_checkin unit tests (pure Python)
# ===========================================================================

class TestEvaluateCheckinUnit(GeoTestBase):
    """Unit tests for geo.evaluate_checkin that don't need a live HTTP server."""

    def _policy(self, **kwargs):
        policy = LocationPolicy.get()
        for k, v in kwargs.items():
            setattr(policy, k, v)
        policy.save()
        return policy

    def _task(self, geofence_m=150):
        return Task(
            location_lat=TASK_LAT,
            location_lng=TASK_LNG,
            geofence_radius_m=geofence_m,
        )

    def test_verified_inside_geofence(self):
        policy = self._policy(low_accuracy_threshold_m=100, max_time_skew_seconds=300)
        result = geo.evaluate_checkin(
            self._task(), float(TASK_LAT), float(TASK_LNG),
            accuracy_m=10.0, mock_location=False, device_time=None, policy=policy,
        )
        self.assertEqual(result['result'], 'VERIFIED')

    def test_out_of_range_outside_geofence(self):
        policy = self._policy(low_accuracy_threshold_m=100)
        far_lat = float(TASK_LAT) + 0.0045  # ~500 m north
        result = geo.evaluate_checkin(
            self._task(), far_lat, float(TASK_LNG),
            accuracy_m=10.0, mock_location=False, device_time=None, policy=policy,
        )
        self.assertEqual(result['result'], 'OUT_OF_RANGE')
        self.assertGreater(result['distance_m'], 150)

    def test_low_accuracy_flagged(self):
        policy = self._policy(low_accuracy_threshold_m=50)
        result = geo.evaluate_checkin(
            self._task(), float(TASK_LAT), float(TASK_LNG),
            accuracy_m=200.0, mock_location=False, device_time=None, policy=policy,
        )
        self.assertEqual(result['result'], 'LOW_ACCURACY')

    def test_mock_location_wins_over_distance(self):
        """FLAGGED_MOCK is returned even when inside geofence."""
        policy = self._policy()
        result = geo.evaluate_checkin(
            self._task(), float(TASK_LAT), float(TASK_LNG),
            accuracy_m=5.0, mock_location=True, device_time=None, policy=policy,
        )
        self.assertEqual(result['result'], 'FLAGGED_MOCK')

    def test_missing_coordinates_returns_location_denied(self):
        policy = self._policy()
        result = geo.evaluate_checkin(
            self._task(), None, None,
            accuracy_m=None, mock_location=False, device_time=None, policy=policy,
        )
        self.assertEqual(result['result'], 'LOCATION_DENIED')

    def test_legacy_task_without_pin_always_verified(self):
        """Tasks created before geolocation (no lat/lng) pass with VERIFIED."""
        task_no_pin = Task(location_lat=None, location_lng=None, geofence_radius_m=150)
        policy = self._policy()
        result = geo.evaluate_checkin(
            task_no_pin, float(TASK_LAT), float(TASK_LNG),
            accuracy_m=10.0, mock_location=False, device_time=None, policy=policy,
        )
        self.assertEqual(result['result'], 'VERIFIED')
        self.assertIsNone(result['distance_m'])


# ===========================================================================
# 17. No-show uses CheckIn (integration with run_scheduled_tasks)
# ===========================================================================

class TestNoShowWithCheckin(GeoTestBase):

    def test_no_show_not_flagged_when_verified_checkin_exists(self):
        """A VERIFIED check-in prevents the no-show flag."""
        from datetime import datetime, timezone as dt_tz
        past_time = (django_tz.now() - timedelta(minutes=35)).time()
        task = self._make_assigned_task()
        task.scheduled_date = django_tz.now().date()
        task.scheduled_time = past_time
        task.save()
        # Place a verified START check-in
        CheckIn.objects.create(
            task=task,
            student=self.student,
            type='START',
            result='VERIFIED',
        )

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_no_shows(django_tz.now())

        task.refresh_from_db()
        self.assertEqual(task.status, 'Assigned')  # not NoShow

    def test_no_show_flagged_when_no_verified_checkin(self):
        from datetime import datetime, timezone as dt_tz
        past_time = (django_tz.now() - timedelta(minutes=35)).time()
        task = self._make_assigned_task()
        task.scheduled_date = django_tz.now().date()
        task.scheduled_time = past_time
        task.save()
        # Only a wrong-code attempt — no verified arrival
        CheckIn.objects.create(
            task=task,
            student=self.student,
            type='ARRIVAL',
            result='WRONG_CODE',
        )

        cmd = ScheduledCmd()
        cmd.stdout = MagicMock()
        cmd._handle_no_shows(django_tz.now())

        task.refresh_from_db()
        self.assertEqual(task.status, 'NoShow')
