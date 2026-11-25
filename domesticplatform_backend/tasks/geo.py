"""
Geolocation helpers for check-in verification.

All distance maths lives here so it can be unit-tested independently of the
API layer.  Coordinates are captured ONLY at explicit check-in/finish events
(see CheckIn model) — never continuously in the background.
"""

import hashlib
import math
from datetime import datetime, timedelta

from django.utils import timezone as django_tz

# Mean Earth radius in metres
EARTH_RADIUS_M = 6371000.0

# How far the "approximate area" centre may sit from the true pin (metres)
APPROX_MAX_OFFSET_M = 400.0
# Decimal places kept on approximate coordinates (~111 m per 0.001 deg lat)
APPROX_DECIMALS = 3

# Version of the location-collection consent notice.  Bump when the wording
# changes materially — students must re-consent against the new version.
LOCATION_CONSENT_VERSION = '1.0'
LOCATION_CONSENT_TEXT = (
    "When you check in to start or finish a task, this app collects your "
    "device's GPS position (latitude, longitude and accuracy) once, at the "
    "moment you submit the start code. The purpose is to confirm that you "
    "are at the task location and to protect both you and the household "
    "against disputes. Your location is never tracked in the background, "
    "is only visible to platform administrators, and is automatically "
    "deleted or anonymised after the retention period (default 90 days, "
    "longer if a dispute is open). The household only sees that you "
    "arrived and that your location was verified — never your coordinates. "
    "Location data is transmitted over an encrypted connection. You can "
    "refuse location permission, but check-in may then be blocked."
)


