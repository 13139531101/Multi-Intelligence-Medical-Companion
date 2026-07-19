"""Test in-process MCP stdio client."""
import asyncio
import os
import sys
sys.path.insert(0, '/app/A2AServer')

# Set env vars for DB connection (some tools need MEMORY_DB_PASSWORD etc.)
os.environ['MEMORY_DB_HOST'] = 'postgres'
os.environ['MEMORY_DB_PORT'] = '5432'
os.environ['MEMORY_DB_USER'] = 'pha'
os.environ['MEMORY_DB_PASSWORD'] = 'zTlQevKV5vzq31QzRqwfcauKX3uQZ64c'
os.environ['MEMORY_DB_NAME'] = 'personal_health_assistant'

sys.stdout.reconfigure(encoding='utf-8')

from mcp import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession

async def main():
    params = StdioServerParameters(
        command="python",
        args=["-m", "MedicationReminder.mcpserver.reminder_tool"],
        env={"PYTHONPATH": "/app/backend", **os.environ}
    )
    print(f"Spawning stdio server: python -m MedicationReminder.mcpserver.reminder_tool")
    async with stdio_client(params) as (read, write):
        print("Connected to stdio!")
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized!")
            tools = await session.list_tools()
            print(f"list_tools returned {len(tools.tools)} tools:")
            for t in tools.tools[:5]:
                print(f"  - {t.name}: {t.description[:60]}...")
            # Call get_today_reminders
            print("\nCalling get_today_reminders via stdio...")
            result = await session.call_tool(
                "get_today_reminders",
                arguments={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"}
            )
            print(f"Result: {result.content[0].text[:200]}...")

asyncio.run(main())
