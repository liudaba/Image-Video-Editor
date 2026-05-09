import requests
try:
    r = requests.post('http://127.0.0.1:8000/api/auth/register',
        json={'username':'testuser99','email':'test99@test.com','password':'Test1234'},
        timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Body: {r.text}')
except Exception as e:
    print(f'Error: {e}')

try:
    r2 = requests.get('http://127.0.0.1:8000/api/auth/profile', timeout=5)
    print(f'Profile Status: {r2.status_code}')
except Exception as e:
    print(f'Profile Error: {e}')
