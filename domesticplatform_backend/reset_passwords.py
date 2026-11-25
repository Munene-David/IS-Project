import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from users.models import CustomUser

PASSWORD = 'demo1234'

# Key demo accounts only
ACCOUNTS = [
    'sarah_m', 'BillWest', 'MuneneM', 'MuthiiDavid', 'test_household',
    'jane_w', 'brian_k', 'mary_n', 'Muthii', 'MuneneP', 'MuthiiQ',
    'David.Muthii', 'Dmunene', 'jp', 'Munene',
    'admin',
]

for name in ACCOUNTS:
    try:
        u = CustomUser.objects.get(username=name)
        u.set_password(PASSWORD)
        u.save()
        print(f'  OK  {name:20} ({u.role})')
    except CustomUser.DoesNotExist:
        print(f'  --  {name} not found')

print(f'\nAll set — password: {PASSWORD}')
