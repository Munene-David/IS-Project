"""
Demo setup script — creates a rich, realistic dataset centred on
Strathmore University, Nairobi (-1.3100, 36.8126).

Run once:
    python setup_demo.py

Accounts created (all password: demo1234)
------------------------------------------
HOUSEHOLD
  sarah_m       — Verified, Madaraka Estate (600 m from Strathmore)
  james_o       — Verified, Ngong Road (1.2 km)
  grace_w       — Verified, Adams Arcade (1.8 km)

STUDENTS  (Verified, 4–5 ★, within 2 km of Strathmore)
  alice_k       — 5★, 200 m south   — Cleaning, Cooking
  brian_m       — 4.5★, 400 m east  — Cleaning, Laundry
  carol_n       — 4★, 700 m north   — Childcare, Cooking
  david_o       — 4.5★, 1.0 km SW   — Cleaning, Gardening
  eve_w         — 4★, 1.5 km SE     — Laundry, Errands

STUDENTS  (Verified, 0 ratings — new joiners near Strathmore)
  frank_k       — 0★, 300 m NW
  grace_s       — 0★, 500 m NE

ADMIN
  admin         — platform admin (unchanged if already exists)

Scenario tasks
--------------
  1. ASSIGNED task owned by sarah_m → alice_k (escrow Held, start code 7391)
     → Demonstrates: student who has the job, start-code check-in flow

  2. NOSHOW task owned by james_o → brian_m (scheduled 35 min ago, no check-in)
     → Demonstrates: no-show detection

  3. BROADCASTING task owned by grace_w
     → Demonstrates: multiple students receiving the broadcast simultaneously

  4. COMPLETED task (sarah_m → carol_n) with ratings
  5. DISPUTED task (james_o → david_o)
"""

import os, sys, django
from datetime import date, time, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from django.utils import timezone as tz
from django.db import transaction as db_tx
from rest_framework.authtoken.models import Token

from users.models import CustomUser, StudentProfile, HouseholdProfile
from users.notifications import Notification
from tasks.models import (
    Task, TaskCompletion, TaskRequest, PriceGuide,
    CheckIn, LocationConsent, LocationPolicy, Dispute, AuditLog,
    CancellationPolicy,
)
from payments.models import Transaction, TransactionLedger, Rating

# ---------------------------------------------------------------------------
# Strathmore University coordinates
# ---------------------------------------------------------------------------
STRATH_LAT = -1.3100
STRATH_LNG = 36.8126

PW = 'demo1234'

def offset(dlat, dlng):
    return round(STRATH_LAT + dlat, 6), round(STRATH_LNG + dlng, 6)


# ---------------------------------------------------------------------------
# 1. Price guides
# ---------------------------------------------------------------------------
print('\n── Price guides ──')
for cat, lo, hi, rec in [
    ('Cleaning', 300, 800, 500),
    ('Cooking',  400, 900, 600),
    ('Laundry',  200, 600, 400),
    ('Childcare',500, 1200,800),
    ('Gardening',300, 700, 500),
    ('Errands',  200, 500, 350),
]:
    PriceGuide.objects.update_or_create(
        category=cat,
        defaults={'min_price': lo, 'max_price': hi, 'recommended_price': rec},
    )
    print(f'  {cat}')

# ---------------------------------------------------------------------------
# 2. Helper functions
# ---------------------------------------------------------------------------

def make_user(username, role, first, last, phone, password=PW):
    u, created = CustomUser.objects.get_or_create(
        username=username,
        defaults={
            'email': f'{username}@demo.ac.ke',
            'role': role,
            'first_name': first,
            'last_name': last,
            'phone_number': phone,
        }
    )
    u.set_password(password)
    u.save()
    Token.objects.get_or_create(user=u)
    return u, created


def setup_student(u, lat, lng, categories, verification='Verified'):
    sp = u.student_profile
    sp.location_lat = lat
    sp.location_lng = lng
    sp.categories_offered = categories
    sp.verification_status = verification
    sp.availability_status = True
    sp.save()
    return sp


