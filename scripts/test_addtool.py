import sys
sys.path.insert(0, '/app/backend')
sys.stdout.reconfigure(encoding='utf-8')

# Import all *_tool.py modules first
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("PHA-Test")

import importlib
for mod_name in ['drug_safety_tool', 'notification_tool', 'ocr_tool', 'reminder_tool']:
    mod = importlib.import_module(f"MedicationReminder.mcpserver.{mod_name}")
    print(f"Loaded {mod_name}, has {len(mod.mcp._tool_manager.list_tools())} tools in its own mcp")
    # Try add get_today_reminders to merge:
    func_name = 'get_today_reminders' if mod_name == 'reminder_tool' else None
    if func_name:
        fn = getattr(mod, func_name)
        try:
            mcp.add_tool(fn, name=func_name, description='test')
            print(f"  add {func_name}: OK")
        except Exception as e:
            print(f"  add {func_name}: FAIL - {e!r}")

print(f"Final mcp tools: {len(mcp._tool_manager.list_tools())}")
