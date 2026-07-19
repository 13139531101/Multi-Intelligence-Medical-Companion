"""阶段48-22 v2: E2E A+B. Skip POST /api/health-records (proxy bug) — create via raw DB insert."""
import asyncio
import httpx
import json
import uuid

USER_ID = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"


async def main():
    r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    print("=== A. Upload 2 files (only upload+OCR) ===")
    file_ids = []
    for name, txt in [
        ("lab_report.csv", "姓名: 张三\n空腹血糖 7.1\n血压 145/95"),
        ("xray.png", bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001")),
    ]:
        files = {"file": (name, txt if isinstance(txt, bytes) else txt.encode("utf-8"),
                          "image/png" if name.endswith(".png") else "text/csv")}
        data = {"user_id": USER_ID, "domain": "pha", "purpose": "health_record", "metadata": '{"step":"A"}'}
        r = httpx.post("http://localhost:13002/v2/upload/file", headers=h, files=files, data=data, timeout=30)
        d = r.json()
        file_ids.append(d["file_id"])
        print(f"  uploaded {name}: file_id={d['file_id']}")
    assert len(file_ids) == 2

    await asyncio.sleep(2)

    # ----- B': directly insert record via DB (绕开 api.py 的 sys.modules bug) -----
    print("\n=== B'. Insert health_record via DB (proxy 不工作) ===")
    rid = str(uuid.uuid4())
    import subprocess
    res = subprocess.run(
        ["docker", "exec", "a2aserver-hostapi-stage39", "python3", "-c", f"""
import psycopg, os
from psycopg.rows import dict_row
dsn = f"postgresql://{{os.getenv('DB_USER','pha')}}:{{os.getenv('DB_PASSWORD','')}}@{{os.getenv('DB_HOST','postgres')}}:5432/{{os.getenv('MEMORY_DB_NAME','personal_health_assistant')}}"
conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
conn.execute(
    'INSERT INTO health_records (id, user_id, title, record_type, summary, content, importance, tags, metadata, record_date) '
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, CURRENT_DATE)",
    ('{rid}', '{USER_ID}', '2024-01 体检报告 (created by test)', 'lab_report',
     '空腹血糖偏高', '空腹血糖 7.1 mmol/L', 'high',
     '["糖尿病筛查"]', '{{}}')
)
print(f'created record id={{rid}}')
"""],
        capture_output=True, text=True, timeout=20,
    )
    print(res.stdout)
    if res.stderr: print("STDERR:", res.stderr[:200])

    # ----- B: attach-files -----
    print(f"\n=== B. POST /api/v2-attach/health_records/{{rid[:8]}}/attach-files ===")
    r = httpx.post(
        f"http://localhost:13002/api/v2-attach/health_records/{rid}/attach-files",
        headers=h,
        params={"user_id": USER_ID},
        json={"file_ids": file_ids, "replace": True},
        timeout=10,
    )
    print(f"  status: {r.status_code}")
    print(f"  body: {r.text[:300]}")

    # GET attached files
    r = httpx.get(
        f"http://localhost:13002/api/v2-attach/health_records/{rid}/files",
        headers=h, params={"user_id": USER_ID}, timeout=5,
    )
    print(f"\n=== GET /attached files: {r.status_code} ===")
    if r.status_code == 200:
        for f in r.json():
            print(f"  - {f['original_name']} ({f.get('size_bytes',0)}B) url={f['public_url']}")

    # detach 1
    if file_ids:
        r = httpx.post(
            f"http://localhost:13002/api/v2-attach/health_records/{rid}/detach-files",
            headers=h,
            params={"user_id": USER_ID},
            json={"file_ids": [file_ids[0]]},
            timeout=10,
        )
        print(f"\n=== POST detach-files: {r.status_code} ===")
        print(f"  body: {r.text[:200]}")

    r = httpx.get(
        f"http://localhost:13002/api/v2-attach/health_records/{rid}/files",
        headers=h, params={"user_id": USER_ID}, timeout=5,
    )
    if r.status_code == 200:
        items = r.json()
        print(f"\n=== After detach: {len(items)} file(s) attached ===")
        for f in items:
            print(f"  - {f['original_name']}")

if __name__ == "__main__":
    asyncio.run(main())
