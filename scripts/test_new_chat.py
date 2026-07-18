"""test new chat writes agent_id properly."""
import httpx, json, time

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

# 发一个新的问题 (应该被路由到 health_advisor 因为健康相关)
qs = [
    "我血压 145/95 怎么办?",
    "今天吃什么药",
    "帮我上传体检报告",
]

for q in qs:
    print(f"\n>>> Q: {q}")
    with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                      headers=H, json={"message": q}, timeout=30) as r:
        buffer = ""
        for raw in r.iter_lines():
            if not raw: continue
            line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            buffer += line + "\n"
            if line.startswith("event: routing"):
                continue
            if line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                    if "agent" in d and "routing" in d:
                        print(f"    routed -> {d.get('agent')}")
                        break
                    if "agent" in d:
                        print(f"    routed -> {d['agent']}")
                        break
                except:
                    pass
    time.sleep(0.5)

# 再查历史
print("\n=== check final counts ===")
for a in ["health_advisor", "medication_reminder", "health_records"]:
    r = httpx.get(f"http://localhost:13002/api/consultations?agent_id={a}", headers=H)
    data = r.json()
    n = len(data) if isinstance(data, list) else "?"
    print(f"  [{a:22s}] count={n}")
