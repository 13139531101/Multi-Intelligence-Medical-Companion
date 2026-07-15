"""测试 v2 smart_chat（小程序即将用的接口）"""
import httpx
import json

# 测试 1: single 模式
print("=" * 60)
print("Test 1: v2 smart_chat (single mode)")
print("=" * 60)
r = httpx.post(
    "http://localhost:13002/smart_chat",
    json={"message": "我头疼", "mode": "single"},
    timeout=120,
)
print(f"HTTP {r.status_code}")
data = r.json()
print(json.dumps(data, ensure_ascii=False, indent=2))

# 测试 2: multi 模式
print("\n" + "=" * 60)
print("Test 2: v2 smart_chat (multi mode)")
print("=" * 60)
r = httpx.post(
    "http://localhost:13002/smart_chat",
    json={"message": "综合分析我的健康", "mode": "multi"},
    timeout=180,
)
print(f"HTTP {r.status_code}")
data = r.json()
print(json.dumps(data, ensure_ascii=False, indent=2))

# 测试 3: with metadata.selected_agent
print("\n" + "=" * 60)
print("Test 3: v2 smart_chat (selected_agent)")
print("=" * 60)
r = httpx.post(
    "http://localhost:13002/smart_chat",
    json={
        "message": "提醒我晚上9点吃药",
        "mode": "single",
        "metadata": {"selected_agent": "medication_reminder"},
    },
    timeout=120,
)
print(f"HTTP {r.status_code}")
data = r.json()
print(json.dumps(data, ensure_ascii=False, indent=2))