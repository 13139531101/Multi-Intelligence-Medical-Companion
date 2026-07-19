"""Test HumanInTheLoop: 触发 '吃药' log → interrupt."""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "我刚吃了硝苯地平, 帮我记录一下"},
                  headers=h, timeout=120) as resp:
    print(f"Status: {resp.status_code}")
    chunks = []
    for line in resp.iter_lines():
        if line:
            print("chunk:", line[:200])
            chunks.append(line)

text = "\n".join(chunks)
if "interrupt" in text.lower() or "confirm" in text.lower() or "确认" in text:
    print("\n[TEST] HumanInTheLoop interrupt detected")
elif "已记录" in text or "marked" in text.lower():
    print("\n[TEST] No interrupt (tool 立即执行)")
else:
    print("\n[TEST] Unknown response")
