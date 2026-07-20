import httpx, json

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

r2 = httpx.get("http://localhost:13002/api/health-records?limit=3", headers=H, timeout=10)
data = r2.json()
print(f"got {len(data)} records")
for rec in data:
    print(f"--- id={rec.get('id')} title={rec.get('title')[:40]}")
    print(f"  files (top-level) = {rec.get('files')!r}")
    meta = rec.get("metadata") or {}
    if isinstance(meta, str):
        try:
            import json as _j
            meta = _j.loads(meta)
        except Exception:
            meta = {}
    print(f"  metadata.attached_file_ids = {meta.get('attached_file_ids') if isinstance(meta, dict) else 'N/A'}")
    print(f"  other top-level keys with 'file' = {[k for k in rec.keys() if 'file' in k.lower()]}")
