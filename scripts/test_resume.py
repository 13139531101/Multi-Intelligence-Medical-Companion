"""Smoke-test: resume endpoint with bad auth returns proper error."""
import httpx, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test resume with empty/invalid body
r = httpx.post("http://localhost:13002/v2/chat/resume", headers=h,
               json={"thread_id": "test_thread_id", "decisions": [{"type": "approve"}]})
print(f"Status: {r.status_code}")
print(f"Body[:300]: {r.text[:300]}")
