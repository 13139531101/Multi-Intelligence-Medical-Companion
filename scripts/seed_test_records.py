"""种子测试数据"""
import httpx
r = httpx.post('http://localhost:13002/auth/login', json={'username':'testuser','password':'test123456'})
token = r.json()['access_token']
H = {'Authorization': f'Bearer {token}'}
test_records = [
    {'title': '原发性高血压诊断', 'type': 'diagnosis', 'description': 'BP 145/95，处方硝苯地平 30mg qd', 'date': '2026-07-10'},
    {'title': '血常规检查', 'type': 'exam', 'description': '白细胞 6.5, 血红蛋白 135', 'date': '2026-07-05'},
    {'title': '青霉素过敏', 'type': 'allergy', 'description': '皮试阳性, 皮疹呼吸困难', 'date': '2026-06-20'},
    {'title': '胸部 CT 检查', 'type': 'report', 'description': '双肺纹理清晰, 未见明显实变', 'date': '2026-05-15'},
]
for rec in test_records:
    r = httpx.post('http://localhost:13002/api/health-records', headers=H, json=rec)
    title = rec['title']
    print(f'  - {title}: {r.status_code}')
print('OK')