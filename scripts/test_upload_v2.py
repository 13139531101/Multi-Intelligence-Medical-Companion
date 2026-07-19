"""阶段48-22: E2E test for Upload Pipeline v2."""
import asyncio
import httpx
import sys
import io
import tempfile
import os

# Create a fake image (tiny PNG bytes)
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c630001000000050001006d539a3a0000000049454e44ae426082"
)

async def main():
    # 1. login
    r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    user_id = r.json()["user"]["user_id"]
    h = {"Authorization": f"Bearer {token}"}
    print(f"Logged in as {user_id}")

    # 2. upload
    print("\n=== Uploading test PNG (purpose=health_record) ===")
    files = {"file": ("report.png", PNG_BYTES, "image/png")}
    data = {"user_id": user_id, "domain": "pha", "purpose": "health_record", "metadata": '{"note":"e2e test"}'}
    r = httpx.post("http://localhost:13002/v2/upload/file", headers=h, files=files, data=data, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text}")
    if r.status_code != 200:
        return
    res = r.json()
    file_id = res["file_id"]

    # 3. wait for OCR
    print("\n=== Waiting for OCR/attach (10s) ===")
    await asyncio.sleep(10)
    r = httpx.get(f"http://localhost:13002/v2/upload/file/{file_id}", headers=h, params={"user_id": user_id}, timeout=5)
    print(f"GET /upload/file/{{file_id}}: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  ocr_status: {d.get('ocr_status')}")
        print(f"  attached_table: {d.get('attached_table')}")
        print(f"  attached_id: {d.get('attached_id')}")
        print(f"  ocr_text: {(d.get('ocr_text') or '')[:200]}")

    # 4. list files
    print("\n=== List files (purpose=health_record) ===")
    r = httpx.get("http://localhost:13002/v2/upload/files", headers=h, params={"user_id": user_id, "purpose": "health_record"}, timeout=5)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        items = r.json()
        print(f"Total: {len(items)}")
        for it in items[:3]:
            print(f"  - {it['id'][:8]}... | {it['original_name']} | ocr={it['ocr_status']} | attached={it.get('attached_record_id', 'none')[:8] if it.get('attached_record_id') else 'none'}")

    # 5. fetch via file serve
    print("\n=== Fetch file content ===")
    r = httpx.get(f"http://localhost:13002/v2/files/{file_id}", timeout=5)
    print(f"Status: {r.status_code}, Content-Type: {r.headers.get('content-type')}, size: {len(r.content)} bytes")

if __name__ == "__main__":
    asyncio.run(main())
