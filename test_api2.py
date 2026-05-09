import requests
import sys

try:
    r = requests.post('http://127.0.0.1:8000/api/auth/register',
        json={'username':'testuser99','email':'test99@test.com','password':'Test1234'},
        timeout=5)
    sys.stdout.write(f'Status: {r.status_code}\n')
    sys.stdout.write(f'Body: {r.text}\n')
    sys.stdout.flush()
except Exception as e:
    sys.stdout.write(f'Error: {type(e).__name__}: {e}\n')
    sys.stdout.flush()
