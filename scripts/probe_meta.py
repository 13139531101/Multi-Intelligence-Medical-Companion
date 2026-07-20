import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
r2 = httpx.get("http://localhost:13002/api/health-records/9e68d18e-233d-4990-b5f2-e0c84c6219dc", headers=H, timeout=10)
d = r2.json()
print(f"HTTP {r2.status_code}, keys = {list(d.keys())[:20]}")
print(f"files = {d.get('files')}")
meta = d.get('metadata', {})
if isinstance(meta, str):
    meta = json.loads(meta)
print(f"metadata._attached_files_meta = {json.dumps(meta.get('_attached_files_meta', []), ensure_ascii=False, indent=2)[:1500]}")
