"""详细看 LLM 循环模式."""
import httpx
import json
import sys

r = httpx.post("http://localhost:13002/auth/login", json={"username":"1111","password":"111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

q = sys.argv[1] if len(sys.argv) > 1 else "我今天血压 145/95 怎么办"
print(f"\n>>> Q: {q}\n")
i = 0
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  headers=H, json={"message": q}, timeout=60) as r:
    for raw in r.iter_lines():
        if not raw: continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            i += 1
            print(f"  {line.strip()}")
        elif line.startswith("data:"):
            try:
                d = json.loads(line[5:].strip())
                if "text" in d:
                    print(f"  data.text += {d['text']!r}")
                elif "name" in d:
                    print(f"    └ {json.dumps(d, ensure_ascii=False)[:300]}")
                else:
                    print(f"  data: {json.dumps(d, ensure_ascii=False)[:200]}")
            except Exception:
                print(f"  data(raw): {line[:200]}")
print(f"\nTotal events: {i}")
