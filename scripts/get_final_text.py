"""Get just the final answer."""
import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username":"1111","password":"111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
final = ""
with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  headers=H, json={"message": "我血压 145/95"}, timeout=30) as r:
    for raw in r.iter_lines():
        if not raw: continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if line.startswith("data:"):
            try:
                d = json.loads(line[5:].strip())
                if "text" in d:
                    final += d["text"]
            except: pass
print("FINAL ANSWER:")
print(final)
