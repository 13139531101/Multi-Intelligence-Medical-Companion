"""阶段48-22: try with text text file (not OCR-able, just to test attach)."""
import asyncio
import httpx

async def main():
    r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    user_id = r.json()["user"]["user_id"]
    h = {"Authorization": f"Bearer {token}"}

    print("=== Upload text/csv (no OCR, will skip + attach only) ===")
    text = "姓名: 张三\n2024-01-15 体检\n空腹血糖: 6.5 mmol/L\n血压: 130/85"
    files = {"file": ("lab_report.csv", text.encode("utf-8"), "text/csv")}
    data = {"user_id": user_id, "domain": "pha", "purpose": "health_record", "metadata": '{"source":"e2e"}'}
    r = httpx.post("http://localhost:13002/v2/upload/file", headers=h, files=files, data=data, timeout=30)
    print(f"Upload: {r.status_code}")
    res = r.json()
    file_id = res.get("file_id")
    print(f"  file_id={file_id}")

    if not file_id:
        return

    await asyncio.sleep(2)

    # 3. wait for attach
    print(f"\n=== Check file after 2s ===")
    r = httpx.get(f"http://localhost:13002/v2/upload/file/{file_id}", headers=h, params={"user_id": user_id}, timeout=5)
    d = r.json()
    print(f"  ocr_status: {d.get('ocr_status')}")
    print(f"  attached_table: {d.get('attached_table')}")
    print(f"  attached_id: {d.get('attached_id')}")

    # verify health_records row exists
    if d.get('attached_id'):
        r2 = httpx.get(f"http://localhost:13002/api/health-records/{d['attached_id']}", headers=h, params={"user_id": user_id}, timeout=5)
        print(f"\n  GET /api/health-records/{{attached_id}}: {r2.status_code}")
        if r2.status_code == 200:
            rec = r2.json()
            print(f"  title: {rec.get('title')}")
            print(f"  description: {(rec.get('description') or '')[:200]}")

if __name__ == "__main__":
    asyncio.run(main())
