"""Direct test PII detection — see middleware applied in stream."""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def safe(s):
    try: return json.loads(s[5:].strip())
    except: return None

# Test: 一般性问题 (无敏感数据), 看 stream 工作
print("=== Test (简单, 测 stream) ===")
text = ""
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "你好"},
                  headers=h, timeout=120) as resp:
    count = 0
    for line in resp.iter_lines():
        count += 1
        if line.startswith("data:"):
            p = safe(line)
            if p:
                if p.get("text"):
                    text += p["text"]
                elif p.get("agent"):
                    print(f"agent={p['agent']}")
                elif "tool_call" in line.lower():
                    print(f"tool_call: {p.get('name')}")
                elif "done" in line.lower():
                    print(f"done!")
                    break
                elif "interrupt" in line.lower():
                    print(f"INTERRUPT!")
                    break
    print(f"total lines: {count}")
print(f"final text: {text[:200]}")