def setup_household(u, lat, lng, address, verification='Verified'):
    hp = u.household_profile
    hp.location_lat = lat
    hp.location_lng = lng
    hp.address = address
    hp.verification_status = verification
    hp.min_rating = 0
    hp.search_radius_km = 5
    hp.save()
    return hp


def add_rating(task, rater, rated, score, comment):
    Rating.objects.get_or_create(
        task=task, rater=rater, rated_user=rated,
        defaults={'score': score, 'comment': comment}
    )


def give_ratings(student, scores_comments):
    """Create synthetic ratings from disposable household accounts."""
    for i, (score, comment) in enumerate(scores_comments):
        rater_name = f'rater_{student.username}_{i}'
        rater, _ = make_user(rater_name, 'HOUSEHOLD', 'Demo', 'Rater',
                             f'2547000{i:05d}')
        hh_task = Task.objects.create(
            household_owner=rater,
            assigned_student=student,
            title=f'Past task for {student.first_name}',
            description='Historical task for rating',
            category=student.student_profile.categories_offered[0],
            posted_price=500,
            location_lat=STRATH_LAT, location_lng=STRATH_LNG,
            location_pin_confirmed=True,
            status='Completed',
        )
        add_rating(hh_task, rater, student, score, comment)
    avg = Rating.calculate_average(student)
    print(f'    {student.username}: avg={avg}★')


# ---------------------------------------------------------------------------
# 3. Household accounts
# ---------------------------------------------------------------------------
print('\n── Households ──')
sarah, _ = make_user('sarah_m', 'HOUSEHOLD', 'Sarah', 'Mwangi', '254711000001')
setup_household(sarah, *offset(-0.0054, 0.0020), 'Madaraka Estate, Nairobi')
print(f'  sarah_m {"(new)" if _ else "(updated)"}')

james, _ = make_user('james_o', 'HOUSEHOLD', 'James', 'Otieno', '254711000002')
setup_household(james, *offset(-0.0030, -0.0120), '44 Ngong Road, Nairobi')
print(f'  james_o {"(new)" if _ else "(updated)"}')

grace_hh, _ = make_user('grace_w', 'HOUSEHOLD', 'Grace', 'Wambui', '254711000003')
setup_household(grace_hh, *offset(0.0050, -0.0180), 'Adams Arcade, Nairobi')
print(f'  grace_w {"(new)" if _ else "(updated)"}')

# ---------------------------------------------------------------------------
# 4. Verified student accounts (rated)
# ---------------------------------------------------------------------------
print('\n── Rated students ──')

alice, _ = make_user('alice_k', 'STUDENT', 'Alice', 'Kamau', '254722000001')
setup_student(alice, *offset(-0.0018, 0.0005), ['Cleaning', 'Cooking'])
give_ratings(alice, [(5,'Superb!'), (5,'Excellent work'), (5,'Very thorough')])

brian, _ = make_user('brian_m', 'STUDENT', 'Brian', 'Mutua', '254722000002')
setup_student(brian, *offset(0.0000, 0.0036), ['Cleaning', 'Laundry'])
give_ratings(brian, [(5,'Very punctual'), (4,'Good job'), (4,'Would hire again')])

carol, _ = make_user('carol_n', 'STUDENT', 'Carol', 'Njeri', '254722000003')
setup_student(carol, *offset(0.0063, 0.0000), ['Childcare', 'Cooking'])
give_ratings(carol, [(4,'Great with kids'), (4,'Reliable')])

david, _ = make_user('david_o', 'STUDENT', 'David', 'Omondi', '254722000004')
setup_student(david, *offset(-0.0090, -0.0045), ['Cleaning', 'Gardening'])
give_ratings(david, [(5,'Perfect'), (4,'Good'), (4,'Recommended')])

