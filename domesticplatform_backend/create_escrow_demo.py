"""Creates a Matched task so the household can demo the escrow payment flow."""
import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from django.utils import timezone as tz
from datetime import timedelta
from users.models import CustomUser
from tasks.models import Task, TaskRequest
from users.notifications import Notification

sarah = CustomUser.objects.get(username='sarah_m')
alice = CustomUser.objects.get(username='alice_k')

task = Task.objects.create(
    household_owner=sarah,
    assigned_student=alice,
    title='Laundry & Ironing',
    description='Wash, dry and iron clothes for a family of 4. Three loads estimated.',
    category='Laundry',
    posted_price=400,
    recommended_price=400,
    location_address='Madaraka Estate, Nairobi',
    location_lat=-1.3154,
    location_lng=36.8146,
    geofence_radius_m=150,
    location_pin_confirmed=True,
    status='Matched',
    scheduled_date=(tz.now() + timedelta(hours=2)).date(),
    scheduled_time=(tz.now() + timedelta(hours=2)).time(),
    grace_window_deadline=tz.now() + timedelta(minutes=9),
)

TaskRequest.objects.create(
    task=task, student=alice,
    status='ACCEPTED', broadcast_round=1,
    rank_score=95.0, responded_at=tz.now(),
)

Notification.send(
    sarah, 'task_matched',
    'Match found — action required',
    'Alice accepted your task. You have 10 minutes to confirm and pay via M-Pesa.',
    task_id=task.id,
)
Notification.send(
    alice, 'task_matched',
    'You got the job!',
    'The household will confirm payment shortly.',
    task_id=task.id,
)

print(f'Task #{task.id}  status=Matched')
print(f'Grace window closes: {task.grace_window_deadline.strftime("%H:%M:%S")} UTC')
print('')
print('=== HOW TO DEMO ESCROW ===')
print('1. Login as sarah_m / demo1234')
print('2. Open task "Laundry & Ironing"')
print('3. Tap "Confirm & Pay (M-Pesa)"')
print('4. Enter phone: 254711000001')
print('5. Watch status change: Matched -> PaymentPending -> Assigned')
print('6. Escrow status shows: Held (funds locked)')
print('7. Login as alice_k to see the start code and full address revealed')
