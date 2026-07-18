"""Inspect /v2/chat/stream raw events."""
import httpx
import json
import sys

r = httpx.post("http://localhost:13002/auth/login", json={"username":"1111","password":"111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

q = sys.argv[1] if len(sys.argv) > 1 else "我今天血压 145/95 怎么办"
print(f"\n>>> Q: {q}\n")
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  headers=H, json={"message": q}, timeout=40) as r:
    for raw in r.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            print(f"  {line}")
        elif line.startswith("data:"):
            try:
                d = json.loads(line[5:].strip())
                if "text" in d:
                    txt = d["text"]
                    print(f"  data.text += {txt!r}")
                elif "tool_calls" in d or "tools" in d:
                    print(f"  data.tools = {json.dumps(d, ensure_ascii=False)[:300]}")
                elif "agent" in d and "routing" in d:
                    print(f"  ROUTING: {d}")
                elif "agent" in d:
                    print(f"  ROUTING: {d}")
                elif "tool" in d.lower() or "function" in d.lower():
                    print(f"  TOOL CALL: {json.dumps(d, ensure_ascii=False)[:300]}")
                else:
                    print(f"  data: {json.dumps(d, ensure_ascii=False)[:300]}")
            except Exception:
                print(f"  data(raw): {line}")
        elif line:
            print(f"  ?? {line[:120]}")
