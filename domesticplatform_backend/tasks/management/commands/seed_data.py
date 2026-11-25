from django.core.management.base import BaseCommand
from tasks.models import PriceGuide
from users.models import CustomUser, StudentProfile, HouseholdProfile


class Command(BaseCommand):
    help = 'Seeds initial Price Guide categories and test accounts'

    def handle(self, *args, **options):
        # 1. Seed Price Guide
        categories = [
            {'category': 'Cleaning', 'min_price': 300, 'max_price': 800, 'recommended_price': 500, 'description': 'House, room, and compound cleaning'},
            {'category': 'Laundry', 'min_price': 200, 'max_price': 600, 'recommended_price': 350, 'description': 'Washing, ironing, and folding clothes'},
            {'category': 'Childcare', 'min_price': 500, 'max_price': 1500, 'recommended_price': 800, 'description': 'Babysitting and daytime childcare'},
            {'category': 'Gardening', 'min_price': 400, 'max_price': 1000, 'recommended_price': 600, 'description': 'Lawn mowing, weeding, compound maintenance'},
            {'category': 'Cooking', 'min_price': 400, 'max_price': 1200, 'recommended_price': 700, 'description': 'Meal preparation and kitchen assistance'},
        ]

        for cat in categories:
            guide, created = PriceGuide.objects.update_or_create(
                category=cat['category'],
                defaults=cat
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} price guide: {guide.category}")

        # 2. Seed Test Users
        # Admin
        admin, _ = CustomUser.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@platform.ac.ke',
                'role': 'ADMIN',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin.set_password('Admin1234!')
        admin.save()

        # Household Owner
        sarah, created = CustomUser.objects.get_or_create(
            username='sarah_m',
            defaults={
                'email': 'sarah@gmail.com',
                'first_name': 'Sarah',
                'last_name': 'Mwangi',
                'role': 'HOUSEHOLD',
                'phone_number': '254712345678',
            }
        )
        if created:
            sarah.set_password('Sarah1234!')
            sarah.save()
            profile = sarah.household_profile
            profile.address = 'Kilimani, Nairobi'
            profile.location_lat = -1.2921
            profile.location_lng = 36.7856
            profile.verification_status = 'Verified'
            profile.save()

        # Student User
        jane, created = CustomUser.objects.get_or_create(
            username='jane_w',
            defaults={
                'email': 'jane.w@uon.ac.ke',
                'first_name': 'Jane',
                'last_name': 'Wanjiru',
                'role': 'STUDENT',
                'phone_number': '254798765432',
            }
        )
        if created:
            jane.set_password('Jane1234!')
            jane.save()
            profile = jane.student_profile
            profile.university_id = 'UON/CS/2023/042'
            profile.university_name = 'University of Nairobi'
            profile.verification_status = 'Verified'
            profile.categories_offered = ['Cleaning', 'Cooking', 'Laundry']
            profile.location_lat = -1.2921
            profile.location_lng = 36.7856
            profile.save()

        # Additional students for broadcast demo
        extra_students = [
            {
                'username': 'brian_k',
                'email': 'brian.k@uon.ac.ke',
                'first_name': 'Brian',
                'last_name': 'Kiptoo',
                'phone_number': '254720111222',
                'university_id': 'UON/IT/2022/015',
                'university_name': 'University of Nairobi',
                'categories': ['Cleaning', 'Gardening'],
                'lat': -1.2950,
                'lng': 36.7800,
            },
            {
                'username': 'mary_n',
                'email': 'mary.n@ku.ac.ke',
                'first_name': 'Mary',
                'last_name': 'Njeri',
                'phone_number': '254721333444',
                'university_id': 'KU/ENG/2023/078',
                'university_name': 'Kenyatta University',
                'categories': ['Cleaning', 'Childcare'],
                'lat': -1.2900,
                'lng': 36.7900,
            },
        ]

        for sd in extra_students:
            student, created = CustomUser.objects.get_or_create(
                username=sd['username'],
                defaults={
                    'email': sd['email'],
                    'first_name': sd['first_name'],
                    'last_name': sd['last_name'],
                    'role': 'STUDENT',
                    'phone_number': sd['phone_number'],
                }
            )
            if created:
                student.set_password('Student1234!')
                student.save()
                profile = student.student_profile
                profile.university_id = sd['university_id']
                profile.university_name = sd['university_name']
                profile.verification_status = 'Verified'
                profile.categories_offered = sd['categories']
                profile.location_lat = sd['lat']
                profile.location_lng = sd['lng']
                profile.save()

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))
