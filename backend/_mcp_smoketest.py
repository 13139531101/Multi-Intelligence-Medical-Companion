import asyncio
import logging
import os
import sys

# Prefer local A2AServer/src over site-packages for testing
_current_dir = os.path.dirname(__file__)
_src_path = os.path.abspath(os.path.join(_current_dir, "A2AServer", "src"))
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# On Windows, ensure Proactor loop (supports subprocess); avoid Selector which breaks subprocess
if sys.platform.startswith("win"):
    try:
        if not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from A2AServer.agent import BasicAgent

logging.basicConfig(level=logging.DEBUG)

async def main():
    agent = BasicAgent(
        config_path=r"HealthRecordsManager/mcp_config.json",
        model_name="deepseek-chat",
        prompt_file=r"HealthRecordsManager/prompt.txt",
        provider="deepseek",
        quiet_mode=False,
    )
    ok = await agent.setup_tools()
    print("setup_tools:", ok)
    await agent.cleanup()
    # Allow a brief moment for transports to finalize on Windows proactor loop
    if sys.platform.startswith("win"):
        try:
            await asyncio.shield(asyncio.sleep(0.1))
        except BaseException:
            pass

if __name__ == "__main__":
    asyncio.run(main())