eve, _ = make_user('eve_w', 'STUDENT', 'Eve', 'Wanjiku', '254722000005')
setup_student(eve, *offset(0.0135, 0.0045), ['Laundry', 'Errands'])
give_ratings(eve, [(4,'On time'), (4,'Neat work')])

# ---------------------------------------------------------------------------
# 5. New student accounts (0 ratings)
# ---------------------------------------------------------------------------
print('\n── New students (0 ratings) ──')

frank, _ = make_user('frank_k', 'STUDENT', 'Frank', 'Kariuki', '254722000006')
setup_student(frank, *offset(-0.0027, -0.0027), ['Cleaning', 'Errands'])
print(f'  frank_k {"(new)" if _ else "(updated)"}')

grace_s, _ = make_user('grace_s', 'STUDENT', 'Grace', 'Simiyu', '254722000007')
setup_student(grace_s, *offset(0.0045, 0.0045), ['Cleaning', 'Laundry'])
print(f'  grace_s {"(new)" if _ else "(updated)"}')

# Grant location consent for all students
from tasks.geo import LOCATION_CONSENT_VERSION
for st in [alice, brian, carol, david, eve, frank, grace_s]:
    LocationConsent.objects.get_or_create(
        student=st, defaults={'version': LOCATION_CONSENT_VERSION}
    )

# ---------------------------------------------------------------------------
# 6. Admin account
# ---------------------------------------------------------------------------
print('\n── Admin ──')
admin, _ = make_user('admin', 'ADMIN', 'Platform', 'Admin', '254700000001')
admin.is_staff = True
admin.is_superuser = True
admin.save()
print(f'  admin {"(new)" if _ else "(updated)"}')

# ---------------------------------------------------------------------------
# 7. Scenario tasks
# ---------------------------------------------------------------------------
print('\n── Scenario tasks ──')

# ------------------------------------------------------------------
# Scenario A: Assigned task — alice_k has the job, escrow held
#             Start code = 7391 (share with household sarah_m)
# ------------------------------------------------------------------
task_a = Task.objects.filter(
    household_owner=sarah, assigned_student=alice,
    status='Assigned', title__startswith='[DEMO A]'
).first()
if not task_a:
    task_a = Task.objects.create(
        household_owner=sarah,
        assigned_student=alice,
        title='[DEMO A] Living Room Deep Clean',
        description=(
            'Full deep clean of a 2-bedroom apartment: vacuum, mop, '
            'wipe surfaces, clean bathrooms. Supplies provided.'
        ),
        category='Cleaning',
        posted_price=500,
        recommended_price=500,
        location_address='Apt 3B, Madaraka Estate, Nairobi',
        location_lat=offset(-0.0054, 0.0020)[0],
        location_lng=offset(-0.0054, 0.0020)[1],
        geofence_radius_m=150,
        location_pin_confirmed=True,
        status='Assigned',
        scheduled_date=tz.now().date(),
        scheduled_time=(tz.now() + timedelta(minutes=20)).time(),
    )
    Transaction.objects.create(
        task=task_a, amount=500, status='Held',
        mpesa_reference='MP_DEMO_A',
        checkout_request_id='CID_DEMO_A',
        phone_number=sarah.phone_number,
    )
    TaskCompletion.objects.create(task=task_a, start_code='7391')
    TransactionLedger.record(
        task=task_a, transaction_type='HOLD', amount=500,
        actor=sarah, notes='Demo A escrow hold', status='SIMULATED',
    )
    # Broadcast record
    TaskRequest.objects.get_or_create(
        task=task_a, student=alice,
        defaults={'status': 'ACCEPTED', 'broadcast_round': 1,
                  'rank_score': 92.0, 'responded_at': tz.now()},
    )
    AuditLog.log(task_a, sarah, 'transition', 'Matched', 'Assigned',
                 'Demo: payment confirmed, escrow held.')
    Notification.send(alice, 'escrow_deposited',
        'Payment confirmed — task is yours! 🎉',
        f'KES 500 secured for "{task_a.title}". '
        f'Get the 4-digit start code from {sarah.first_name} when you arrive.',
        task_id=task_a.id)
    Notification.send(sarah, 'start_code',
        f'Start code for "{task_a.title}"',
        'Your start code is: 7391  —  share it with Alice when she arrives.',
        task_id=task_a.id)
    print(f'  [A] Assigned   #{task_a.id}  alice_k → sarah_m  (start code 7391)')
