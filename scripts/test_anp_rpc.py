"""测试 ANP RPC 调用"""
import httpx
import json

r = httpx.post(
    "http://localhost:13002/anp/agent/rpc",
    json={
        "jsonrpc": "2.0",
        "method": "route_query",
        "params": {"user_id": "test_user", "query": "我头疼"},
        "id": 3
    },
    timeout=120,
)
print(f"HTTP {r.status_code}")
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:1000])