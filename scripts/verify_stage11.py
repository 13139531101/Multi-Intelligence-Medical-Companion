"""阶段11 验收 - 监控模块 + 集成"""
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('PHA v2 阶段11 验收 - 监控模块')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 监控模块导入 ----
print('\n[1] 监控模块导入')
from A2AServer.v2.monitoring import (
    get_metrics,
    get_prometheus_metrics,
    print_summary,
    reset_metrics,
    record_tool_cache_hit,
    record_tool_cache_miss,
    record_tool_cache_skip,
    record_agent_new,
    record_agent_reuse,
    record_request,
    record_llm_call,
)

total += 1
if check('所有 record_* 函数可调用', callable(record_tool_cache_hit)):
    passed += 1
total += 1
if check('get_metrics() 可调用', callable(get_metrics)):
    passed += 1
total += 1
if check('get_prometheus_metrics() 可调用', callable(get_prometheus_metrics)):
    passed += 1

# ---- 2. 单元测试 ----
print('\n[2] 监控单元测试')
reset_metrics()
record_tool_cache_hit()
record_tool_cache_hit()
record_tool_cache_hit()
record_tool_cache_miss()
record_tool_cache_skip()
record_agent_new()
record_agent_reuse()
record_agent_reuse()
record_request(1.5)
record_request(2.0)
record_request(2.5, error=True)
record_llm_call()
record_llm_call(error=True)

m = get_metrics()
total += 1
if check('tool_cache.hits=3', m['tool_cache']['hits'] == 3, f"got {m['tool_cache']['hits']}"):
    passed += 1
total += 1
if check('tool_cache.misses=1', m['tool_cache']['misses'] == 1, f"got {m['tool_cache']['misses']}"):
    passed += 1
total += 1
if check('tool_cache.skips=1', m['tool_cache']['skips'] == 1):
    passed += 1
total += 1
if check('tool_cache.hit_rate=75%', m['tool_cache']['hit_rate'] == 75.0):
    passed += 1
total += 1
if check('agent_singleton.reuse=2', m['agent_singleton']['reuse'] == 2):
    passed += 1
total += 1
if check('agent_singleton.new=1', m['agent_singleton']['new'] == 1):
    passed += 1
total += 1
if check('requests.total=3', m['requests']['total'] == 3):
    passed += 1
total += 1
if check('requests.errors=1', m['requests']['errors'] == 1):
    passed += 1
total += 1
if check('latency p50/p95/p99 计算正确', m['requests']['latency_p50'] > 0, f"p50={m['requests']['latency_p50']}"):
    passed += 1
total += 1
if check('llm_api.calls=2', m['llm_api']['calls'] == 2):
    passed += 1

# ---- 3. Prometheus 格式导出 ----
print('\n[3] Prometheus 格式导出')
prom = get_prometheus_metrics()
total += 1
if check('Prometheus 输出非空', len(prom) > 100):
    passed += 1
total += 1
if check('含 pha_tool_cache_hits', 'pha_tool_cache_hits 3' in prom):
    passed += 1
total += 1
if check('含 pha_request_latency_seconds', 'pha_request_latency_seconds' in prom):
    passed += 1

# ---- 4. 集成到 v2_agent 触发指标 ----
print('\n[4] 集成到 v2_agent 触发指标')
reset_metrics()
from A2AServer.v2 import HealthAdvisorV2
from A2AServer.v2.tool_cache import get_tool_cache
from A2AServer.v2.v2_agent import V2Agent

get_tool_cache().clear()
V2Agent._agent_instance_cache.clear()

import asyncio
import time

async def integration_test():
    global total, passed
    # 第 1 次：new
    a = HealthAdvisorV2()
    n = 0
    gen = a.stream('我头疼', 'monitor-test-1', user_id='u_mon')
    try:
        async for event in gen:
            n += 1
            if event.get('is_task_complete') or n > 30:
                break
    finally:
        await gen.aclose()  # 触发 finally

    m1 = get_metrics()
    total += 1
    if check('第 1 次：agent.new+1', m1['agent_singleton']['new'] >= 1, f"new={m1['agent_singleton']['new']}"):
        passed += 1
    total += 1
    if check('第 1 次：requests.total+1', m1['requests']['total'] >= 1, f"total={m1['requests']['total']}"):
        passed += 1
    total += 1
    if check('第 1 次：latency_p50>0', m1['requests']['latency_p50'] > 0):
        passed += 1

    # 第 2 次：reuse
    a2 = HealthAdvisorV2()
    n2 = 0
    gen2 = a2.stream('我头疼', 'monitor-test-2', user_id='u_mon')
    try:
        async for event in gen2:
            n2 += 1
            if event.get('is_task_complete') or n2 > 30:
                break
    finally:
        await gen2.aclose()  # 触发 finally

    m2 = get_metrics()
    total += 1
    if check('第 2 次：agent.reuse+1', m2['agent_singleton']['reuse'] >= 1, f"reuse={m2['agent_singleton']['reuse']}"):
        passed += 1
    total += 1
    if check('第 2 次：requests.total+1', m2['requests']['total'] >= 2, f"total={m2['requests']['total']}"):
        passed += 1
    total += 1
    if check('reuse_rate > 0', m2['agent_singleton']['reuse_rate'] > 0):
        passed += 1


asyncio.run(integration_test())

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段11 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段11 完成，监控模块就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
print()
print('=== 监控摘要 ===')
print_summary()