else:
    print(f'  [A] Already exists #{task_a.id}')

# ------------------------------------------------------------------
# Scenario B: NoShow task — brian_m was assigned, never checked in
#             Scheduled 35 minutes ago
# ------------------------------------------------------------------
task_b = Task.objects.filter(
    household_owner=james, assigned_student=brian,
    status__in=['Assigned', 'NoShow'], title__startswith='[DEMO B]'
).first()
if not task_b:
    start_time = (tz.now() - timedelta(minutes=35)).time()
    task_b = Task.objects.create(
        household_owner=james,
        assigned_student=brian,
        title='[DEMO B] Kitchen Cleaning',
        description='Deep clean kitchen including oven, fridge and cupboards.',
        category='Cleaning',
        posted_price=500,
        recommended_price=500,
        location_address='44 Ngong Road, Nairobi',
        location_lat=offset(-0.0030, -0.0120)[0],
        location_lng=offset(-0.0030, -0.0120)[1],
        geofence_radius_m=150,
        location_pin_confirmed=True,
        status='NoShow',
        scheduled_date=tz.now().date(),
        scheduled_time=start_time,
    )
    Transaction.objects.create(
        task=task_b, amount=500, status='Held',
        mpesa_reference='MP_DEMO_B',
        checkout_request_id='CID_DEMO_B',
        phone_number=james.phone_number,
    )
    TaskCompletion.objects.create(task=task_b, start_code='4829')
    TaskRequest.objects.get_or_create(
        task=task_b, student=brian,
        defaults={'status': 'ACCEPTED', 'broadcast_round': 1,
                  'rank_score': 88.0, 'responded_at': tz.now() - timedelta(hours=1)},
    )
    AuditLog.log(task_b, None, 'transition', 'Assigned', 'NoShow',
                 'Auto no-show flag: no check-in 30 min after scheduled start.')
    Notification.send(james, 'no_show',
        'Student did not show up ⚠️',
        'Brian did not check in within 30 minutes of the scheduled start. '
        'You can claim a full refund or re-broadcast the task.',
        task_id=task_b.id)
    # Lower brian's reliability
    brian.student_profile.record_cancellation()
    print(f'  [B] NoShow     #{task_b.id}  brian_m → james_o  (missed start)')
else:
    print(f'  [B] Already exists #{task_b.id}')

# ------------------------------------------------------------------
# Scenario C: Broadcasting task — multiple students receive broadcast
#             All 5 rated students + 2 new joiners get a request
# ------------------------------------------------------------------
task_c = Task.objects.filter(
    household_owner=grace_hh,
    status='Broadcasting', title__startswith='[DEMO C]'
).first()
if not task_c:
    task_c = Task.objects.create(
        household_owner=grace_hh,
        title='[DEMO C] Saturday Apartment Clean',
        description=(
            'Full apartment clean: 3 bedrooms, living room, kitchen and '
            'bathrooms. Must bring own cleaning supplies.'
        ),
        category='Cleaning',
        posted_price=600,
        recommended_price=500,
        location_address='Adams Arcade, Langata Road, Nairobi',
        location_lat=offset(0.0050, -0.0180)[0],
        location_lng=offset(0.0050, -0.0180)[1],
        geofence_radius_m=150,
        location_pin_confirmed=True,
        status='Broadcasting',
        broadcast_round=1,
        scheduled_date=(tz.now() + timedelta(days=1)).date(),
        scheduled_time=time(10, 0),
    )
    broadcast_students = [alice, brian, carol, david, eve, frank, grace_s]
    for rank, st in enumerate(broadcast_students):
        avg = Rating.calculate_average(st)
        score = round(50 * (avg / 5) + 30 * (1 - rank * 0.1) + 20 * st.student_profile.reliability_score, 1)
        TaskRequest.objects.get_or_create(
            task=task_c, student=st,
            defaults={'status': 'SENT', 'broadcast_round': 1,
                      'rank_score': max(score, 10)},
        )
        Notification.send(st, 'task_request',
            'New task available for you!',
            f'A "Cleaning" task near Strathmore: "{task_c.title}" for KES 600. '
            'Open the app to accept — first come, first served!',
            task_id=task_c.id)
    AuditLog.log(task_c, None, 'transition', 'Posted', 'Broadcasting',
                 f'Round 1 broadcast sent to {len(broadcast_students)} students.')
    print(f'  [C] Broadcasting #{task_c.id}  grace_w → 7 students  (round 1)')
