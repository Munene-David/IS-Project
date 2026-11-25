import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from users.models import CustomUser

DEMO_ACCOUNTS = [
    ('sarah_m',  'demo1234'),  # Household
    ('jane_w',   'demo1234'),  # Student
    ('brian_k',  'demo1234'),  # Student
    ('admin',    'demo1234'),  # Admin
]

for username, pw in DEMO_ACCOUNTS:
    try:
        u = CustomUser.objects.get(username=username)
        u.set_password(pw)
        u.save()
        print(f'  OK  {username} ({u.role})')
    except CustomUser.DoesNotExist:
        print(f'  --  {username} not found')
