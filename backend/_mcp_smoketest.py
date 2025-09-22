import asyncio
import logging
import os
import sys

# Prefer local A2AServer/src over site-packages for testing
_current_dir = os.path.dirname(__file__)
_src_path = os.path.abspath(os.path.join(_current_dir, "A2AServer", "src"))
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from A2AServer.agent import BasicAgent

logging.basicConfig(level=logging.DEBUG)

async def main():
    agent = BasicAgent(
        config_path=r"HealthAdvisor/mcp_config.json",
        model_name="deepseek-chat",
        prompt_file=r"HealthAdvisor/memory_enhanced_agent_prompt.md",
        provider="deepseek",
        quiet_mode=False,
    )
    ok = await agent.setup_tools()
    print("setup_tools:", ok)
    await agent.cleanup()

if __name__ == "__main__":
    asyncio.run(main())