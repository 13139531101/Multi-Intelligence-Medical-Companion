"""Direct test PII: 1 question with real sensitive data, 120s timeout."""
import httpx, json, sys
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def safe(s):
    try: return json.loads(s[5:].strip())
    except: return None

def stream_text(msg):
    text = ""
    with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                      json={"message": msg}, headers=h, timeout=120) as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                p = safe(line)
                if p and p.get("text"):
                    text += p["text"]
    return text

# 测试 1: 手机号
print("=== 手机号 mask 测试 ===")
out = stream_text("我记一下手机号 13800138000 是我的备用号码")
print(f"REPLY: [{out[:500]}]")
# 我们关心的是: PII middleware 是否真的 mask 这 11 位
# 通过 send_request 的日志看不到, 但被 mask 后 LLM 看到 [PHONE_MASKED]
# 我们的输出 (LLM response) 不会有 mask 内容 (因为 mask 是 redact 输入, 输出包含)
# 实际上我们要看 LLM response 是否包括明文 13800138000 (因为输出不被 redact)

# 这里检验: PII middleware 默认 apply to user input + agent output both
# We need a fake question asking the LLM to repeat the number
# LLM 应该 memorize then output should also be masked

print("\n=== 邮箱 redact 测试 ===")
out = stream_text("把邮箱 zhang.san@example.com 保存一下")
print(f"REPLY: [{out[:300]}]")

print("\n=== URL redact 测试 ===")
out = stream_text("我对 https://baike.baidu.com/item/disease 这个网页的内容很感兴趣")
print(f"REPLY: [{out[:300]}]")
