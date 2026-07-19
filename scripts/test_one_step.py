"""阶段48-22 v2+: E2E 单步 create-record-and-attach."""
import asyncio
import httpx

USER_ID = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"


async def main():
    r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # Upload 2 files (A)
    print("=== Step 1: Upload 2 files (A) ===")
    file_ids = []
    for name, txt in [
        ("lab_2024.csv", "姓名: 张三\n空腹血糖 7.1\n血压 145/95"),
        ("ct_note.png", "CT 影像备注 — 肺部无明显异常"),
    ]:
        files = {"file": (name, txt.encode("utf-8"), "image/png" if name.endswith(".png") else "text/csv")}
        data = {"user_id": USER_ID, "domain": "pha", "purpose": "health_record", "metadata": '{"test":"one-step"}'}
        r = httpx.post("http://localhost:13002/v2/upload/file", headers=h, files=files, data=data, timeout=30)
        d = r.json()
        file_ids.append(d["file_id"])
        print(f"  uploaded {name}: {d['file_id']}")

    # Step 2: single-step create + attach (B+C one-call)
    print(f"\n=== Step 2: ONE-STEP POST /api/v2/create-record-and-attach ===")
    payload = {
        "target_table": "health_records",
        "record": {
            "title": "2024-01 体检 (one-step)",
            "record_type": "lab_report",
            "record_date": "2024-01-15",
            "hospital": "协和医院",
            "doctor": "李医生",
            "summary": "空腹血糖偏高",
            "content": "完整内容:\n空腹血糖 7.1 mmol/L\n血压 145/95",
            "importance": "high",
            "tags": ["糖尿病筛查", "高血压关注"],
        },
        "attached_file_ids": file_ids,
    }
    r = httpx.post("http://localhost:13002/api/v2/create-record-and-attach",
                   headers=h, params={"user_id": USER_ID}, json=payload, timeout=15)
    print(f"  status: {r.status_code}")
    print(f"  body: {r.text[:500]}")

    if r.status_code != 200:
        return

    res = r.json()
    rid = res["record_id"]

    # Verify attach worked
    print(f"\n=== Step 3: Verify attach ===")
    r = httpx.get(f"http://localhost:13002/api/v2-attach/health_records/{rid}/files",
                  headers=h, params={"user_id": USER_ID}, timeout=5)
    if r.status_code == 200:
        items = r.json()
        print(f"  GET attached files: {len(items)} file(s)")
        for f in items:
            print(f"    - {f['original_name']} ({f.get('size_bytes',0)}B) url={f['public_url']}")


if __name__ == "__main__":
    asyncio.run(main())
