"""阶段31 测试：AgentRegistry 自动发现 + 动态添加 agent"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("阶段31 测试：AgentRegistry 自动发现")
print("=" * 70)

# Test 1: discover_agents 自动发现
print("\n=== Test 1: discover_agents() ===")
from A2AServer.v2.agent_registry import AgentRegistry, discover_agents

specs = discover_agents()
print(f"发现 {len(specs)} 个 agent:")
for s in specs:
    print(f"  - {s.name}: {s.description}")
    print(f"    keywords: {s.keywords[:3]}... ({len(s.keywords)} total)")
    print(f"    aliases: {s.aliases}")
    print(f"    node_name: {s.node_name}")

# Test 2: AgentRegistry.get
print("\n=== Test 2: AgentRegistry.get('health_advisor') ===")
spec = AgentRegistry.get("health_advisor")
print(f"  name: {spec.name}")
print(f"  cls: {spec.cls.__name__}")
print(f"  node_name: {spec.node_name}")
print(f"  class_name: {spec.class_name}")

# Test 3: AgentRegistry.by_alias
print("\n=== Test 3: by_alias('健康顾问') ===")
spec = AgentRegistry.by_alias("健康顾问")
print(f"  找到: {spec.name} -> {spec.cls.__name__}")

# Test 4: 动态添加新 agent
print("\n=== Test 4: 动态添加 nutrition_advisor ===")
from A2AServer.v2.agent_registry import register_agent
from A2AServer.v2.v2_agent import V2Agent

@register_agent(
    name="nutrition_advisor",
    description="营养建议、饮食分析",
    keywords=["营养", "饮食", "食物", "nutrition", "diet", "卡路里"],
    tools_module="nutrition_advisor",
    aliases=["营养师", "饮食顾问"],
)
class NutritionAdvisorV2(V2Agent):
    name = "nutrition_advisor"
    system_prompt = "你是营养顾问，帮助用户分析饮食。"
    
    def get_tools(self):
        return []

print(f"  注册后总数: {AgentRegistry.stats()}")
spec = AgentRegistry.get("nutrition_advisor")
print(f"  新 agent: {spec.name} cls={spec.cls.__name__}")

# Test 5: 动态启用/禁用
print("\n=== Test 5: enable/disable ===")
AgentRegistry.enable("nutrition_advisor", False)
print(f"  disable nutrition_advisor 后: enabled_only={len(AgentRegistry.list())}")
AgentRegistry.enable("nutrition_advisor", True)
print(f"  enable nutrition_advisor 后: enabled_only={len(AgentRegistry.list())}")

# Test 6: 移除 agent
print("\n=== Test 6: remove('nutrition_advisor') ===")
AgentRegistry.remove("nutrition_advisor")
print(f"  remove 后: {AgentRegistry.names()}")
print(f"  stats: {AgentRegistry.stats()}")

# Test 7: build_host_graph 用 registry 自动构建
print("\n=== Test 7: build_host_graph(mode='single') ===")
from A2AServer.v2.host_graph import build_host_graph
g_single = build_host_graph(mode="single")
print(f"  single graph: {g_single}")
# 列出图里的所有节点
if g_single is not None:
    nodes = list(g_single.nodes.keys()) if hasattr(g_single, "nodes") else []
    print(f"  nodes: {nodes}")

# Test 8: multi 模式
print("\n=== Test 8: build_host_graph(mode='multi') ===")
g_multi = build_host_graph(mode="multi")
print(f"  multi graph: {g_multi}")

# Test 9: 动态添加 agent 后再 build
print("\n=== Test 9: 动态添加后 build ===")
@register_agent(name="emergency_advisor", description="急救", keywords=["急救", "emergency"])
class EmergencyV2(V2Agent):
    name = "emergency_advisor"
    system_prompt = "你是急救顾问"
    def get_tools(self): return []

# Force rebuild
from A2AServer.v2 import host_graph as hg
hg._host_graph = None
hg._host_graph_multi = None
hg.AgentRegistry._loaded = False  # type: ignore

g_after = build_host_graph(mode="single")
print(f"  build after add: {g_after}")
if g_after is not None:
    nodes = list(g_after.nodes.keys()) if hasattr(g_after, "nodes") else []
    has_emergency = any("emergency" in n for n in nodes)
    print(f"  contains emergency node: {has_emergency}")
    print(f"  all nodes: {nodes}")

# Test 10: 清理
AgentRegistry.remove("emergency_advisor")
print(f"\n=== Test 10: cleanup ===")
print(f"  最终 agents: {AgentRegistry.names()}")
print(f"  最终 stats: {AgentRegistry.stats()}")

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)