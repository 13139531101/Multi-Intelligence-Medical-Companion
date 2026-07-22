import httpx
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']
for ep in ['/api/health-records', '/api/health-records/statistics', '/v2/health-records', '/health/records', '/health_records']:
    r = httpx.get('http://localhost:13002'+ep, headers={'Authorization': 'Bearer '+tok}, timeout=5)
    body = (r.text or "")[:80]
    print(f'{ep:35s} status={r.status_code}  body={body!r}')
