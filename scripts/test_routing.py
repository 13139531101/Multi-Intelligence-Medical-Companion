"""测 routing: 看不同问题路由到哪个 agent."""
import httpx
import json

def ask(q):
    r = httpx.post("http://localhost:13002/auth/login",
                   json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}
    with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                      headers=H, json={"message": q}, timeout=30) as r:
        buffer = ""
        agent = "?"
        for raw in r.iter_lines():
            if not raw: continue
            line = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw
            buffer += line + "\n"
            if line.startswith('event: routing'):
                # 下一行是 data: {...}
                continue
            if line.startswith('data: '):
                try:
                    d = json.loads(line[6:])
                    if "agent" in d:
                        agent = d.get("agent", "?")
                        break
                except: pass
    return agent

questions = [
    "我今天血压 145/95 算高血压吗",
    "什么是高血压? 有什么症状",
    "我最近失眠怎么办",
    "我吃硝苯地平后头痛正常吗",
    "帮我上传体检报告",
    "帮我查询最近的就诊记录",
    "今天吃什么药",
    "漏服了一次降压药",
]

for q in questions:
    a = ask(q)
    print(f"[{a:30s}] Q: {q}")
