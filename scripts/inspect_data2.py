import httpx, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
USER='user_4e3ef0b3f49d8d4433e0b4420a3bae2a'
# Verify the actual data path
recs = httpx.get('http://localhost:13002/api/health-records', headers={'Authorization': 'Bearer '+tok}, timeout=10).json()
meds = httpx.get('http://localhost:13002/api/medication-reminders', params={'today': 'true', 'user_id': USER}, headers={'Authorization': 'Bearer '+tok}, timeout=10).json()
print(f'recs: type={type(recs).__name__}, len={len(recs) if isinstance(recs, list) else "n/a"}')
print(f'meds: type={type(meds).__name__}, len={len(meds) if isinstance(meds, list) else "n/a"}')
print(f'first med: {meds[0] if meds and isinstance(meds, list) else meds}')
# Now mimic Dashboard logic
recList = recs if isinstance(recs, list) else (recs.get('records') if isinstance(recs, dict) else [])
medList = meds if isinstance(meds, list) else (meds.get('reminders') if isinstance(meds, dict) else [])
print(f'recList: {len(recList)}, medList: {len(medList)}')

# Simulate computeCoverage — 5 categories: examination/exam/check/allergy/medication/report/treatment
def cov(records):
    if not records: return 0
    types = set()
    for r in records:
        rt = r.get('record_type') or r.get('type') or 'other'
        if rt in ('examination', 'exam', 'check', '检查'):
            types.add('check')
        elif rt in ('allergy', '过敏'):
            types.add('allergy')
        elif rt in ('medication', 'med', '用药'):
            types.add('medication')
        elif rt in ('report', '报告'):
            types.add('report')
        elif rt in ('treatment', 'visit', '诊断', 'treatment'):
            types.add('treatment')
    return len(types) / 5 * 100

def comp(reminders):
    if not reminders: return 0
    taken = sum(1 for r in reminders if r.get('taken') or r.get('status') == 'taken')
    return (taken / len(reminders)) * 100

def act(consultations):
    # placeholder
    return 0

print(f'cov: {cov(recList):.1f}%')
print(f'comp: {comp(medList):.1f}%')
# rough
score = comp(medList) * 0.35 + cov(recList) * 0.25 + act([]) * 0.2 + 50 * 0.2
print(f'estimated score: {score:.1f}')
