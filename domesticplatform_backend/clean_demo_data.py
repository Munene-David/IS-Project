"""
Removes all synthetic/demo data and leaves only genuine user-created content.
Run once: python clean_demo_data.py
"""
import os, sys, re, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from tasks.models import Task
from payments.models import Rating
from users.models import CustomUser

# ── 1. Delete all synthetic tasks (id >= 20) ──────────────────────────────
synthetic = Task.objects.filter(id__gte=20)
n = synthetic.count()
synthetic.delete()
print(f'Deleted {n} synthetic tasks (cascades all checkins, escrow, ledger, disputes)')

# ── 2. Demo named accounts from setup_demo.py ─────────────────────────────
demo_names = [
    'alice_k', 'brian_m', 'carol_n', 'david_o', 'eve_w',
    'frank_k', 'grace_s', 'james_o', 'grace_w',
]
# Also e2e-generated accounts: grace_XXXXXX / tom_XXXXXX
pattern = re.compile(r'^(grace_|tom_)[0-9a-f]{5,8}$')
for u in CustomUser.objects.all():
    if pattern.match(u.username):
        demo_names.append(u.username)

removed = 0
for name in set(demo_names):
    deleted, _ = CustomUser.objects.filter(username=name).delete()
    if deleted:
        print(f'  Deleted user: {name}')
        removed += 1
print(f'Removed {removed} demo user accounts')

# ── 3. rater_ scaffold accounts ───────────────────────────────────────────
raters = CustomUser.objects.filter(username__startswith='rater_')
n = raters.count()
raters.delete()
print(f'Removed {n} rater_ scaffold accounts')

# ── 4. Orphaned ratings ───────────────────────────────────────────────────
orphans = Rating.objects.filter(task__isnull=True)
n = orphans.count()
orphans.delete()
print(f'Removed {n} orphaned ratings')

# ── 5. Summary ────────────────────────────────────────────────────────────
print()
print('=== REMAINING USERS ===')
for role in ['HOUSEHOLD', 'STUDENT', 'ADMIN']:
    qs = CustomUser.objects.filter(role=role)
    print(f'  {role} ({qs.count()}): ' + ', '.join(u.username for u in qs))

print()
print('=== REMAINING TASKS ===')
for t in Task.objects.order_by('id'):
    print(f'  [{t.id}] {t.status:20} | {t.title}')

print('\nDone — database contains only live user data.')