else:
    print(f'  [C] Already exists #{task_c.id}')

# ------------------------------------------------------------------
# Scenario D: Completed task with mutual ratings
# ------------------------------------------------------------------
task_d = Task.objects.filter(
    household_owner=sarah, assigned_student=carol,
    status='Completed', title__startswith='[DEMO D]'
).first()
if not task_d:
    task_d = Task.objects.create(
        household_owner=sarah,
        assigned_student=carol,
        title='[DEMO D] Baby-Sitting Saturday',
        description='Looking after 2 children (3 and 6 years old), 4 hours.',
        category='Childcare',
        posted_price=800,
        recommended_price=800,
        location_address='Madaraka Estate, Nairobi',
        location_lat=offset(-0.0054, 0.0020)[0],
        location_lng=offset(-0.0054, 0.0020)[1],
        location_pin_confirmed=True,
        status='Completed',
        scheduled_date=(tz.now() - timedelta(days=3)).date(),
    )
    escrow_d = Transaction.objects.create(
        task=task_d, amount=800, status='Released',
        mpesa_reference='MP_DEMO_D', checkout_request_id='CID_DEMO_D',
        phone_number=sarah.phone_number,
    )
    TransactionLedger.record(task=task_d, transaction_type='HOLD', amount=800, actor=sarah, status='SIMULATED')
    TransactionLedger.record(task=task_d, transaction_type='RELEASE', amount=800, actor=sarah, status='SIMULATED')
    add_rating(task_d, sarah, carol, 5, 'Carol is amazing with kids — punctual and caring!')
    add_rating(task_d, carol, sarah, 5, 'Very organised household, lovely family.')
    print(f'  [D] Completed  #{task_d.id}  carol_n → sarah_m  (5★ both ways)')
else:
    print(f'  [D] Already exists #{task_d.id}')

