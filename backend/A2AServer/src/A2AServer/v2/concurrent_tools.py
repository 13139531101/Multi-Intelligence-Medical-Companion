"""
PHA v2 并发工具调用（阶段11 性能优化）

**问题**：LangChain Agent 串行执行 tool_calls，多个独立工具时延迟叠加
  例如：3 个独立 search 调用 -> 3*5s = 15s

**优化**：对**独立工具调用**用 asyncio.gather 并发执行
  - 3 个独立 search -> max(5s, 5s, 5s) = 5s（节省 66%）

**实现思路**：
- LLM 一次输出多个 tool_calls
- 我们拦截后按依赖关系分组（v1: 全部独立）
- 用 asyncio.gather 并发执行
- 把结果合并回 message 流

**注意**：
- 仅并发**无依赖**的 tool_call
- 写操作不并发（避免 race condition）
- 已被工具调用缓存命中的不并发（已在缓存层处理）
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ============================================================
# 并发执行器
# ============================================================
async def execute_tool_calls_concurrent(
    tool_calls: list[dict],
    tool_executor: Callable,
    *,
    max_concurrency: int = 5,
) -> list[Any]:
    """
    并发执行多个 tool_call

    Args:
        tool_calls: [{"name": "search_X", "args": {...}}, ...]
        tool_executor: 单个 tool_call 的执行器 (callable)
        max_concurrency: 最大并发数（防止 LLM 限流）

    Returns:
        [result1, result2, ...] (按输入顺序)
    """
    if not tool_calls:
        return []

    if len(tool_calls) == 1:
        # 单个 tool_call 不需要并发
        return [await _safe_call(tool_executor, tool_calls[0])]

    # 信号量限流
    sem = asyncio.Semaphore(max_concurrency)

    async def _run_one(tc):
        async with sem:
            return await _safe_call(tool_executor, tc)

    # 并发执行
    start = time.time()
    results = await asyncio.gather(
        *[_run_one(tc) for tc in tool_calls],
        return_exceptions=True,
    )
    elapsed = time.time() - start

    logger.info(
        "[concurrent_tools] executed %d tool_calls in %.2fs (max_concurrency=%d)",
        len(tool_calls),
        elapsed,
        max_concurrency,
    )

    return results


async def _safe_call(executor: Callable, tool_call: dict) -> Any:
    """安全调用单个 tool，异常转 dict"""
    try:
        return await executor(tool_call)
    except Exception as e:
        logger.exception(f"[concurrent_tools] tool_call {tool_call.get('name')} failed")
        return {"error": str(e), "tool": tool_call.get("name")}
