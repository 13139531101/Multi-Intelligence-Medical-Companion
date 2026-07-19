"""Test HITL interrupt emission.
Trigger 'add_medication_reminder' tool call (interrupt_on add_medication_reminder).
Expected: stream emits 'event: interrupt' before 'event: done'.
"""
import httpx, json, sys, os
sys.stdout.reconfigure(encoding="utf-8")

# Login
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Try 1: ask add medication reminder explicitly
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "帮我添加一个药物提醒: 阿司匹林肠溶片, 100mg, 每天早上 8 点服用"},
                  headers=h, timeout=60) as resp:
    print(f"Status: {resp.status_code}")
    chunks = []
    for line in resp.iter_lines():
        if line:
            chunks.append(line)

print(f"\n总 chunk 数: {len(chunks)}")
print("\n=== 关键事件 ===")
for ln in chunks:
    if 'interrupt' in ln.lower() or 'add_medication' in ln.lower() or 'tool_call' in ln:
        print(ln[:200])

# Try 2: prompt to delete a record (high-risk interrupt tool)
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "请帮我删除用药提醒 35"},
                  headers=h, timeout=60) as resp:
    print(f"\n\n--- Test 2: delete reminder ---\nStatus: {resp.status_code}")
    chunks = []
    for line in resp.iter_lines():
        if line:
            chunks.append(line)
print(f"总 chunk 数: {len(chunks)}")
for ln in chunks:
    if 'interrupt' in ln.lower() or 'delete' in ln.lower() or 'tool_call' in ln:
        print(ln[:200])
