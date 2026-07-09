"""阶段3 验收脚本 - HostGraph 端到端测试"""
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
    build_host_graph,
    get_host_graph,
    route_and_invoke,
    HostState,
)

print('=' * 70)
print('PHA v2 阶段3 验收 - HostGraph 编排')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 模块导入 ----
print('\n[1] HostGraph 模块导入')
total += 1
if check('build_host_graph 可调用', callable(build_host_graph)):
    passed += 1
total += 1
if check('route_and_invoke 可调用', callable(route_and_invoke)):
    passed += 1
total += 1
if check('HostState 可实例化', HostState(query='test', conversation_id='c1', user_id='u1') is not None):
    passed += 1

# ---- 2. 路由函数单元测试 ----
print('\n[2] 路由函数（3 层）')
from A2AServer.v2.host_graph import _layer1_metadata, _layer2_heuristic, AGENT_ALIAS

# Layer 1: metadata
total += 1
s = {'metadata': {'selected_agent': '健康顾问'}, 'query': 'test', 'events': []}
if check('Layer 1: metadata 命中', _layer1_metadata(s) == 'health_advisor'):
    passed += 1

# Layer 1: 英文
total += 1
s = {'metadata': {'selected_agent': 'health_records'}, 'query': 'test', 'events': []}
if check('Layer 1: 英文 metadata 命中', _layer1_metadata(s) == 'health_records'):
    passed += 1

# Layer 1: 未知
total += 1
s = {'metadata': {'selected_agent': 'unknown_agent'}, 'query': 'test', 'events': []}
if check('Layer 1: 未知 agent 返回空', _layer1_metadata(s) == ''):
    passed += 1

# Layer 2: 关键词
total += 1
s = {'query': '我最近有点头疼', 'metadata': {}, 'events': []}
if check('Layer 2: 头疼 -> health_advisor', _layer2_heuristic(s) == 'health_advisor'):
    passed += 1

total += 1
s = {'query': '请帮我看看体检报告', 'metadata': {}, 'events': []}
if check('Layer 2: 体检报告 -> health_records', _layer2_heuristic(s) == 'health_records'):
    passed += 1

total += 1
s = {'query': '我今天忘记吃药了', 'metadata': {}, 'events': []}
if check('Layer 2: 吃药 -> medication_reminder', _layer2_heuristic(s) == 'medication_reminder'):
    passed += 1

total += 1
s = {'query': '帮我总结就诊记录', 'metadata': {}, 'events': []}
if check('Layer 2: 就诊 -> visit_summary', _layer2_heuristic(s) == 'visit_summary'):
    passed += 1

# ---- 3. 构建 StateGraph ----
print('\n[3] 构建 StateGraph')
graph = build_host_graph()
total += 1
if check('build_host_graph() 返回 CompiledGraph', graph is not None):
    passed += 1
if graph is not None:
    total += 1
    if check('get_host_graph() 不为 None', get_host_graph() is not None):
        passed += 1
    total += 1
    if check('get_host_graph() 单例', get_host_graph() is get_host_graph()):
        passed += 1

# ---- 4. 端到端测试 ----
print('\n[4] 端到端测试 - 3 种路由场景')

async def e2e_tests():
    global total, passed

    # 场景 A: 关键词 -> health_advisor
    print('   场景 A: 关键词触发健康顾问')
    result_a = await route_and_invoke(
        query='我最近头疼得厉害，可能是什么原因？',
        conversation_id='stage3-e2e-A',
        user_id='u_stage3',
    )
    total += 1
    if check('场景 A 返回正常', not result_a.get('error'), f'agent={result_a.get("agent")}'):
        passed += 1
    total += 1
    if check('场景 A 路由到 health_advisor', result_a.get('agent') == 'health_advisor'):
        passed += 1
    total += 1
    if check('场景 A 命中 layer 2 启发', result_a.get('routing', {}).get('layer') == 2):
        passed += 1
    print(f'   response[{len(result_a.get("content", ""))} chars]: {result_a.get("content", "")[:120]}...')

    # 场景 B: metadata 显式指定 -> health_records
    print('\n   场景 B: metadata 显式指定 health_records')
    result_b = await route_and_invoke(
        query='查询我的档案',
        conversation_id='stage3-e2e-B',
        user_id='u_stage3',
        metadata={'selected_agent': 'health_records'},
    )
    total += 1
    if check('场景 B 返回正常', not result_b.get('error')):
        passed += 1
    total += 1
    if check('场景 B 路由到 health_records', result_b.get('agent') == 'health_records'):
        passed += 1
    total += 1
    if check('场景 B 命中 layer 1 metadata', result_b.get('routing', {}).get('layer') == 1):
        passed += 1

    # 场景 C: 关键词触发 medication_reminder
    print('\n   场景 C: 关键词触发 medication_reminder')
    result_c = await route_and_invoke(
        query='请设置用药提醒',
        conversation_id='stage3-e2e-C',
        user_id='u_stage3',
    )
    total += 1
    if check('场景 C 返回正常', not result_c.get('error')):
        passed += 1
    total += 1
    if check('场景 C 路由到 medication_reminder', result_c.get('agent') == 'medication_reminder'):
        passed += 1

asyncio.run(e2e_tests())

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段3 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段3 完成，HostGraph 端到端跑通。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
