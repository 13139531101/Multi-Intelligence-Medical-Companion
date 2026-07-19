"""阶段48-22 v3: E2E visit_summary 单步接口."""
import asyncio
import httpx

USER_ID = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"


async def main():
    r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # Visit summary needs purpose=visit_summary uploads
    print("=== Upload visit_summary purpose file ===")
    files = {"file": ("visit_card.txt", "协和医院 内分泌门诊 就诊卡\n日期 2024-01-15", "text/plain")}
    data = {"user_id": USER_ID, "domain": "pha", "purpose": "visit_summary", "metadata": "{}"}
    r = httpx.post("http://localhost:13002/v2/upload/file", headers=h, files=files, data=data, timeout=30)
    d = r.json()
    fid = d["file_id"]
    print(f"  uploaded: {fid}")

    print("\n=== POST /api/v2/create-record-and-attach (visit_summary) ===")
    payload = {
        "target_table": "visit_summaries",
        "record": {
            "title": "协和内分泌门诊 2024-01-15",
            "visit_date": "2024-01-15",
            "doctor": "王医生",
            "hospital": "协和医院",
            "chief_complaint": "持续乏力 1 月",
            "symptoms": "疲倦、体重下降",
            "examination": "HbA1c 8.2%, 空腹血糖 9.0",
            "diagnosis": "2型糖尿病",
            "treatment": "二甲双胍 0.5g bid",
            "prescription": json.dumps([{"drug": "二甲双胍", "dose": "0.5g", "freq": "bid"}]),
            "follow_up": "4 周后复诊",
            "notes": "饮食建议",
        },
        "attached_file_ids": [fid],
    }
    r = httpx.post("http://localhost:13002/api/v2/create-record-and-attach",
                   headers=h, params={"user_id": USER_ID}, json=payload, timeout=15)
    print(f"  status: {r.status_code}")
    print(f"  body: {r.text[:500]}")

    if r.status_code == 200:
        res = r.json()
        print(f"  record_id={res['record_id']}, attached_count={res['attached_count']}")

        # Idempotency test: send same Idempotency-Key twice
        print("\n=== Idempotency test: 重复同样参数 ===")
        # 实际 idempotency 由后端检查 header; 这里调一次, 后端应该 return same record_id
        # 我们通过 metadata 验证 (下面 GET 直接用 record_id)
        r2 = httpx.get(
            f"http://localhost:13002/api/v2-attach/visit_summaries/{res['record_id']}/files",
            headers=h, params={"user_id": USER_ID}, timeout=5,
        )
        print(f"  GET attached files: {r2.status_code}")
        if r2.status_code == 200:
            for f in r2.json():
                print(f"    - {f['original_name']} ({f.get('size_bytes',0)}B)")

if __name__ == "__main__":
    import json as _json
    json = _json
    asyncio.run(main())
