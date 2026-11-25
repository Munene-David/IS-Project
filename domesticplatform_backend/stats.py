import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from tasks.models import Task, TaskRequest, CheckIn
from users.models import CustomUser
from payments.models import Rating, Transaction, TransactionLedger

print('=== SYSTEM STATISTICS ===')
total = CustomUser.objects.count()
hh = CustomUser.objects.filter(role='HOUSEHOLD').count()
st = CustomUser.objects.filter(role='STUDENT').count()
ad = CustomUser.objects.filter(role='ADMIN').count()
print(f'Total users: {total}  (Households: {hh}, Students: {st}, Admins: {ad})')

tasks = Task.objects.filter(is_deleted=False).exclude(title__startswith='_')
print(f'Total tasks: {tasks.count()}')
for s in ['Posted','Broadcasting','Matched','Assigned','InProgress','AwaitingConfirmation','Completed','Cancelled','Disputed','NoShow']:
    c = tasks.filter(status=s).count()
    if c: print(f'  {s}: {c}')

reqs = TaskRequest.objects.exclude(task__title__startswith='_').count()
print(f'Task requests sent: {reqs}')
checkins = CheckIn.objects.count()
print(f'Check-in records: {checkins}')
ratings = Rating.objects.exclude(task__title__startswith='_').count()
print(f'Ratings: {ratings}')
txns = Transaction.objects.count()
ledger = TransactionLedger.objects.count()
print(f'Escrow transactions: {txns}  |  Ledger entries: {ledger}')
