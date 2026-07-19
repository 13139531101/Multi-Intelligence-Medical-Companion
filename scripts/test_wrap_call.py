import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
os.environ["PHA_USER_ID"] = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"

from A2AServer.v2.mcp_tool_adapter import _wrap_mcp_tool_with_userid
from langchain_mcp_adapters.tools import load_mcp_tools as lc_load_tools
from langchain_mcp_adapters.sessions import StreamableHttpConnection
import asyncio, json

async def main():
    conn = StreamableHttpConnection(transport="streamable_http", url="http://127.0.0.1:9103/mcp")
    tools = await lc_load_tools(None, connection=conn)
    for t in tools:
        if t.name == "get_today_reminders":
            print(f"BEFORE wrap, required: {t.args_schema['required']}")
            print(f"BEFORE wrap, properties: {t.args_schema['properties']['user_id']}")
            wrapped = _wrap_mcp_tool_with_userid(t)
            print(f"AFTER wrap, required: {wrapped.args_schema['required']}")
            print(f"AFTER wrap, properties user_id: {wrapped.args_schema['properties']['user_id']}")
            # Try ainvoke empty
            try:
                result = await wrapped.ainvoke({})
                print(f"ainvoke empty: {str(result)[:200]}")
            except Exception as e:
                print(f"ainvoke empty fail: {e!r}")
            break

asyncio.run(main())
