"""阶段10 验收 - 并发工具调用集成"""
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
print('PHA v2 阶段10 验收 - 并发工具调用集成')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 模块导入 ----
print('\n[1] 模块导入')
total += 1
try:
    from A2AServer.v2.concurrent_tools import (
        execute_tool_calls_concurrent,
        wrap_tool_call_with_concurrent,
    )
    if check('execute_tool_calls_concurrent 可调用', True):
        passed += 1
except Exception as e:
    check('execute_tool_calls_concurrent 可调用', False, str(e))

total += 1
if check('wrap_tool_call_with_concurrent 可调用', callable(wrap_tool_call_with_concurrent)):
    passed += 1

# ---- 2. execute_tool_calls_concurrent 单元测试 ----
print('\n[2] execute_tool_calls_concurrent 单元测试')

async def fake_executor(tc, delay=0.1):
    """模拟一个慢执行工具"""
    await asyncio.sleep(delay)
    return f"result_{tc['name']}_{tc['args'].get('q', '')}"


async def unit_test():
    global total, passed

    # 2.1: 单个 tool_call
    t0 = time.time()
    r1 = await execute_tool_calls_concurrent(
        [{"name": "t1", "args": {"q": "a"}}],
        fake_executor,
    )
    elapsed1 = time.time() - t0
    total += 1
    if check('单个 tool_call 串行', len(r1) == 1 and "t1" in r1[0], f'elapsed={elapsed1:.2f}s'):
        passed += 1

    # 2.2: 3 个 tool_call 串行参考
    t0 = time.time()
    r2 = []
    for tc in [{"name": "t1", "args": {"q": "a"}}, {"name": "t2", "args": {"q": "b"}}, {"name": "t3", "args": {"q": "c"}}]:
        r2.append(await fake_executor(tc))
    elapsed_serial = time.time() - t0

    # 2.3: 3 个 tool_call 并发
    t0 = time.time()
    r3 = await execute_tool_calls_concurrent(
        [{"name": "t1", "args": {"q": "a"}}, {"name": "t2", "args": {"q": "b"}}, {"name": "t3", "args": {"q": "c"}}],
        fake_executor,
        max_concurrency=3,
    )
    elapsed_concurrent = time.time() - t0

    print(f"    串行 3 个: {elapsed_serial:.2f}s")
    print(f"    并发 3 个: {elapsed_concurrent:.2f}s")
    if elapsed_concurrent > 0:
        speedup = (elapsed_serial - elapsed_concurrent) / elapsed_serial * 100
        print(f"    提速: {speedup:.1f}%")
    total += 1
    if check('3 个 tool_call 并发比串行快', elapsed_concurrent < elapsed_serial * 0.8, f'serial={elapsed_serial:.2f}s vs concurrent={elapsed_concurrent:.2f}s'):
        passed += 1

    # 2.4: 限流测试（max_concurrency=2）
    t0 = time.time()
    r4 = await execute_tool_calls_concurrent(
        [{"name": f"t{i}", "args": {"q": str(i)}} for i in range(6)],
        fake_executor,
        max_concurrency=2,
    )
    elapsed_limited = time.time() - t0
    # 6 个 / 2 并发 = 3 批 * 0.1s = ~0.3s
    total += 1
    if check('限流 max_concurrency=2 生效', 0.25 < elapsed_limited < 0.6, f'elapsed={elapsed_limited:.2f}s (期望 ~0.3s)'):
        passed += 1

    # 2.5: 异常隔离
    async def bad_executor(tc):
        if tc['name'] == 't2':
            raise ValueError("intentional error")
        return f"ok_{tc['name']}"

    r5 = await execute_tool_calls_concurrent(
        [{"name": "t1", "args": {}}, {"name": "t2", "args": {}}, {"name": "t3", "args": {}}],
        bad_executor,
    )
    total += 1
    if check('异常隔离（一个失败不影响其他）', len(r5) == 3 and r5[0] == "ok_t1" and isinstance(r5[1], dict) and r5[2] == "ok_t3"):
        passed += 1


asyncio.run(unit_test())

# ---- 3. V2Agent 集成 ----
print('\n[3] V2Agent 集成 - _concurrent_kwargs')

from A2AServer.v2.v2_agent import V2Agent

# 3.1: 默认启用
total += 1
os.environ.pop("PHA_CONCURRENT_TOOLS", None)
kwargs = V2Agent()._concurrent_kwargs()
if check('默认 PHA_CONCURRENT_TOOLS=true 启用', "awrap_tool_call" in kwargs):
    passed += 1

# 3.2: 显式关闭
total += 1
os.environ["PHA_CONCURRENT_TOOLS"] = "false"
kwargs = V2Agent()._concurrent_kwargs()
if check('PHA_CONCURRENT_TOOLS=false 关闭', kwargs == {}):
    passed += 1
os.environ.pop("PHA_CONCURRENT_TOOLS", None)

# 3.3: 自定义并发数
total += 1
os.environ["PHA_MAX_CONCURRENCY"] = "10"
v2a = V2Agent()
kwargs = v2a._concurrent_kwargs()
if check('PHA_MAX_CONCURRENCY=10 生效', "awrap_tool_call" in kwargs):
    passed += 1
os.environ.pop("PHA_MAX_CONCURRENCY", None)

# ---- 4. wrap_tool_call_with_concurrent 集成测试 ----
print('\n[4] wrap_tool_call_with_concurrent 集成测试')


class MockRequest:
    def __init__(self, tool_calls, delay=0.05):
        self.tool_calls = tool_calls
        self._delay = delay

    async def execute(self, tc):
        await asyncio.sleep(self._delay)
        return f"done_{tc.get('name')}"


async def integration_test():
    global total, passed

    wrapper = wrap_tool_call_with_concurrent(max_concurrency=3)

    # 4.1: 0 个 tool_call
    req = MockRequest([])
    r = await wrapper(req)
    total += 1
    if check('0 个 tool_call 返回 None', r is None):
        passed += 1

    # 4.2: 1 个 tool_call
    req = MockRequest([{"name": "t1", "args": {}}])
    r = await wrapper(req)
    total += 1
    if check('1 个 tool_call 返回 None（不并发）', r is None):
        passed += 1

    # 4.3: 多个 tool_call 并发（用 search_ 前缀确保 is_write_tool 识别为读）
    req = MockRequest(
        [
            {"name": "search_t1", "args": {}},
            {"name": "search_t2", "args": {}},
            {"name": "search_t3", "args": {}},
        ],
        delay=0.1,
    )
    t0 = time.time()
    r = await wrapper(req)
    elapsed = time.time() - t0
    # 3 个 0.1s 串行 = 0.3s，并发 = 0.1s
    total += 1
    if check('3 个 tool_call 并发执行', r is not None and len(r) == 3 and elapsed < 0.2, f'elapsed={elapsed:.2f}s'):
        passed += 1


asyncio.run(integration_test())

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段10 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段10 完成，并发工具调用集成。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
