import httpx, sys
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']

# Try various paths
paths = ['/api/health-records/upload', '/api/health-records/upload/multiple', '/v2/files/upload']
for p in paths:
    with open(r'I:\A2A\3\A2AServer\scripts\check_api_routes.py', 'rb') as f:
        r = httpx.post('http://localhost:13002'+p, headers={'Authorization': 'Bearer '+tok}, files={'file': ('test.txt', f, 'text/plain')}, timeout=15)
    print(f'{p:50s} {r.status_code}  {r.text[:200]!r}')
