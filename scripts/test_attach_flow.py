"""阶段48-22 v2: E2E test A+B 架构.

A: POST /v2/upload/file (only upload + OCR)
B: POST /api/v2-attach/health_records/<id>/attach-files (explicit link)
"""
import asyncio
import httpx

USER_ID = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"


async def main():
    r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # ----- A: upload 2 files -----
    print("=== A. Upload 2 files (only) ===")
    file_ids = []
    for i, (name, txt) in enumerate([
        ("lab_report.csv", "姓名: 张三\n空腹血糖 7.1\n血压 145/95\n总胆固醇 5.9"),
        ("xray.png", "fake_xray_bytes"),     # will fail OCR
    ]):
        files = {"file": (name, txt.encode("utf-8") if isinstance(txt, str) else txt.encode("latin-1"),
                          "image/png" if i == 1 else "text/csv")}
        data = {"user_id": USER_ID, "domain": "pha", "purpose": "health_record", "metadata": '{"step":"A"}'}
        r = httpx.post("http://localhost:13002/v2/upload/file", headers=h, files=files, data=data, timeout=30)
        d = r.json()
        file_ids.append(d["file_id"])
        print(f"  uploaded {name}: file_id={d['file_id']}, status={r.status_code}")
    assert len(file_ids) == 2

    await asyncio.sleep(3)  # let OCR run

    # ----- B: create health_records row, then attach -----
    print("\n=== B. Create health_records + attach-files ===")
    payload = {
        "title": "2024-01 体检报告",
        "record_type": "lab_report",
        "record_date": "2024-01-15",
        "hospital": "协和医院",
        "doctor": "李医生",
        "importance": "high",
        "summary": "空腹血糖偏高",
        "tags": ["糖尿病筛查"],
    }
    r = httpx.post("http://localhost:13002/api/health-records", headers=h,
                   params={"user_id": USER_ID}, json=payload, timeout=10)
    print(f"  POST /api/health-records: {r.status_code}")
    if r.status_code != 200:
        print(f"  BODY: {r.text[:300]}")
        return
    rec = r.json()
    rid = rec["id"]
    print(f"  created record: id={rid}, title={rec.get('title')}")

    # Now attach the 2 files
    r = httpx.post(
        f"http://localhost:13002/api/v2-attach/health_records/{rid}/attach-files",
        headers=h,
        params={"user_id": USER_ID},
        json={"file_ids": file_ids, "replace": True},
        timeout=10,
    )
    print(f"\n  POST attach-files: {r.status_code}")
    print(f"  BODY: {r.text}")

    # List attached files
    r = httpx.get(
        f"http://localhost:13002/api/v2-attach/health_records/{rid}/files",
        headers=h, params={"user_id": USER_ID}, timeout=5,
    )
    print(f"\n  GET attached files: {r.status_code}")
    if r.status_code == 200:
        for f in r.json():
            print(f"    - {f['original_name']} ({f.get('size_bytes',0)} B) ocr={f.get('ocr_status')} url={f['public_url']}")

    # detach 1
    if file_ids:
        r = httpx.post(
            f"http://localhost:13002/api/v2-attach/health_records/{rid}/detach-files",
            headers=h,
            params={"user_id": USER_ID},
            json={"file_ids": [file_ids[0]]},
            timeout=10,
        )
        print(f"\n  POST detach-files [{file_ids[0][:8]}]: {r.status_code}")
        print(f"  BODY: {r.text[:200]}")

    # verify still attached
    r = httpx.get(
        f"http://localhost:13002/api/v2-attach/health_records/{rid}/files",
        headers=h, params={"user_id": USER_ID}, timeout=5,
    )
    if r.status_code == 200:
        items = r.json()
        print(f"\n  After detach: {len(items)} files attached")
        for f in items:
            print(f"    - {f['original_name']} url={f['public_url']}")

if __name__ == "__main__":
    asyncio.run(main())
