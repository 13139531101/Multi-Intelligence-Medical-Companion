import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# 查 R-C.jpg 的状态
print("=== /v2/upload/files (限 50) 找 R-C.jpg ===")
r2 = httpx.get("http://localhost:13002/v2/upload/files",
               params={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a", "limit": "200"},
               headers=H, timeout=10)
for f in r2.json():
    if "R-C" in (f.get("original_name") or ""):
        print(f"  fid={f['id']} name={f['original_name']} ocr={f['ocr_status']} mime={f['mime_type']} size={f.get('size_bytes')}")
        print(f"  ocr_text (前 300 字): {(f.get('ocr_text') or '')[:300]!r}")

# 查 health-records 列表, 找有 R-C.jpg 的
print("\n=== /api/health-records 哪些 record.files 含此 fid ===")
r3 = httpx.get("http://localhost:13002/api/health-records", headers=H, params={"limit": "200"}, timeout=10)
for rec in r3.json():
    files = rec.get("files") or []
    if "292c452c-1560-4f0f-a7bf-d2e88e221532" in files:
        print(f"  HIT: id={rec['id']} title={rec.get('title')}")
        print(f"    files = {files}")
        meta = rec.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        print(f"    meta._attached_files_meta = {meta.get('_attached_files_meta', [])[:2]}")
        # content / description
        print(f"    description={rec.get('description')[:200]!r}")
        print(f"    content={rec.get('content')[:200]!r}")

# 单独拿这条 record
print("\n=== /api/health-records/{id} (单个取) ===")
rec_id = rec['id']
r4 = httpx.get(f"http://localhost:13002/api/health-records/{rec_id}", headers=H, timeout=10)
d = r4.json()
print(json.dumps({k: d.get(k) for k in ['id','title','content','description','files','metadata']}, ensure_ascii=False, indent=2)[:1500])
