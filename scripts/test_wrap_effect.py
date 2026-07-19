import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
os.environ["PHA_USER_ID"] = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"
import asyncio, json
from A2AServer.v2.mcp_tool_adapter import _load_http_mcp_tools

async def main():
    tools = _load_http_mcp_tools("medication_reminder")
    for t in tools:
        if t.name == "get_today_reminders":
            print(f"args_schema type: {type(t.args_schema)}")
            print(f"args_schema: {json.dumps(t.args_schema, default=str)[:600]}")
            try:
                result = await t.ainvoke({})
                print(f"ainvoke empty: {str(result)[:300]}")
            except Exception as e:
                print(f"ainvoke empty fail: {e!r}")
            try:
                result = await t.ainvoke({"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"})
                print(f"ainvoke with uid: {str(result)[:300]}")
            except Exception as e:
                print(f"ainvoke with uid fail: {e!r}")
            break

asyncio.run(main())
