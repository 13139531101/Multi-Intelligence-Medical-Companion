"""Direct test: stdio + load_mcp_tools (langchain_mcp_adapters)."""
import asyncio, os, sys

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    from mcp import StdioServerParameters, stdio_client
    from mcp.client.session import ClientSession
    from langchain_mcp_adapters.tools import load_mcp_tools as lc_load_tools

    params = StdioServerParameters(
        command="python",
        args=["-m", "MedicationReminder.mcpserver._stdio_starter"],
        env={"PYTHONPATH": "/app/backend"},
    )
    print("Spawning...")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Direct list_tools:
            resp = await session.list_tools()
            print(f"session.list_tools() returned {len(resp.tools)} tools:")
            for t in resp.tools:
                print(f"  - {t.name}")
            # Then via lc adapter:
            tools = await lc_load_tools(session=session)
            print(f"\nlc_load_tools returned {len(tools)} tools:")
            for t in tools:
                print(f"  - {type(t).__name__}: {t.name}")

asyncio.run(main())
