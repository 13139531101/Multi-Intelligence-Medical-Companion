"""Full HITL flow: interrupt → user reviews → approve → tool executes."""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Step 1: 触发 interrupt
print("=== Step 1: 触发 interrupt ===")
thread_id = None
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "帮我添加一个药物提醒: 鱼油软胶囊 1000mg, 每天晚上 9 点服用"},
                  headers=h, timeout=90) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:") and "thread_id" in line:
            try:
                p = json.loads(line[5:].strip())
                if "thread_id" in p:
                    thread_id = p["thread_id"]
                    print(f"Got thread_id: {thread_id}")
                    if p.get("interrupt_data", {}).get("action_requests"):
                        ar = p["interrupt_data"]["action_requests"][0]
                        print(f"Action: {ar['name']}")
                        print(f"Args: {json.dumps(ar.get('args', {}), ensure_ascii=False)[:200]}")
                    break
            except Exception:
                pass

if not thread_id:
    print("FAIL: No thread_id from interrupt")
    sys.exit(1)

# Step 2: 用户点 "确认"
print("\n=== Step 2: 用户 click \"✅ 确认执行\" ===")
with httpx.stream("POST", "http://localhost:13002/v2/chat/resume",
                  json={
                      "thread_id": thread_id,
                      "decisions": [{"type": "approve"}],
                      "conversation_id": f"resume_{thread_id}",
                      "target_agent": "medication_reminder",
                  },
                  headers=h, timeout=60) as resp:
    print(f"Status: {resp.status_code}")
    chunks_done = 0
    for line in resp.iter_lines():
        if line:
            chunks_done += 1
            if "chunk" in line.lower() or "tool" in line.lower() or "done" in line.lower() or "error" in line.lower():
                print(f"  {line[:200]}")
    print(f"\n总 chunks: {chunks_done}")
