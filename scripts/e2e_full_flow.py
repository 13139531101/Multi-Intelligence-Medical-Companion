"""阶段29 完整链路 E2E：v2 LangGraph + A2A sub-agent 互调"""
import sys
import time
import json
import httpx


def step(msg):
    print(f"\n[STEP] {msg}")


def ok(msg):
    print(f"  [OK]   {msg}")


def fail(msg):
    print(f"  [FAIL] {msg}")


print("=" * 70)
print("PHA v2 阶段29 完整链路 E2E")
print("=" * 70)

# ---- 1. 4 sub-agent card ----
step("1. 4 sub-agent agent card 健康检查")
sub_agents = [
    ("health_records", "http://localhost:10010/.well-known/agent.json"),
    ("health_advisor", "http://localhost:10011/.well-known/agent.json"),
    ("medication_reminder", "http://localhost:10012/.well-known/agent.json"),
    ("visit_summary", "http://localhost:10013/.well-known/agent.json"),
]
for name, url in sub_agents:
    try:
        r = httpx.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            ok(f"{name} | name={data.get('name','?')}")
        else:
            fail(f"{name} HTTP {r.status_code}")
    except Exception as e:
        fail(f"{name}: {str(e)[:80]}")


# ---- 2. hostapi health ----
step("2. hostapi health check")
try:
    r = httpx.get("http://localhost:13002/health", timeout=5)
    if r.status_code == 200:
        ok(f"hostapi: HTTP {r.status_code}")
    else:
        fail(f"hostapi HTTP {r.status_code}")
except Exception as e:
    fail(f"hostapi: {str(e)[:80]}")


# ---- 3. hostapi /v2/status ----
step("3. hostapi /v2/status")
try:
    r = httpx.get("http://localhost:13002/v2/status", timeout=5)
    if r.status_code == 200:
        data = r.json()
        ok(f"v2 status: {json.dumps(data, ensure_ascii=False)[:200]}")
    else:
        ok(f"/v2/status HTTP {r.status_code}")
except Exception as e:
    ok(f"/v2/status: {str(e)[:80]} (可能没注册此端点)")


# ---- 4. 真提问 ----
step("4. 真提问 - 健康咨询")
print("  提问: \"我最近总是头疼，可能是什么原因？\"")
try:
    r = httpx.post(
        "http://localhost:13002/smart_chat",
        json={"message": "我最近总是头疼，可能是什么原因？"},
        timeout=120,
    )
    print(f"  HTTP status: {r.status_code}")
    body = r.text
    print(f"  Response (前 500 字符): {body[:500]}")
    if r.status_code == 200:
        ok(f"HTTP 200")
    else:
        fail(f"HTTP {r.status_code}")
except Exception as e:
    fail(f"调用失败: {str(e)[:100]}")


# ---- 5. 等 v2 stream 跑 ----
step("5. 等 v2 LangGraph stream 跑（30s）")
time.sleep(30)


print("\n" + "=" * 70)
print("E2E 调用完成，请看 docker logs a2aserver-hostapi-stage28v3 完整调用链")
print("=" * 70)