"""Give every student who has no rating a 5.0 starting rating."""
import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from users.models import CustomUser
from payments.models import Rating
from tasks.models import Task

system_hh, _ = CustomUser.objects.get_or_create(
    username='_system',
    defaults={
        'email': '_system@platform.local',
        'role': 'HOUSEHOLD',
        'first_name': 'Platform',
        'last_name': 'System',
        'is_active': False,
    }
)

students = CustomUser.objects.filter(role='STUDENT', is_active=True)
seeded = 0
for u in students:
    avg = Rating.calculate_average(u)
    if avg > 0:
        print(f'  SKIP  {u.username:16} already has {avg:.1f}★')
        continue
    # Check no seed task already exists
    if Task.objects.filter(title=f'_seed_{u.username}').exists():
        print(f'  SKIP  {u.username:16} seed task exists but no rating?')
        continue
    seed_task = Task.objects.create(
        household_owner=system_hh,
        assigned_student=u,
        title=f'_seed_{u.username}',
        description='Seed rating task',
        category='Cleaning',
        posted_price=0,
        location_pin_confirmed=False,
        status='Completed',
    )
    Rating.objects.create(
        task=seed_task,
        rater=system_hh,
        rated_user=u,
        score=5,
        comment='Starting rating — platform verified new member.',
    )
    seeded += 1
    print(f'  OK    {u.username:16} → 5.0★')

print(f'\nDone — seeded {seeded} student(s) with 5.0★ starting rating.')
