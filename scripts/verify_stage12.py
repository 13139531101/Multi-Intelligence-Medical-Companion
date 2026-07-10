"""阶段12 验收 - 限流中间件"""
import os
import sys
import asyncio
import time
from pathlib import Path

from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('PHA v2 阶段12 验收 - 限流')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 模块导入 ----
print('\n[1] 限流模块导入')
from A2AServer.v2.rate_limit import (
    TokenBucket,
    SlidingWindowLimiter,
    PHA2RateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
    RateLimitError,
)

total += 1
if check('TokenBucket 可导入', TokenBucket is not None):
    passed += 1
total += 1
if check('SlidingWindowLimiter 可导入', SlidingWindowLimiter is not None):
    passed += 1
total += 1
if check('PHA2RateLimiter 可导入', PHA2RateLimiter is not None):
    passed += 1

# ---- 2. TokenBucket 单元测试 ----
print('\n[2] TokenBucket 单元测试')


async def test_token_bucket():
    global total, passed

    # 2.1: 初始满桶
    tb = TokenBucket(rate=10, capacity=10)
    allowed = 0
    for _ in range(15):
        if await tb.acquire():
            allowed += 1
    total += 1
    if check('TokenBucket 初始满 10 个允许 10 次', allowed == 10, f'allowed={allowed}'):
        passed += 1

    # 2.2: 等待补充
    tb2 = TokenBucket(rate=10, capacity=10)
    # 耗尽
    for _ in range(10):
        await tb2.acquire()
    # 等 0.2s 应补充 ~2 个
    await asyncio.sleep(0.2)
    allowed2 = 0
    for _ in range(5):
        if await tb2.acquire():
            allowed2 += 1
    total += 1
    if check('TokenBucket 0.2s 补充 ~2 个', 1 <= allowed2 <= 4, f'allowed={allowed2} (期望 1-4)'):
        passed += 1


asyncio.run(test_token_bucket())

# ---- 3. SlidingWindowLimiter 单元测试 ----
print('\n[3] SlidingWindowLimiter 单元测试')


async def test_sliding():
    global total, passed

    sw = SlidingWindowLimiter(max_requests=3, window_sec=1.0)

    # 3.1: 3 次允许
    allowed = 0
    for _ in range(3):
        if await sw.allow("user1"):
            allowed += 1
    total += 1
    if check('3 次请求全部允许', allowed == 3):
        passed += 1

    # 3.2: 第 4 次拒绝
    total += 1
    if check('第 4 次被拒绝', not await sw.allow("user1")):
        passed += 1

    # 3.3: 不同 key 独立
    total += 1
    if check('不同 key 独立计数', await sw.allow("user2")):
        passed += 1

    # 3.4: 窗口过期后恢复
    await asyncio.sleep(1.1)
    total += 1
    if check('窗口过期后恢复', await sw.allow("user1")):
        passed += 1


asyncio.run(test_sliding())

# ---- 4. PHA2RateLimiter 单元测试 ----
print('\n[4] PHA2RateLimiter 单元测试')


async def test_combined():
    global total, passed

    # 用低 QPS 测试（不传 agent 避免 agent_limiter 干扰）
    limiter = PHA2RateLimiter(llm_qps=5, user_rpm=3, agent_rpm=10)

    # 4.1: 正常允许
    allowed = 0
    for _ in range(3):
        if await limiter.allow_llm_call(user_id="u1"):
            allowed += 1
    total += 1
    if check('3 次允许（user_rpm=3）', allowed == 3, f'allowed={allowed}'):
        passed += 1

    # 4.2: user 超限
    total += 1
    if check('user 超限拒绝', not await limiter.allow_llm_call(user_id="u1")):
        passed += 1

    # 4.3: 不同 user 仍可
    total += 1
    if check('不同 user 仍可', await limiter.allow_llm_call(user_id="u2")):
        passed += 1

    # 4.4: stats 记录
    s = limiter.stats()
    total += 1
    if check('stats 记录 llm_allowed=4', s["llm_allowed"] == 4, f"got {s['llm_allowed']}"):
        passed += 1
    total += 1
    if check('stats 记录 user_denied>=1', s["user_denied"] >= 1, f"got {s['user_denied']}"):
        passed += 1


