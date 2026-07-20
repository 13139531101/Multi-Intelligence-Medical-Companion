"""阶段48-22 v6: 全量补跑 skipped 的 OCR.

对每个 user, 把所有 ocr_status='skipped' 的 file 调一次 reextract.
不要 force — 如果 done 不重跑. 但这里只查 skipped 所以都是要跑的.
"""
import httpx, time

UID = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# 1. 列所有 skipped
r2 = httpx.get("http://localhost:13002/v2/upload/files",
               params={"user_id": UID, "limit": "200"},
               headers=H, timeout=10)
files = r2.json()
target = [f for f in files if f.get("ocr_status") == "skipped" and (f.get("mime_type") or "").startswith("image/")]
print(f"target = {len(target)} skipped image files")
print(f"skipped non-image = {len([f for f in files if f.get('ocr_status') == 'skipped' and not (f.get('mime_type') or '').startswith('image/')])}")

success = 0
fail = 0
for f in target:
    fid = f["id"]
    name = f.get("original_name", fid[:8])
    print(f"  OCR {name}... ", end="", flush=True)
    try:
        r3 = httpx.post(
            f"http://localhost:13002/v2/upload/files/{fid}/reextract",
            json={"user_id": UID, "force": True},
            headers=H, timeout=120,
        )
        if r3.status_code == 200:
            j = r3.json()
            if j.get("ocr_status") == "done":
                success += 1
                print(f"OK ({len(j.get('ocr_text') or '')} 字)")
            else:
                fail += 1
                print(f"FAIL ({j.get('message') or j.get('ocr_status')})")
        else:
            fail += 1
            print(f"HTTP {r3.status_code}: {r3.text[:120]}")
    except Exception as e:
        fail += 1
        print(f"EXC: {e!r}")

print(f"\nDONE: {success}/{len(target)} succeeded, {fail} failed")
