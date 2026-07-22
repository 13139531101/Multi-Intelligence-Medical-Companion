import httpx
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
# Try v2 upload exactly as frontend HealthUploader does
with open(r'I:\A2A\3\A2AServer\scripts\check_api_routes.py','rb') as f:
    r = httpx.post('http://localhost:13002/v2/upload/file',
                   data={'user_id': 'user_4e3ef0b3f49d8d4433e0b4420a3bae2a', 'domain': 'pha', 'purpose': 'health_record', 'limit': 10},
                   files={'file': ('test.txt', f, 'text/plain')},
                   headers={'Authorization': 'Bearer '+tok},
                   timeout=20)
print(f'/v2/upload/file  status={r.status_code}')
print(f'body: {r.text[:300]}')
