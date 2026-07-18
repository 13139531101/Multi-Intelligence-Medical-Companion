import httpx
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
for a in ["all", "health_advisor", "medication_reminder", "health_records", "visit_summary"]:
    if a == "all":
        r = httpx.get("http://localhost:13002/api/consultations", headers=H)
    else:
        r = httpx.get(f"http://localhost:13002/api/consultations?agent_id={a}", headers=H)
    data = r.json()
    n = len(data) if isinstance(data, list) else "?"
    print(f"[{a:22s}] count={n}")
    if isinstance(data, list) and data:
        d0 = data[0]
        print(f"  first: title='{d0.get('title', '')[:30]}', agent={d0.get('agentId')}")
