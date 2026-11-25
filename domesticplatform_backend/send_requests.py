import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from tasks.models import Task, TaskRequest
from users.models import CustomUser
from users.notifications import Notification

task = Task.objects.get(id=43)

# Send to all verified students who haven't received it yet
students = CustomUser.objects.filter(
    role='STUDENT',
    student_profile__verification_status='Verified',
    is_active=True,
)

for student in students:
    obj, created = TaskRequest.objects.get_or_create(
        task=task, student=student,
        defaults={'status': 'SENT', 'broadcast_round': 1, 'rank_score': 80.0}
    )
    if created:
        Notification.send(
            student, 'task_request',
            'New task available!',
            'A new task has been posted. Open Available Tasks to accept.',
            task_id=task.id,
        )
        print(f'  Sent to {student.username}')
    else:
        print(f'  {student.username} already has [{obj.status}]')
