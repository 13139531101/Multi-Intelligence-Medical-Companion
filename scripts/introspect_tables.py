"""Query actual health_records / visit_summaries schemas."""
import httpx
import sys
import os

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

# Try fetching records list (this works through whatever schema)
r = httpx.get("http://localhost:13002/api/health-records", headers=h, timeout=5)
print(f"GET /api/health-records: {r.status_code}, count={len(r.json()) if r.status_code==200 else 0}")
if r.status_code == 200:
    recs = r.json()
    if recs:
        print(f"\nFirst record full schema:")
        for k in sorted(recs[0].keys()):
            v = recs[0][k]
            if isinstance(v, (str, int, float, list, dict, type(None))):
                print(f"  {k}: {str(v)[:80]}")
            else:
                print(f"  {k}: <{type(v).__name__}>")

# V2 health records endpoint test
print("\n--- now test upload_pipeline path ---")

# Try direct introspection with psql via running python -c
import json
import subprocess
res = subprocess.run(
    ["docker", "exec", "a2aserver-hostapi-stage39", "python3", "-c", """
import psycopg, os, json
from psycopg.rows import dict_row
dsn = f"postgresql://{os.getenv('DB_USER','pha')}:{os.getenv('DB_PASSWORD','')}@{os.getenv('DB_HOST','postgres')}:5432/{os.getenv('MEMORY_DB_NAME','personal_health_assistant')}"
conn = psycopg.connect(dsn, row_factory=dict_row)
for table in ['health_records', 'visit_summaries', 'uploaded_files']:
    cols = conn.execute(f\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position\", (table,)).fetchall()
    print(f'== {table} ({len(cols)} cols) ==')
    for c in cols:
        print(f\"  {c['column_name']:30} {c['data_type']}\")
"""],
    capture_output=True, text=True, timeout=20,
)
print(res.stdout)
print(res.stderr[:500] if res.stderr else "")
