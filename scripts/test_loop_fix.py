"""测循环修复 — 期望: tool_call 各只 1 次, chunk 不重复."""
import httpx, json, sys
r = httpx.post("http://localhost:13002/auth/login", json={"username":"1111","password":"111111"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

q = sys.argv[1] if len(sys.argv) > 1 else "我今天血压 145/95 怎么办"
print(f"\n>>> Q: {q}\n")

tool_calls = []     # [(name, args)]
tool_results = []   # [(name)]
chunks = []
routing = None

with httpx.stream("POST", "http://localhost:13002/v2/chat/stream",
                  headers=H, json={"message": q}, timeout=60) as r:
    for raw in r.iter_lines():
        if not raw: continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            print(f"  {line}")
        elif line.startswith("data:"):
            try:
                d = json.loads(line[5:].strip())
                if "text" in d:
                    chunks.append(d["text"])
                    print(f"    CHUNK: {d['text'][:60]!r}")
                elif "name" in d and "args" in d:
                    tool_calls.append((d["name"], json.dumps(d.get("args", {}), sort_keys=True, ensure_ascii=False)))
                    print(f"    TOOL_CALL: {d['name']}({d.get('args')})")
                elif "name" in d and "output" in d:
                    tool_results.append((d["name"]))
                    print(f"    TOOL_RESULT: {d['name']} (return len={len(json.dumps(d.get('output')))}")
                elif "agent" in d:
                    routing = d.get("agent")
                    print(f"    ROUTING: {d}")
            except Exception:
                pass

print(f"\n===== summary =====")
print(f"routing: {routing}")
print(f"tool_calls unique: {len(set(tool_calls))} / total: {len(tool_calls)}")
print(f"tool_results: {len(tool_results)}")
print(f"chunks total: {len(chunks)}, unique text: {len(set(chunks))}")
print(f"final text len: {sum(len(c) for c in chunks)}")
