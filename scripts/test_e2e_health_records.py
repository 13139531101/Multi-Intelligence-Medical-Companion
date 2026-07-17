"""e2e 测试"""
import httpx
r = httpx.post('http://localhost:13002/auth/login', json={'username':'testuser','password':'test123456'})
token = r.json()['access_token']
H = {'Authorization': f'Bearer {token}'}
r = httpx.get('http://localhost:13002/api/health-records', headers=H)
print('HTTP:', r.status_code)
data = r.json()
print('Count:', len(data) if isinstance(data, list) else 'N/A')
if isinstance(data, list):
    for rec in data[:5]:
        print(f"  - [{rec.get('record_type', '?')}] {rec.get('title', '?')[:50]}")