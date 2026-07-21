import httpx, time
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# 拉之前那条 R-C.jpg fid
fid = "362abdbb-bc03-4307-9318-0dd5b928a619"
uid = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"

# 看关联 record 的 content 现在是什么样
r2 = httpx.get(f"http://localhost:13002/api/health-records", headers=H, params={"limit": "200"}, timeout=10)
target = None
for rec in r2.json():
    files = rec.get("files") or []
    meta = rec.get("metadata") or {}
    if isinstance(meta, str):
        import json as _
        meta = json.loads(meta)
    afids = meta.get("attached_file_ids") or []
    if fid in files or fid in afids:
        target = rec
        break
print(f"BEFORE: record.id={target['id']}")
print(f"  title={target.get('title')!r}")
print(f"  content_len={len(target.get('content') or '')}")
print(f"  content[:300]={(target.get('content') or '')[:300]!r}")

# 现在 reextract 应该会触发自动 merge
r3 = httpx.post(
    f"http://localhost:13002/v2/upload/files/{fid}/reextract",
    json={"user_id": uid, "force": True},
    headers=H,
    timeout=60,
)
print(f"\nreextract: HTTP {r3.status_code}, ocr_status={r3.json().get('ocr_status')}, text_len={len(r3.json().get('ocr_text') or '')}")

# 重新查 record
r4 = httpx.get(f"http://localhost:13002/api/health-records/{target['id']}", headers=H, timeout=10)
d = r4.json()
print(f"\nAFTER: content_len={len(d.get('content') or '')}")
print(f"  content[:600]={(d.get('content') or '')[:600]!r}")