# ------------------------------------------------------------------
# Scenario E: Disputed task
# ------------------------------------------------------------------
task_e = Task.objects.filter(
    household_owner=james, assigned_student=david,
    status='Disputed', title__startswith='[DEMO E]'
).first()
if not task_e:
    task_e = Task.objects.create(
        household_owner=james,
        assigned_student=david,
        title='[DEMO E] Garden Trimming',
        description='Trim hedges, mow lawn and remove weeds from front garden.',
        category='Gardening',
        posted_price=500,
        recommended_price=500,
        location_address='44 Ngong Road, Nairobi',
        location_lat=offset(-0.0030, -0.0120)[0],
        location_lng=offset(-0.0030, -0.0120)[1],
        location_pin_confirmed=True,
        status='Disputed',
        scheduled_date=(tz.now() - timedelta(days=1)).date(),
    )
    Transaction.objects.create(
        task=task_e, amount=500, status='Held',
        mpesa_reference='MP_DEMO_E', checkout_request_id='CID_DEMO_E',
        phone_number=james.phone_number,
    )
    comp_e = TaskCompletion.objects.create(
        task=task_e, start_code='3317',
        start_code_verified=True,
        arrived_at=tz.now() - timedelta(hours=5),
        started_at=tz.now() - timedelta(hours=5),
        finished_at=tz.now() - timedelta(hours=2),
    )
    CheckIn.objects.create(
        task=task_e, student=david, type='START',
        lat=offset(-0.0030, -0.0120)[0],
        lng=offset(-0.0030, -0.0120)[1],
        accuracy_m=12.0,
        distance_m=18.0,
        result='VERIFIED',
    )
    CheckIn.objects.create(
        task=task_e, student=david, type='FINISH',
        lat=offset(-0.0030, -0.0120)[0],
        lng=offset(-0.0030, -0.0120)[1],
        accuracy_m=10.0,
        distance_m=5.0,
        result='VERIFIED',
    )
    Dispute.objects.create(
        task=task_e,
        raised_by=james,
        reason='poor_quality',
        description=(
            'The hedges were unevenly trimmed and the back garden was '
            'completely missed. Work is only half done.'
        ),
        student_response=(
            'I completed all the work described. The back area was out of '
            'scope — it was not mentioned in the task description.'
        ),
        student_responded_at=tz.now() - timedelta(hours=1),
    )
    AuditLog.log(task_e, james, 'dispute_event', '', '',
                 'Dispute raised: poor_quality. Awaiting admin resolution.')
    for adm in CustomUser.objects.filter(role='ADMIN', is_active=True):
        Notification.send(adm, 'dispute_raised',
            f'New dispute on task #{task_e.id}',
            f'Task "{task_e.title}": poor_quality — both sides have submitted statements.',
            task_id=task_e.id)
    print(f'  [E] Disputed   #{task_e.id}  david_o → james_o  (both sides responded)')
else:
    print(f'  [E] Already exists #{task_e.id}')

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
print("""
╔══════════════════════════════════════════════════════════════════╗
║               DEMO SETUP COMPLETE — password: demo1234          ║
╠══════════════════════════════════════════════════════════════════╣
║  HOUSEHOLDS                                                      ║
║    sarah_m   Madaraka Estate  (600 m from Strathmore)           ║
║    james_o   Ngong Road       (1.2 km)                          ║
║    grace_w   Adams Arcade     (1.8 km)                          ║
╠══════════════════════════════════════════════════════════════════╣
║  STUDENTS (Verified, 4–5 ★)                                     ║
║    alice_k   5.0★  200 m south    Cleaning, Cooking             ║
║    brian_m   4.3★  400 m east     Cleaning, Laundry             ║
║    carol_n   4.0★  700 m north    Childcare, Cooking            ║
║    david_o   4.3★  1.0 km SW      Cleaning, Gardening           ║
║    eve_w     4.0★  1.5 km SE      Laundry, Errands              ║
║                                                                  ║
║  STUDENTS (Verified, new joiners)                               ║
║    frank_k   0★   300 m NW        Cleaning, Errands             ║
║    grace_s   0★   500 m NE        Cleaning, Laundry             ║
╠══════════════════════════════════════════════════════════════════╣
║  ADMIN: admin                                                    ║
╠══════════════════════════════════════════════════════════════════╣
║  DEMO SCENARIOS                                                  ║
║  [A] Assigned   sarah_m → alice_k  start code: 7391            ║
║      → Check in as alice_k to start the task                   ║
║  [B] NoShow     james_o → brian_m  scheduled 35 min ago        ║
║      → Brian never arrived, penalty applied                     ║
║  [C] Broadcasting  grace_w → 7 students in inbox               ║
║      → Race to accept: login as any student                     ║
║  [D] Completed  sarah_m → carol_n  mutual 5★ ratings           ║
║  [E] Disputed   james_o → david_o  both sides responded        ║
║      → Login as admin to resolve                                ║
╠══════════════════════════════════════════════════════════════════╣
║  URLs                                                            ║
║    App:          http://localhost:8082                           ║
║    Django Admin: http://localhost:8000/admin                     ║
╚══════════════════════════════════════════════════════════════════╝
""")
