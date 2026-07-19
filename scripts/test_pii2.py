"""Light PII test: just one number at a time"""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def safe_parse(s):
    try: return json.loads(s[5:].strip())
    except: return None

# Test 1: 仅 含手机号
print("=== Test 1: 手机号 ===")
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "今天身体好点了, 13800138000 这个手机号帮我存起来, 我下次用"},
                  headers=h, timeout=30) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            p = safe_parse(line)
            if p and (p.get("text") or p.get("tool_call") or p.get("tool_result")):
                print("  event:", str(p)[:300])

print()
print("=== Test 2: 仅 信用卡 ===")
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "我的信用卡号是 4111111111111111, 帮我存起来"},
                  headers=h, timeout=30) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            p = safe_parse(line)
            if p and (p.get("text") or p.get("tool_call") or p.get("tool_result")):
                print("  event:", str(p)[:300])

print()
print("=== Test 3: 仅 URL ===")
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  json={"message": "想了解病情, 我看 https://baike.baidu.com/item/disease 这个网站还挺好的"},
                  headers=h, timeout=30) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            p = safe_parse(line)
            if p and (p.get("text") or p.get("tool_call") or p.get("tool_result")):
                print("  event:", str(p)[:300])
