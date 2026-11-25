from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from users.models import CustomUser
from tasks.models import PriceGuide, Task, Bid
from payments.models import Transaction, Rating


class MarketplaceEndToEndTests(APITestCase):
    def setUp(self):
        # 1. Setup Price Guide
        self.price_guide = PriceGuide.objects.create(
            category='Cleaning',
            min_price=300,
            max_price=800,
            recommended_price=500
        )

        # 2. Setup Household Owner
        self.household_user = CustomUser.objects.create_user(
            username='sarah_m',
            email='sarah@example.com',
            password='Password123!',
            role='HOUSEHOLD',
            phone_number='254711000111'
        )
        self.household_token = Token.objects.create(user=self.household_user).key

        # 3. Setup Student
        self.student_user = CustomUser.objects.create_user(
            username='jane_w',
            email='jane@uon.ac.ke',
            password='Password123!',
            role='STUDENT',
            phone_number='254722000222'
        )
        self.student_token = Token.objects.create(user=self.student_user).key

    def test_full_marketplace_workflow(self):
        # Step 1: Check Price Guide
        response = self.client.get('/api/price-guide/Cleaning/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['recommended_price']), 500.0)

        # Step 2: Household posts a task
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        task_data = {
            'title': 'Living Room Cleaning',
            'description': 'Deep clean living room and sofa',
            'category': 'Cleaning',
            'posted_price': '500.00',
            'location_address': 'Kilimani, Nairobi',
            'location_lat': '-1.292100',
            'location_lng': '36.785600',
        }
        create_task_res = self.client.post('/api/tasks/', task_data, format='json')
        self.assertEqual(create_task_res.status_code, status.HTTP_201_CREATED)
        task_id = create_task_res.data['id']

        # Step 3: Student browses tasks
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.student_token}')
        browse_res = self.client.get('/api/tasks/?category=Cleaning')
        self.assertEqual(browse_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(browse_res.data), 1)

        # Step 4: Student submits a bid
        bid_data = {
            'amount': '450.00',
            'message': 'Available this pm and experienced!'
        }
        bid_res = self.client.post(f'/api/tasks/{task_id}/bids/', bid_data, format='json')
        self.assertEqual(bid_res.status_code, status.HTTP_201_CREATED)
        bid_id = bid_res.data['id']

        # Step 5: Household accepts the bid
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.household_token}')
        accept_res = self.client.post(f'/api/tasks/{task_id}/accept-bid/', {'bid_id': bid_id}, format='json')
        self.assertEqual(accept_res.status_code, status.HTTP_200_OK)
        self.assertEqual(accept_res.data['task']['status'], 'Assigned')

        # Step 6: Household deposits funds into Escrow via M-Pesa
        deposit_data = {
            'task_id': task_id,
            'phone_number': '254711000111'
        }
        deposit_res = self.client.post('/api/payments/initiate-escrow/', deposit_data, format='json')
        self.assertEqual(deposit_res.status_code, status.HTTP_200_OK)
        self.assertEqual(deposit_res.data['transaction']['status'], 'Held')
        self.assertEqual(deposit_res.data['task_status'], 'InProgress')

        # Step 7: Send a chat message
        msg_data = {'content': 'Hi Jane, I have funded the escrow. See you at 3pm!'}
        msg_res = self.client.post(f'/api/tasks/{task_id}/messages/', msg_data, format='json')
        self.assertEqual(msg_res.status_code, status.HTTP_201_CREATED)

        # Step 8: Release Escrow upon completion
        release_res = self.client.post('/api/payments/release-escrow/', {'task_id': task_id}, format='json')
        self.assertEqual(release_res.status_code, status.HTTP_200_OK)
        self.assertEqual(release_res.data['transaction']['status'], 'Released')
        self.assertEqual(release_res.data['task_status'], 'Completed')

        # Step 9: Rate the student
        rate_data = {
            'task': task_id,
            'rated_user': self.student_user.id,
            'score': 5,
            'comment': 'Fantastic job, very punctual and thorough!'
        }
        rate_res = self.client.post('/api/ratings/', rate_data, format='json')
        self.assertEqual(rate_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Rating.calculate_average(self.student_user), 5.0)
