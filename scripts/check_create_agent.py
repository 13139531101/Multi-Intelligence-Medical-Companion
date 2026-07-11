"""真证 create_agent 被调用 + LangChain 1.x 真的工作"""
import sys
import re
import inspect
import asyncio

sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('验证 v2_agent.py 真调 langchain.agents.create_agent')
print('=' * 70)

from A2AServer.v2.v2_agent import V2Agent
src = inspect.getsource(V2Agent._ensure_agent)
calls = re.findall(r'create_agent\(', src)
print(f'\n[1] v2_agent._ensure_agent() 中 create_agent( 调用次数: {len(calls)}')
for m in re.finditer(r'agent\s*=\s*create_agent\(', src):
    line = src[:m.start()].count(chr(10)) + 1
    print(f'    - 在第 {line} 行')


async def main():
    from A2AServer.v2.sub_agents import HealthAdvisorV2
    V2Agent._agent_instance_cache.clear()
    a = HealthAdvisorV2()
    agent = await a._ensure_agent()
    print(f'\n[2] HealthAdvisorV2._ensure_agent() 返回:')
    print(f'    type: {type(agent).__module__}.{type(agent).__name__}')
    print(f'    has stream(): {hasattr(agent, "stream")}')

    n = 0
    final = ''
    async for event in agent.stream('hi', 'check-1', user_id='u1'):
        n += 1
        if event.get('type') == 'normal' and event.get('content'):
            final += event['content']
        if event.get('is_task_complete') or n > 50:
            break
    print(f'\n[3] 调 stream() events: {n}')
    print(f'    final: "{final[:80]}"')


asyncio.run(main())

import langchain
print(f'\n[4] langchain version: {getattr(langchain, "__version__", "?")}')
print(f'    path: {langchain.__file__}')