asyncio.run(test_combined())

# ---- 5. 全局单例 ----
print('\n[5] 全局单例')
reset_rate_limiter()
os.environ["PHA_LLM_QPS"] = "20"
os.environ["PHA_USER_RPM"] = "100"
l1 = get_rate_limiter()
l2 = get_rate_limiter()
total += 1
if check('全局单例（同一对象）', l1 is l2):
    passed += 1
total += 1
if check('环境变量生效 PHA_LLM_QPS=20', l1.llm_bucket.rate == 20.0, f"rate={l1.llm_bucket.rate}"):
    passed += 1
total += 1
if check('环境变量生效 PHA_USER_RPM=100', l1.user_limiter.max_requests == 100):
    passed += 1
del os.environ["PHA_LLM_QPS"]
del os.environ["PHA_USER_RPM"]
reset_rate_limiter()

# ---- 6. 集成到 V2Agent ----
print('\n[6] V2Agent 集成限流')
os.environ["PHA_LLM_QPS"] = "100"  # 调大，避免 llm 维度干扰
os.environ["PHA_USER_RPM"] = "1"
os.environ["PHA_AGENT_RPM"] = "100"  # 调大，避免 agent 维度干扰
os.environ["PHA_RATE_LIMIT_WINDOW"] = "600"  # 拉长窗口，避免测试间隔 > 60s 误判
os.environ["PHA_RATE_LIMIT"] = "true"
reset_rate_limiter()
from A2AServer.v2 import HealthAdvisorV2
from A2AServer.v2.v2_agent import V2Agent
from A2AServer.v2.tool_cache import get_tool_cache

get_tool_cache().clear()
V2Agent._agent_instance_cache.clear()


async def integration_test():
    global total, passed

    # 第 1 次：允许
    a = HealthAdvisorV2()
    n = 0
    rate_limited = False
    gen = a.stream('我头疼', 'rl-1', user_id='u_rl_1')
    try:
        async for event in gen:
            n += 1
            if event.get("rate_limited"):
                rate_limited = True
                break
            if event.get("is_task_complete"):
                break
    finally:
        await gen.aclose()

    total += 1
    if check('第 1 次：未限流（user_rpm=1 没用过）', not rate_limited, f'rate_limited={rate_limited}'):
        passed += 1

    # 第 2 次：同一 user 立刻再用 -> 限流
    a2 = HealthAdvisorV2()
    n2 = 0
    rate_limited2 = False
    gen2 = a2.stream('我头疼', 'rl-2', user_id='u_rl_1')
    try:
        async for event in gen2:
            n2 += 1
            if event.get("rate_limited"):
                rate_limited2 = True
                break
            if n2 > 5:  # 限流只 1 个 event
                break
    finally:
        await gen2.aclose()

    total += 1
    if check('第 2 次：限流（user_rpm=1 已用）', rate_limited2, f'rate_limited={rate_limited2}'):
        passed += 1

    # 不同 user 不限
    a3 = HealthAdvisorV2()
    n3 = 0
    rate_limited3 = False
    gen3 = a3.stream('我头疼', 'rl-3', user_id='u_rl_2')
    try:
        async for event in gen3:
            n3 += 1
            if event.get("rate_limited"):
                rate_limited3 = True
                break
            if n3 > 5:
                break
    finally:
        await gen3.aclose()

    total += 1
    if check('不同 user 不限流', not rate_limited3, f'rate_limited={rate_limited3}'):
        passed += 1


asyncio.run(integration_test())

# 清理
os.environ["PHA_RATE_LIMIT"] = "false"
del os.environ["PHA_LLM_QPS"]
del os.environ["PHA_USER_RPM"]
del os.environ["PHA_AGENT_RPM"]
reset_rate_limiter()

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段12 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段12 完成，限流就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
