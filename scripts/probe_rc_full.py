import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
r2 = httpx.get("http://localhost:13002/v2/upload/files",
               params={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a", "limit": "50"}, headers=H, timeout=10)
files = r2.json()
# 找 R-C.jpg
for f in files[:5]:
    if "R-C" in (f.get("original_name") or ""):
        print(f"=== {f['original_name']} ({f['id'][:8]}...) ocr={f['ocr_status']} ({len(f.get('ocr_text') or '')}字) ===")
        text = f.get("ocr_text") or ""
        print(text[:1500])
        print("---END---")
        break
