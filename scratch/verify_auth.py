import requests, json, sys, time
BASE = 'http://127.0.0.1:8000'
# Register a student
reg_data = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123",
    "first_name": "Test",
    "last_name": "User",
    "phone_number": "123456",
    "university_id": "U123",
    "university_name": "Test University"
}
r = requests.post(f'{BASE}/api/auth/register/student/', json=reg_data)
print('Register status', r.status_code, r.text)
if r.status_code != 201:
    sys.exit(1)
# Login
login_data = {"email": "test@example.com", "password": "password123"}
r = requests.post(f'{BASE}/api/auth/login/', json=login_data)
print('Login status', r.status_code, r.text)
if r.status_code != 200:
    sys.exit(1)
resp = r.json()
next_url = resp.get('next')
print('Next URL:', next_url)
# Access home page with session (cookie) using same session
s = requests.Session()
# Set auth token cookie as if server set it (token auth may not set cookie, but we'll use token header)
token = resp.get('token')
headers = {'Authorization': f'Token {token}'}
# Get home page (HTML) - may need to use session with auth cookie, but we use token header
home = s.get(f'{BASE}{next_url}', headers=headers)
print('Home status', home.status_code)
print('Home content snippet:', home.text[:200])
