import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
os.environ["PHA_USER_ID"] = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"
import asyncio, json
from langchain_mcp_adapters.tools import load_mcp_tools as lc_load_tools
from langchain_mcp_adapters.sessions import StreamableHttpConnection

async def main():
    conn = StreamableHttpConnection(transport="streamable_http", url="http://127.0.0.1:9103/mcp")
    tools = await lc_load_tools(None, connection=conn)
    for t in tools:
        if t.name == "get_today_reminders":
            print(f"args_schema type: {type(t.args_schema)}")
            print(f"args_schema value: {json.dumps(t.args_schema, indent=2, default=str)[:600]}")
            print(f"\nargs type: {type(t.args)}")
            print(f"args value: {str(t.args)[:500]}")
            print(f"\ntool fields/methods: {[m for m in dir(t) if not m.startswith('_')][:15]}")
            # Try the syntax in the run path
            try:
                # Find tool_call config method
                result = await t.ainvoke({"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"})
                print(f"\nainvoke with user_id: {str(result)[:200]}")
            except Exception as e:
                print(f"\nainvoke fail: {e!r}")
            break
asyncio.run(main())
