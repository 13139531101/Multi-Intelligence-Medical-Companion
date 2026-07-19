import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
import asyncio, json
from A2AServer.v2.mcp_tool_adapter import _load_http_mcp_tools

tools = _load_http_mcp_tools("medication_reminder")
for t in tools:
    if t.name == "get_today_reminders":
        # Check all related attrs
        print(f"tool_call_schema type: {type(t.tool_call_schema)}")
        print(f"tool_call_schema: {json.dumps(t.tool_call_schema, default=str)[:600]}")
        print(f"get_input_schema: {type(t.get_input_schema)}")
        try:
            print(f"input_schema(): {t.get_input_schema()}")
        except Exception as e:
            print(f"err: {e!r}")
        # Tool fields all
        print(f"\nfields: {[f for f in dir(t) if 'tool' in f.lower() or 'input' in f.lower() or 'args' in f.lower()]}")
        break
