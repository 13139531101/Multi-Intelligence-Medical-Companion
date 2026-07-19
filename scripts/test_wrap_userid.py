import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
os.environ["PHA_USER_ID"] = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"

import asyncio
from A2AServer.v2.mcp_tool_adapter import _load_http_mcp_tools
tools = _load_http_mcp_tools("medication_reminder")
print(f"Got {len(tools)} tools")

async def run():
    for t in tools:
        if t.name == "get_today_reminders":
            print(f"Tool: {t.name}")
            print(f"Type: {type(t).__name__}")
            try:
                # Empty args
                result = await t.ainvoke({})
                print(f"Result with empty args: {str(result)[:200]}")
            except Exception as e:
                print(f"ainvoke empty failed: {e!r}")

            # Try sync _run directly (which our wrapper monkey-patched)
            try:
                if hasattr(t, '_run'):
                    direct_result = t._run()
                    print(f"Direct _run (sync, with our wrapper): {str(direct_result)[:200]}")
            except Exception as e:
                print(f"direct _run failed: {e!r}")
            break

asyncio.run(run())

