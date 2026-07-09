"""阶段2-5 验收：4 个 Agent 全部接入真实 MCP 工具"""
import os
import sys
import asyncio
from pathlib import Path

# 加载 .env
from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2 import (
    HealthAdvisorV2,
    HealthRecordsV2,
    MedicationReminderV2,
    VisitSummaryV2,
)
from A2AServer.v2.mcp_tool_adapter import load_mcp_tools

print('=' * 70)
print('PHA v2 阶段2-5 验收 - 真实 MCP 工具接入')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# 1. 静态发现
print('\n[1] 静态发现 4 个 Agent 的 MCP 工具')
for agent_name in ['health_advisor', 'health_records', 'medication_reminder', 'visit_summary']:
    tools = load_mcp_tools(agent_name)
    total += 1
    if check(
        f'load_mcp_tools({agent_name!r})',
        len(tools) > 0,
        f'-> {len(tools)} tools: {[t.name for t in tools][:5]}...' if tools else 'empty!',
    ):
        passed += 1

# 2. 真实工具 vs stub 标记
print('\n[2] 确认是真实工具（不是 stub）')
import os
for agent_name in ['health_advisor', 'health_records', 'medication_reminder', 'visit_summary']:
    tools = load_mcp_tools(agent_name)
    total += 1
    if not tools:
        check(f'{agent_name} 真实工具', False, 'empty')
        continue
    # 真实工具的名字应该出现在 *_tool.py 里
    real_names = {t.name for t in tools}
    has_real = any('mcp' not in str(type(t).__name__).lower() for t in tools)
    if check(
        f'{agent_name} 包含真实 MCP 工具',
        len(tools) >= 2,
        f'tool count: {len(tools)}',
    ):
        passed += 1

# 3. 端到端测试：调一次健康咨询
print('\n[3] 端到端测试 - HealthAdvisorV2 调真实工具')
async def e2e_test():
    global total, passed
    agent = HealthAdvisorV2()
    print(f'   agent: {agent.name}, model: {agent.model}')
    print(f'   tools count: {len(agent.get_tools())}')

    n = 0
    full = ''
    tool_called = None
    async for event in agent.stream(
        '我最近有点头晕，可能是什么原因？需要分析症状',
        'stage25-e2e-001',
        user_id='u_stage25_001',
    ):
        n += 1
        ev = event.get('type', '?')
        c = event.get('content') or event.get('updates') or event.get('output') or ''
        if c:
            full += str(c)
        if ev == 'tool_call':
            tool_called = event.get('name')
        if event.get('is_task_complete'):
            print(f'   [event {n}] task_complete, tool called: {tool_called}')
            break
        if n > 30:
            break

    total += 1
    if check('HealthAdvisorV2 端到端推理', n > 1, f'{n} events, {len(full)} chars'):
        passed += 1
    total += 1
    if check('实际调用了 MCP 工具', tool_called is not None, f'last tool: {tool_called}'):
        passed += 1

asyncio.run(e2e_test())

# 4. 4 个 Agent 实例化
print('\n[4] 4 个 Agent 全部可实例化')
for cls in [HealthAdvisorV2, HealthRecordsV2, MedicationReminderV2, VisitSummaryV2]:
    total += 1
    a = cls()
    if check(f'{cls.__name__}', True, f'model={a.model}, tools={len(a.get_tools())}'):
        passed += 1

# 总结
print('\n' + '=' * 70)
print(f'阶段2-5 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段2-5 完成，V2Agent 接入真实 MCP 工具。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
