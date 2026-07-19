import sys
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ["MEMORY_DB_PASSWORD"] = "zTlQevKV5vzq31QzRqwfcauKX3uQZ64c"
os.environ["PHA_USER_ID"] = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"
import asyncio
from A2AServer.v2.mcp_tool_adapter import _load_http_mcp_tools
tools = _load_http_mcp_tools("medication_reminder")
for t in tools:
    if t.name == "get_today_reminders":
        schema = t.args_schema
        print(f"args_schema: {schema}")
        print(f"fields: {list(schema.model_fields.keys())}")
        if "user_id" in schema.model_fields:
            f = schema.model_fields["user_id"]
            print(f"user_id field: is_required={f.is_required()}, default={f.default}")
        print(f"t.args = {t.args}")
