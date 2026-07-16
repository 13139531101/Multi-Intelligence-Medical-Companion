"""验证 hostapi 调 subagent (MCP) 工具的完整链路"""
import sys
sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('PHA v2 MCP 工具发现 + 加载验证')
print('=' * 70)

from A2AServer.v2.mcp_discover import discover_mcp_tools_static
from A2AServer.v2.mcp_tool_adapter import load_mcp_tools

agents = ['health_advisor', 'health_records', 'medication_reminder', 'visit_summary']

print('\n[1] 静态扫描 (AST) 发现的工具:')
for a in agents:
    specs = discover_mcp_tools_static(a)
    print(f'  {a}: {len(specs)} tools')
    for s in specs[:5]:
        n = s.get("name", "?")
        m = s.get("tool_module", "?")
        print(f'    - {n} (in {m})')

print('\n[2] 实际加载 (load_mcp_tools):')
for a in agents:
    tools = load_mcp_tools(a)
    print(f'  {a}: {len(tools)} BaseTool')
    for t in tools[:5]:
        name = getattr(t, 'name', str(t))
        print(f'    - {name}')

# 3. 实际给 HealthAdvisorV2 注入的工具数
print('\n[3] HealthAdvisorV2._ensure_agent 真创建的 tools 数:')
import asyncio
from A2AServer.v2.sub_agents import HealthAdvisorV2
from A2AServer.v2.v2_agent import V2Agent

async def main():
    V2Agent._agent_instance_cache.clear()
    a = HealthAdvisorV2()
    agent = await a._ensure_agent()
    print(f'  tools count = {len(a._tools)}')
    for t in a._tools:
        name = getattr(t, 'name', str(t))
        print(f'    - {name}')

asyncio.run(main())
