import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
os.environ["PHA_USER_ID"] = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"
import asyncio
from langchain_mcp_adapters.tools import load_mcp_tools as lc_load_tools
from langchain_mcp_adapters.sessions import StreamableHttpConnection

async def main():
    conn = StreamableHttpConnection(transport="streamable_http", url="http://127.0.0.1:9103/mcp")
    tools = await lc_load_tools(None, connection=conn)
    for t in tools:
        if t.name == "get_today_reminders":
            schema = t.args_schema
            print(f"schema class: {type(schema).__name__}")
            print(f"fields: {list(schema.model_fields.keys())}")
            if "user_id" in schema.model_fields:
                f = schema.model_fields["user_id"]
                print(f"user_id field: is_required={f.is_required()}, default={f.default}")
            # Try ainvoke
            try:
                result = await t.ainvoke({})
                print(f"\nainvoke empty: {str(result)[:200]}")
            except Exception as e:
                print(f"\nainvoke empty fail: {e!r}")
            try:
                result = await t.ainvoke({"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"})
                print(f"\nainvoke with user_id: {str(result)[:200]}")
            except Exception as e:
                print(f"\nainvoke with user_id fail: {e!r}")
            break
asyncio.run(main())
