"""Debug: dump all SSE events from add_medication_reminder."""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("=== Test: 添加用药提醒 ===")
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "帮我添加一个药物提醒: 维生素 C 片 100mg, 每天早上 9 点服用"},
                  headers=h, timeout=90) as resp:
    print(f"Status: {resp.status_code}")
    for line in resp.iter_lines():
        if line:
            print(line[:200])
