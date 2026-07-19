import httpx
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=5)
r.raise_for_status()
tok = r.json()["access_token"]
print("login ok, token len=", len(tok))

# Health records list
r2 = httpx.get("http://localhost:13002/api/health-records", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
print(f"GET /api/health-records: HTTP {r2.status_code}")
print(f"  body[0:200]: {r2.text[:200]}")
