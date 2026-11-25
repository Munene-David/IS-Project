import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from users.models import CustomUser
from tasks.models import Task, TaskRequest
from payments.models import Rating
from users.notifications import Notification

# ── 1. Find Nesh ──────────────────────────────────────────────────
nesh = None
for u in CustomUser.objects.filter(role='STUDENT').order_by('-id'):
    if 'nesh' in u.username.lower() or 'nesh' in (u.first_name or '').lower():
        nesh = u
        break

if not nesh:
    print('Nesh not found by name — recent students:')
    for u in CustomUser.objects.filter(role='STUDENT').order_by('-id')[:10]:
        try:
            sp = u.student_profile
            avg = Rating.calculate_average(u)
            print(f'  {u.id:4} | {u.username:18} | {u.first_name:12} | {sp.verification_status:10} | {avg:.1f}*')
        except Exception:
            print(f'  {u.id:4} | {u.username:18} | no profile')
else:
    sp = nesh.student_profile
    avg = Rating.calculate_average(nesh)
    print(f'Found Nesh: {nesh.username} | {nesh.first_name} {nesh.last_name}')
    print(f'  verified={sp.verification_status} | rating={avg} | cats={sp.categories_offered}')

    # ── 2. Fix: verify, give categories, seed rating if needed ───
    sp.verification_status = 'Verified'
    sp.availability_status = True
    if not sp.categories_offered:
        sp.categories_offered = ['Cleaning', 'Cooking', 'Laundry', 'Errands']
    sp.save()
    print(f'  Profile fixed: Verified, cats={sp.categories_offered}')

    if avg == 0:
        # Seed 5-star rating
        system_hh, _ = CustomUser.objects.get_or_create(
            username='_system',
            defaults={'email': '_system@platform.local', 'role': 'HOUSEHOLD',
                      'first_name': 'Platform', 'last_name': 'System', 'is_active': False}
        )
        from tasks.models import Task
        seed = Task.objects.create(
            household_owner=system_hh, assigned_student=nesh,
            title=f'_seed_{nesh.username}', description='Seed rating',
            category='Cleaning', posted_price=0,
            location_pin_confirmed=False, status='Completed',
        )
        Rating.objects.create(task=seed, rater=system_hh, rated_user=nesh,
                               score=5, comment='Starting rating — new member.')
        print(f'  Seeded 5.0 rating')

    # ── 3. Send Nesh requests for all active Broadcasting tasks ──
    active_tasks = Task.objects.filter(
        status='Broadcasting', is_deleted=False
    ).exclude(title__startswith='_')

    sent = 0
    for task in active_tasks:
        req, created = TaskRequest.objects.get_or_create(
            task=task, student=nesh,
            defaults={'status': 'SENT', 'broadcast_round': 1, 'rank_score': 95.0}
        )
        if created:
            Notification.send(
                nesh, 'task_request',
                'New task available for you!',
                f'A "{task.category}" task is available: "{task.title}" for KES {task.posted_price}. Open Available Tasks to accept.',
                task_id=task.id,
                request_id=req.id,
            )
            print(f'  Sent request for task #{task.id}: {task.title}')
            sent += 1
        elif req.status in ('EXPIRED', 'SENT', 'VIEWED'):
            req.status = 'SENT'
            req.save(update_fields=['status'])
            print(f'  Re-opened request for task #{task.id}: {task.title}')
            sent += 1
        else:
            print(f'  Task #{task.id} already has [{req.status}]')

    print(f'\nDone — {sent} task(s) sent to {nesh.username}. Tell Nesh to refresh Available Tasks.')
