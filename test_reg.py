import requests
import sys
try:
    r = requests.post('http://127.0.0.1:8000/api/auth/register', json={'username':'testuser99','email':'test99@test.com','password':'Test1234'}, timeout=5)
    sys.stdout.write('Status: ' + str(r.status_code) + '\n')
    sys.stdout.write('Body: ' + r.text + '\n')
except Exception as e:
    sys.stdout.write('Error: ' + str(e) + '\n')
sys.stdout.flush()
