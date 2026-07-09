"""阶段2-5 测试：静态扫描 4 个 agent 的 MCP 工具"""
import os, sys
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2.mcp_discover import discover_mcp_tools_static

for agent in ['health_advisor', 'health_records', 'medication_reminder', 'visit_summary']:
    print(f'=== {agent} ===')
    tools = discover_mcp_tools_static(agent)
    for t in tools:
        args_str = ', '.join(t['args'])
        print(f"  - {t['name']:30s} | args=({args_str})")
        if t['description']:
            print(f"      {t['description'][:80]}")
    print(f'  total: {len(tools)} tools')
    print()
