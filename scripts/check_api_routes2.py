import httpx
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']
r = httpx.get('http://localhost:13002/api/health-records', headers={'Authorization': 'Bearer '+tok}, timeout=10)
print('status:', r.status_code)
print('body:', r.text[:1500])
