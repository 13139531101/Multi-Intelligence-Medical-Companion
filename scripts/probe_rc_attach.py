import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# 看哪些 record 里面有 R-C.jpg 的 fid
r2 = httpx.get("http://localhost:13002/api/health-records", headers=H, params={"limit": "200"}, timeout=10)
target_fids = {"362abdbb-bc03-4307-9318-0dd5b928a619", "292c452c-1560-4f0f-a7bf-d2e88e221532", "5aec38ce-f484-4261-8796-8f0637fc190c"}
for rec in r2.json():
    files = rec.get("files") or []
    meta = rec.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    afids = meta.get("attached_file_ids") or []
    if target_fids & set(files) or target_fids & set(afids):
        print(f"HIT: id={rec['id']}, title={rec.get('title')!r}")
        print(f"   files(top-level) = {files}")
        print(f"   metadata.attached_file_ids = {afids}")
        attach_meta = meta.get("_attached_files_meta", [])
        print(f"   _attached_files_meta = {len(attach_meta)} items")
        for m in attach_meta:
            print(f"     - {m.get('file_name')} ({m.get('file_id')[:8]}...) ocr={m.get('ocr_status')}")
