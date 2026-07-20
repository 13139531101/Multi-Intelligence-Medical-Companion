import httpx
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]

# 列出 v2/upload/files (user=1111)
r2 = httpx.get(
    "http://localhost:13002/v2/upload/files",
    params={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a", "limit": "20"},
    headers={"Authorization": f"Bearer {tok}"},
    timeout=10,
)
print(f"/v2/upload/files: HTTP {r2.status_code}")
if r2.status_code == 200:
    rows = r2.json()
    print(f"got {len(rows)} files")
    for row in rows[:5]:
        print(f"  fid={row['id']} name={row['original_name']} ocr={row['ocr_status']} mime={row['mime_type']}")

    if rows:
        first = rows[0]
        # 测 /v2/files/{id}
        r3 = httpx.get(f"http://localhost:13002/v2/files/{first['id']}", timeout=10)
        print(f"\n/v2/files/{first['id'][:8]}...: HTTP {r3.status_code}, bytes={len(r3.content)}, mime={r3.headers.get('content-type')}, body[:80]={r3.content[:80]}")
