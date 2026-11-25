"""
Sets up real student accounts properly:
  - Verifies them
  - Assigns realistic categories
  - Adds ratings so the broadcast ranking works (higher rated = gets task first)
  - Sets locations near Nairobi CBD

Run: python setup_students.py
"""
import os, sys, django
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'domesticplatform_backend.settings'
django.setup()

from users.models import CustomUser, StudentProfile
from payments.models import Rating
from tasks.models import Task, PriceGuide

# ---------------------------------------------------------------------------
# Student config: username -> (categories, rating_scores, lat, lng)
# ---------------------------------------------------------------------------
STUDENT_CONFIG = {
    'jane_w':     (['Cleaning', 'Cooking', 'Laundry'],      [5, 5, 5],      -1.2921, 36.7856),
    'brian_k':    (['Cleaning', 'Gardening', 'Errands'],    [4, 5, 4],      -1.2950, 36.7800),
    'mary_n':     (['Cleaning', 'Childcare', 'Cooking'],    [4, 4, 5],      -1.2900, 36.7900),
    'MuneneP':    (['Cleaning', 'Laundry', 'Errands'],      [3, 4],         -1.2960, 36.8100),
    'MuthiiQ':    (['Cooking', 'Cleaning'],                 [4, 3],         -1.3000, 36.8200),
    'David.Muthii':(['Cleaning', 'Gardening'],              [3, 3],         -1.2880, 36.8000),
    'Muthii':     (['Cleaning', 'Errands'],                 [2, 3],         -1.3100, 36.8300),
    'Dmunene':    (['Cleaning', 'Laundry'],                 [2, 2],         -1.3050, 36.8150),
}

# Make sure price guides exist for all categories
CATEGORIES = ['Cleaning', 'Cooking', 'Laundry', 'Childcare', 'Gardening', 'Errands', 'Other']
for cat in CATEGORIES:
    PriceGuide.objects.get_or_create(
        category=cat,
        defaults={'min_price': 200, 'max_price': 1000, 'recommended_price': 500}
    )

# Get or create a dummy household for giving historical ratings
rater_hh, _ = CustomUser.objects.get_or_create(
    username='_rating_hh',
    defaults={
        'email': '_ratinghh@system.local',
        'role': 'HOUSEHOLD',
        'first_name': 'Rating',
        'last_name': 'System',
    }
)
rater_hh.set_password('x')
rater_hh.save()

print('Setting up students...\n')

for username, (categories, scores, lat, lng) in STUDENT_CONFIG.items():
    try:
        u = CustomUser.objects.get(username=username)
    except CustomUser.DoesNotExist:
        print(f'  SKIP  {username} — not found')
        continue

    # Ensure profile exists
    sp, _ = StudentProfile.objects.get_or_create(user=u)
    sp.verification_status = 'Verified'
    sp.availability_status = True
    sp.categories_offered = categories
    sp.location_lat = lat
    sp.location_lng = lng
    sp.save()

    # Add historical ratings (create throwaway completed tasks)
    added = 0
    for i, score in enumerate(scores):
        # Create a unique completed task for each rating
        task_key = f'_hist_{username}_{i}'
        hist_task = Task.objects.filter(title=task_key).first()
        if not hist_task:
            hist_task = Task.objects.create(
                household_owner=rater_hh,
                assigned_student=u,
                title=task_key,
                description='Historical rating task',
                category=categories[0],
                posted_price=500,
                location_pin_confirmed=False,
                status='Completed',
            )
        _, created = Rating.objects.get_or_create(
            task=hist_task, rater=rater_hh, rated_user=u,
            defaults={'score': score, 'comment': 'Historical rating'}
        )
        if created:
            added += 1

    avg = Rating.calculate_average(u)
    print(f'  OK  {username:16} | Verified | {avg:.1f}★ | {categories}')

print()
print('Rating-based broadcast priority (highest first):')
print('-' * 50)
from payments.models import Rating as R
all_students = []
for username in STUDENT_CONFIG:
    try:
        u = CustomUser.objects.get(username=username)
        avg = R.calculate_average(u)
        all_students.append((avg, username))
    except Exception:
        pass

for avg, name in sorted(all_students, reverse=True):
    bar = '★' * int(round(avg))
    print(f'  {avg:.1f} {bar:5}  {name}')

print()
print('Done. Higher-rated students will now receive broadcasts first.')
print('All students can still accept — lower-rated ones just get round-2.')
