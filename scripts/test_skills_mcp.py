"""阶段41-1+2: Skill 系统 + MCP 加载器测试"""
import json
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))


# ============================================================
# Test 1: Skill 注册
# ============================================================
print("=" * 60)
print("Test 1: Skill 注册 + 列表")
print("=" * 60)

from A2AServer.v2.skills import get_skill_registry, Skill
reg = get_skill_registry()
skills = reg.list_skills()
print(f"  total skills: {len(skills)}")
for s in skills[:3]:
    print(f"    [{s['priority']:3d}] {s['icon']} {s['display_name']} ({s['name']})")
assert len(skills) >= 5
assert any(s["name"] == "health_records" for s in skills)
print("[PASS] Test 1")


# ============================================================
# Test 2: Skill 关键词匹配
# ============================================================
print()
print("=" * 60)
print("Test 2: Skill 关键词匹配")
print("=" * 60)

selected = reg.select_skills("我最近血压有点高，吃什么药好", top_k=2)
print(f"  input: '我最近血压有点高，吃什么药好'")
print(f"  selected: {[s.display_name for s in selected]}")
assert any(s.name == "medication" for s in selected)
print("[PASS] Test 2")


# ============================================================
# Test 3: 动态 system prompt 构造
# ============================================================
print()
print("=" * 60)
print("Test 3: 动态 system prompt 构造")
print("=" * 60)

base = "你是一个健康助手。"
text = "我吃硝苯地平过敏吗？"
prompt, skill_names = reg._skills if False else (None, None)
# 用 build_smart_prompt
from A2AServer.v2.skills import build_smart_prompt
prompt, used_skills = build_smart_prompt(base, text, top_k=2)
print(f"  used_skills: {used_skills}")
print(f"  prompt preview: {prompt[:200]}")
assert "Skill:" in prompt
print("[PASS] Test 3")


# ============================================================
# Test 4: @tool 工具注册 + 调用
# ============================================================
print()
print("=" * 60)
print("Test 4: @tool 工具注册 + 调用")
print("=" * 60)

from A2AServer.v2.skills import get_tool_registry, calculate_bmi
tool_reg = get_tool_registry()
tools = tool_reg.list_tools()
print(f"  total tools: {len(tools)}")
for t in tools[:3]:
    print(f"    - {t['name']} ({t['category']})")
# 调用 BMI 工具
result = tool_reg.call("calculate_bmi", weight_kg=70, height_cm=175)
print(f"  BMI result: {result}")
assert result["success"]
bmi_data = json.loads(result["result"])
assert bmi_data["bmi"] > 22 and bmi_data["bmi"] < 23
print(f"  BMI: {bmi_data['bmi']} ({bmi_data['category']})")
print("[PASS] Test 4")


# ============================================================
# Test 5: 工具调用统计
# ============================================================
print()
print("=" * 60)
print("Test 5: 工具调用统计")
print("=" * 60)

# 调 3 次
for i in range(3):
    tool_reg.call("calculate_bmi", weight_kg=60 + i, height_cm=170)
stats = tool_reg.get_stats()
print(f"  total_calls: {stats['total_calls']}")
print(f"  total_errors: {stats['total_errors']}")
print(f"  error_rate: {stats['error_rate']:.1f}%")
assert stats["total_calls"] >= 3
print("[PASS] Test 5")


# ============================================================
# Test 6: MCP 加载器 - 默认本地 MCP
# ============================================================
print()
print("=" * 60)
print("Test 6: MCP 加载器 - 默认 4 个本地 MCP")
print("=" * 60)

from A2AServer.v2.mcp_loader import get_mcp_loader
loader = get_mcp_loader()
servers = loader.list_servers()
print(f"  total MCPs: {len(servers)}")
for s in servers:
    print(f"    [{s['status']:10s}] {s['icon']} {s['display_name']}")
assert len(servers) == 4
assert all(s["status"] == "connected" for s in servers)
print("[PASS] Test 6")


# ============================================================
# Test 7: MCP 调用 + 追踪
# ============================================================
print()
print("=" * 60)
print("Test 7: MCP 调用 + 追踪（可视化数据）")
print("=" * 60)

result = loader.call("health_records_mcp", "search_health_records",
                     {"user_id": "u1", "limit": 5})
print(f"  call result: success={result['success']}, latency={result['latency_ms']:.1f}ms")
print(f"  call_id: {result['call_id']}")
assert result["success"]

# 查看历史
history = loader.get_call_history(limit=5)
print(f"  history: {len(history)} calls")
for h in history:
    print(f"    {h['call_id']}: {h['mcp_name']}.{h['method']} → {h['duration_str']}")
assert len(history) >= 1
print("[PASS] Test 7")


# ============================================================
# Test 8: 远程 MCP 注册（模拟）
# ============================================================
print()
print("=" * 60)
print("Test 8: 远程 MCP 注册")
print("=" * 60)

server = loader.register_remote(
    name="test_httpbin",
    url="https://httpbin.org",
    display_name="HTTPBin 测试",
    description="远程 MCP 测试"
)
print(f"  registered: {server.name} @ {server.url}")
print(f"  status: {server.status.value}")
servers = loader.list_servers()
assert any(s["name"] == "test_httpbin" for s in servers)
print("[PASS] Test 8")


# ============================================================
# Test 9: 监听者（用于 SSE 可视化）
# ============================================================
print()
print("=" * 60)
print("Test 9: 监听者（前端可视化用）")
print("=" * 60)

events_received = []
def listener(event, data):
    events_received.append((event, data.get("call_id")))

loader.add_listener(listener)
loader.call("health_records_mcp", "test", {})
print(f"  events received: {len(events_received)}")
for e, cid in events_received[-4:]:
    print(f"    [{e}] call_id={cid}")
assert len(events_received) >= 2  # call_start + call_end
assert any(e == "call_start" for e, _ in events_received)
assert any(e == "call_end" for e, _ in events_received)
print("[PASS] Test 9")


# ============================================================
# Test 10: Health check
# ============================================================
print()
print("=" * 60)
print("Test 10: Health check（远程 MCP）")
print("=" * 60)

result = loader.health_check()
print(f"  total: {result['total']}, healthy: {result['healthy']}, failed: {result['failed']}")
print(f"  local MCPs: {sum(1 for s in result['servers'] if s['type']=='local')}")
print(f"  remote MCPs: {sum(1 for s in result['servers'] if s['type']!='local')}")
print("[PASS] Test 10")


print()
print("=" * 60)
print("[ALL PASS] 10/10 tests")
print("=" * 60)