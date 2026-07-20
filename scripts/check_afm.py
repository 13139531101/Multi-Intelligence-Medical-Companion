import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
r2 = httpx.get("http://localhost:13002/api/health-records/f7e82145-f4e4-41c9-84e5-563833b0050f", headers=H, timeout=10)
d = r2.json()
print(f"HTTP {r2.status_code} title={d.get('title')}")
meta = d.get("metadata") or {}
print("meta keys:", list(meta.keys()))
afm = meta.get("_attached_files_meta") or []
print(f"_attached_files_meta has {len(afm)} items")
for f in afm:
    text = f.get("ocr_text") or ""
    print(f"  -> {f.get('file_name')} ocr_status={f.get('ocr_status')} ocr_text_len={len(text)}")
    if f.get("ocr_status") == "done":
        print("     text-preview:", repr(text[:120]))
