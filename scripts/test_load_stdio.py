import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
from A2AServer.v2.mcp_tool_adapter import _load_stdio_mcp_tools
tools = _load_stdio_mcp_tools('medication_reminder')
print(f'Got {len(tools)} tools')
for t in tools:
    name = getattr(t, 'name', '?')
    print('  -', name)
