"""Test HITL with direct add_medication_reminder."""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "请帮我添加一个新药提醒: 早上 8 点吃葡萄糖酸锌片 50mg"},
                  headers=h, timeout=120) as resp:
    print(f"Status: {resp.status_code}")
    chunks = []
    for line in resp.iter_lines():
        if line:
            print("chunk:", line[:200])
            chunks.append(line)
