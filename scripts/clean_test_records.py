"""阶段47: 清理脏数据 - 删除 hash 命名的测试记录"""
import httpx
import sys

# 1. 登录
r = httpx.post('http://localhost:13002/auth/login', json={'username':'testuser','password':'test123456'})
if r.status_code != 200:
    print(f'登录失败: {r.status_code}')
    sys.exit(1)
token = r.json().get('access_token')
print('登录成功')

# 2. 拿所有 records
r = httpx.get('http://localhost:13002/api/health-records',
              headers={'Authorization': f'Bearer {token}'})
records = r.json()
print(f'找到 {len(records)} 条记录')

# 3. 删除 hash 命名的（title 包含 long alphanumeric + .png/.jpg）
import re
deleted = 0
for rec in records:
    title = rec.get('title', '')
    # 检测是否是文件名 hash: 长字符串 + 后缀
    if re.search(r'- [A-Za-z0-9]{20,}\.(png|jpg|jpeg|pdf)$', title):
        rid = rec.get('id')
        print(f'  删除: {title[:60]}... (id={rid})')
        rd = httpx.delete(f'http://localhost:13002/api/health-records/{rid}',
                          headers={'Authorization': f'Bearer {token}'})
        if rd.status_code in (200, 204):
            deleted += 1
        else:
            print(f'  删除失败: {rd.status_code} {rd.text}')

print(f'\n删除 {deleted} 条脏数据')
print(f'剩余 {len(records) - deleted} 条记录')