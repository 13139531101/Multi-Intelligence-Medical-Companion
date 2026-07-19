"""Direct dump stream: 添加用药"""
import httpx, json, sys, time
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def safe(s):
    try: return json.loads(s[5:].strip())
    except: return None

print("=== 添加肌酸激酶提醒 (might trigger LLM thinking + interrupt) ===")
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "添加用药提醒: 钙片 500mg, 每天早上 7 点"},
                  headers=h, timeout=120) as resp:
    intr = None
    for line in resp.iter_lines():
        if line.startswith("data:"):
            p = safe(line)
            if p:
                if p.get("text"):
                    pass  # text chunks (skip)
                elif p.get("thread_id"):
                    intr = p
                    print(f"thread_id: {p['thread_id'][:60]}")
                    print(f"action: {p['interrupt_data'].get('action_requests', [{}])[0].get('name')}")
                elif "tool_call" in line.lower():
                    print(f"tool_call: {p.get('name')}")
                elif "done" in line.lower():
                    print(f"done")

    if intr:
        print("\n=== Now resume with approve ===")
        with httpx.stream("POST", "http://localhost:13002/v2/chat/resume",
                          json={"thread_id": intr["thread_id"],
                                "decisions": [{"type": "approve"}],
                                "conversation_id": f"r_{int(time.time())}",
                                "target_agent": "medication_reminder"},
                          headers=h, timeout=60) as r2:
            chunks = 0
            for ln in r2.iter_lines():
                chunks += 1
                if "done" in ln.lower() or chunks > 50:
                    break
            print(f"Resume returned {chunks} chunks")
