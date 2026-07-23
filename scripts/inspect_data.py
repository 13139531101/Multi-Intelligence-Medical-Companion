import httpx
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
USER = 'user_4e3ef0b3f49d8d4433e0b4420a3bae2a'
recs = httpx.get('http://localhost:13002/api/health-records', headers={'Authorization': 'Bearer '+tok}, timeout=10).json()
meds_raw = httpx.get('http://localhost:13002/api/medication-reminders/today', params={'user_id': USER}, headers={'Authorization': 'Bearer '+tok}, timeout=10).json()
print(f'recs: {len(recs)} items')
print(f'meds_raw type: {type(meds_raw).__name__}, keys: {list(meds_raw.keys()) if isinstance(meds_raw, dict) else None}')

if isinstance(meds_raw, dict):
    for k in meds_raw:
        v = meds_raw[k]
        print(f'  {k}: {type(v).__name__}, len={len(v) if isinstance(v, (list, dict)) else "n/a"}')
    medList = meds_raw.get('reminders') or meds_raw.get('medications') or meds_raw.get('data') or []
else:
    medList = meds_raw if isinstance(meds_raw, list) else []
print(f'medList: {len(medList)} items')
if medList and isinstance(medList[0], dict):
    print(f'first med: {medList[0]}')
