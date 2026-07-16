"""检查 v2 是否有 subagent 状态端点"""
import httpx

print("=" * 70)
print("PHA v2 subagent 状态端点检查")
print("=" * 70)

endpoints = [
    "/health",
    "/health/deep",
    "/v2/status",
    "/v2/metrics/json",
    "/v2/summary",
    "/v2/audit/stats",
    "/v2/agents",          # 看有没有 agent 列表端点
    "/v2/agents/status",   # 看有没有 agent 状态端点
    "/v2/subagents",
]

for ep in endpoints:
    try:
        r = httpx.get(f"http://localhost:13002{ep}", timeout=5)
        print(f"\n{ep}: HTTP {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
                if ep == "/v2/status":
                    print(f"  顶层字段: {list(data.keys())}")
                    print(f"  agent_singleton_classes: {data.get('agent_singleton_classes', 'N/A')}")
                    metrics = data.get('metrics', {})
                    if isinstance(metrics, dict):
                        print(f"  metrics keys: {list(metrics.keys())[:8]}")
                else:
                    print(f"  body[:300]: {r.text[:300]}")
            except Exception:
                print(f"  body[:300]: {r.text[:300]}")
    except Exception as e:
        print(f"\n{ep}: FAIL - {str(e)[:80]}")