def haversine_m(lat1, lng1, lat2, lng2):
    """
    Great-circle distance between two (lat, lng) points in metres.
    Accepts Decimal or float inputs.
    """
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lng2) - float(lng1))

    a = (math.sin(dphi / 2.0) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


# Minimum blur distance from the true pin (metres).  Rounding to 3 decimals
# moves the point by up to ~78 m, so 200 m guarantees the published
# approximate point stays >120 m away from the real pin.
APPROX_MIN_OFFSET_M = 200.0


def _seeded_offset_m(seed):
    """Deterministic pseudo-random (dx, dy) metre offsets derived from `seed`.

    Magnitude is bounded to [APPROX_MIN_OFFSET_M, APPROX_MAX_OFFSET_M] so the
    blurred point always hides the true pin but stays in the same
    neighbourhood (roughly the same area label).
    """
    digest = hashlib.sha256(str(seed).encode('utf-8')).hexdigest()
    # Two independent 8-hex-digit chunks scaled to [-1, 1)
    def unit(chunk):
        return (int(chunk, 16) / 16 ** 8) * 2.0 - 1.0
    dx = unit(digest[:8]) * APPROX_MAX_OFFSET_M
    dy = unit(digest[8:16]) * APPROX_MAX_OFFSET_M
    mag = math.hypot(dx, dy)
    if mag < APPROX_MIN_OFFSET_M:
        if mag == 0:
            dx, dy = APPROX_MIN_OFFSET_M, 0.0
        else:
            scale = APPROX_MIN_OFFSET_M / mag
            dx, dy = dx * scale, dy * scale
    return dx, dy


def approximate_coords(lat, lng, seed):
    """
    Blur a coordinate into an approximate area centre.

    The offset is deterministic for a given `seed` (e.g. task id) so the same
    task always shows the same approximate area, but the true pin cannot be
    recovered from the blurred value.  Result is rounded to 3 decimals
    (~110 m granularity) and offset by up to ~400 m.
    """
    dx_m, dy_m = _seeded_offset_m(seed)
    # metres → degrees (approximate, fine for blurring)
    dlat = dy_m / 111320.0
    dlng = dx_m / (111320.0 * math.cos(math.radians(float(lat))) or 1.0)
    approx_lat = round(float(lat) + dlat, APPROX_DECIMALS)
    approx_lng = round(float(lng) + dlng, APPROX_DECIMALS)
    return approx_lat, approx_lng


def approximate_area_label(address):
    """
    Coarse text label for a task address, e.g.
    '123 Riverside Drive, Kilimani, Nairobi' → 'Kilimani, Nairobi'.
    Used for students who have not been assigned/paid yet.
    """
    if not address:
        return ''
    parts = [p.strip() for p in address.split(',')]
    return ', '.join(parts[1:]) if len(parts) > 1 else parts[0]


def parse_bool(value):
    """
    Parse a boolean from JSON (true/false) or multipart form data
    ('true'/'false' strings) without the bool('false') trap.
    """
    if value is None or value == '':
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def parse_device_time(value):
    """
    Parse a device timestamp (ISO 8601 string or epoch seconds/ms) to an
    aware datetime.  Returns None when unparseable.
    """
    if value is None or value == '':
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            # Heuristic: epoch milliseconds vs seconds
            if ts > 1e12:
                ts = ts / 1000.0
            dt = datetime.fromtimestamp(ts, tz=django_tz.get_current_timezone())
        else:
            text = str(value).strip().replace('Z', '+00:00')
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=django_tz.utc)
        return dt
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def evaluate_checkin(task, lat, lng, accuracy_m, mock_location,
                     device_time, policy, previous_checkin=None):
    """
    Decide the check-in result for a submitted position.

    Returns a dict:
        result        VERIFIED | OUT_OF_RANGE | LOW_ACCURACY | LOCATION_DENIED
                      | FLAGGED_MOCK
        distance_m    Haversine distance to the task pin (None if unknown)
        time_skew_s   |server_time - device_time| (None if no device time)
        impossible_jump  True if the jump from previous_checkin is implausible
    """
    now = django_tz.now()

    # --- Time skew (anti-spoofing) -------------------------------------
    time_skew_s = None
    if device_time is not None:
        time_skew_s = abs((now - device_time).total_seconds())

    # --- Impossible jump (anti-spoofing) --------------------------------
    impossible_jump = False
    if previous_checkin is not None and previous_checkin.lat is not None and lat is not None:
        prev_dt = previous_checkin.device_time or previous_checkin.server_time
        dt_s = max((now - prev_dt).total_seconds(), 1.0)
        dist = haversine_m(previous_checkin.lat, previous_checkin.lng, lat, lng)
        speed_mps = dist / dt_s
        if speed_mps > policy.max_speed_mps:
            impossible_jump = True

    # --- Mock location (anti-spoofing, Android) ------------------------
    if mock_location:
        return {
            'result': 'FLAGGED_MOCK',
            'distance_m': _distance_or_none(task, lat, lng),
            'time_skew_s': time_skew_s,
            'impossible_jump': impossible_jump,
        }

    # --- Permission denied / missing coordinates -----------------------
    if lat is None or lng is None:
        return {
            'result': 'LOCATION_DENIED',
            'distance_m': None,
            'time_skew_s': time_skew_s,
            'impossible_jump': False,
        }

    # --- Legacy tasks without a pin cannot be distance-checked ----------
    if task.location_lat is None or task.location_lng is None:
        return {
            'result': 'VERIFIED',
            'distance_m': None,
            'time_skew_s': time_skew_s,
            'impossible_jump': impossible_jump,
        }

    distance = haversine_m(task.location_lat, task.location_lng, lat, lng)

    # --- Accuracy gate ---------------------------------------------------
    if accuracy_m is not None and accuracy_m > policy.low_accuracy_threshold_m:
        return {
            'result': 'LOW_ACCURACY',
            'distance_m': distance,
            'time_skew_s': time_skew_s,
            'impossible_jump': impossible_jump,
        }

    # --- Geofence gate ---------------------------------------------------
    if distance > (task.geofence_radius_m or 150):
        return {
            'result': 'OUT_OF_RANGE',
            'distance_m': distance,
            'time_skew_s': time_skew_s,
            'impossible_jump': impossible_jump,
        }

    return {
        'result': 'VERIFIED',
        'distance_m': distance,
        'time_skew_s': time_skew_s,
        'impossible_jump': impossible_jump,
    }


def _distance_or_none(task, lat, lng):
    if lat is None or lng is None or task.location_lat is None or task.location_lng is None:
        return None
    return haversine_m(task.location_lat, task.location_lng, lat, lng)


def is_late_sync(device_time, client_flag, max_skew_seconds):
    """A check-in counts as a late (offline) sync when the client queued it
    or the device timestamp is far behind the server clock."""
    if client_flag:
        return True
    if device_time is None:
        return False
    skew = abs((django_tz.now() - device_time).total_seconds())
    return skew > max_skew_seconds
