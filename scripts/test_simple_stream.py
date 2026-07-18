"""Test simple '你好' stream."""
import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username":"1111","password":"111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
chunks = 0; tools = 0
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  headers=H, json={"message": "你好"}, timeout=30) as r:
    for raw in r.iter_lines():
        if not raw: continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            print("E:", line)
        elif line.startswith("data:"):
            try:
                d = json.loads(line[5:].strip())
                if "text" in d:
                    chunks += 1
                    print(f"   T: {d['text']!r}")
                elif "name" in d and "args" in d:
                    tools += 1
                    print(f"   CALL: {d['name']}({d.get('args')})")
                elif "agent" in d:
                    print(f"   ROUTE: {d.get('agent')}")
                elif "name" in d and "output" in d:
                    print(f"   RESULT: {d['name']} (len={len(str(d.get('output')))})")
                else:
                    print(f"   DATA: {json.dumps(d)[:200]}")
            except Exception as e:
                print("err:", e)
print(f"\nchunks={chunks} tools={tools}")
