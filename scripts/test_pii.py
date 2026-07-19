"""Test PII: 输入含手机号 → 验证被 mask"""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def safe_parse(s):
    try:
        return json.loads(s[5:].strip())
    except Exception:
        return None

def stream_chat(msg):
    text = ""
    with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                      json={"message": msg}, headers=h, timeout=45) as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                p = safe_parse(line)
                if p and p.get("text"):
                    text += p["text"]
    return text

# Test 1: 中国手机号
print("=== Test 1: 输入含中国手机号 + 国际号 + 邮箱 + IP ===")
out = stream_chat("我最近身体不太好, 15012345678 和 13800138000 这两个电话帮我记下, 邮箱 zhang.san@163.com 有用, IP 地址 192.168.1.1 异常登录")
print(out[:600])
print()

# Test 2: 信用卡
print("=== Test 2: 输入含信用卡号 ===")
out = stream_chat("我的信用卡号 4111 1111 1111 1111 帮我保存到档案")
print(out[:400])
print()

# Test 3: URL
print("=== Test 3: URL ===")
out = stream_chat("去这个网站看看血压的治疗: https://example.com/article.html")
print(out[:400])
