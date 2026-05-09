import requests
try:
    r = requests.post('http://127.0.0.1:8000/api/auth/register', json={'username':'testuser99','email':'test99@test.com','password':'Test1234'}, timeout=5)
    with open('test_result.txt', 'w') as f:
        f.write('Status: ' + str(r.status_code) + '\n')
        f.write('Body: ' + r.text + '\n')
except Exception as e:
    with open('test_result.txt', 'w') as f:
        f.write('Error: ' + str(type(e).__name__) + ': ' + str(e) + '\n')
