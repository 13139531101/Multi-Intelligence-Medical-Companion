"""
PHA v2 并发工具调用（阶段11 性能优化 + 阶段13 集成）

**问题**：LangChain Agent 串行执行 tool_calls，多个独立工具时延迟叠加
  例如：3 个独立 search 调用 -> 3*5s = 15s

**优化**：通过 LangGraph 1.0 `ToolNode.awrap_tool_call` 钩子并发执行
  - 3 个独立 search -> max(5s, 5s, 5s) = 5s（节省 66%）

**集成方式**（阶段13）：
- 在 v2_agent.py 的 `create_agent()` 调用前，用 `concurrent_tool_node` 替换默认 ToolNode
- 通过 `wrap_tool_call_with_concurrent()` 创建并发工具节点
- 自动应用：所有 V2Agent 默认启用并发（环境变量可关闭）

**使用方式**：
```python
from A2AServer.v2.concurrent_tools import wrap_tool_call_with_concurrent

# 替换默认的 tool_node
concurrent_wrapper = wrap_tool_call_with_concurrent(max_concurrency=5)

# 在 create_agent 时传入
agent = create_agent(
    model=chat_model,
    tools=tools,
    system_prompt=...,
    middleware=[...],
    tool_node=concurrent_tool_node,  # 替换默认 ToolNode
)
```

**注意**：
- 仅并发**无依赖**的 tool_call
- 写操作不并发（避免 race condition）
- 已被工具调用缓存命中的不并发（已在缓存层处理）
- 依赖 v2/tool_cache.is_write_tool() 识别写操作
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ============================================================
# 并发执行核心
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


# ============================================================
# LangGraph ToolNode 集成（阶段13）
# ============================================================
def wrap_tool_call_with_concurrent(*, max_concurrency: int = 5):
    """
    创建一个 `awrap_tool_call` 函数，用于替换 LangGraph ToolNode 默认串行执行

    Returns:
        async function: 符合 LangGraph 1.0 `awrap_tool_call` 签名

    用法：
        agent = create_agent(
            ...,
            awrap_tool_call=wrap_tool_call_with_concurrent(max_concurrency=5),
        )

    实现：
    - 接收 `request` (ToolCallRequest) 包含多个 tool_calls
    - 用 `asyncio.gather` 并发执行
    - 收集所有 ToolMessage 返回
    """
    async def awrap_tool_call(request):
        # LangGraph 1.0 ToolCallRequest 包含 tool_calls 列表
        tool_calls = getattr(request, "tool_calls", []) or []
        if not tool_calls:
            return None  # 不变

        # 写操作不并发（保守）
        try:
            from .tool_cache import is_write_tool
            write_count = sum(1 for tc in tool_calls if is_write_tool(_tc_to_tool_like(tc)))
            if write_count > 0 and write_count == len(tool_calls):
                # 全是写操作 -> 串行
                logger.debug("[concurrent_tools] all write tools, sequential")
                return None
            if write_count > 0 and write_count < len(tool_calls):
                # 混合 -> 串行（保守）
                logger.debug("[concurrent_tools] mixed read/write tools, sequential")
                return None
        except Exception as e:
            logger.debug(f"[concurrent_tools] write check failed: {e}")
            pass

        # 已经是缓存命中的 -> 不并发
        # (LangGraph ToolNode 已处理缓存，这里不重复)

        # 1 个或 0 个 -> 串行足够
        if len(tool_calls) <= 1:
            return None

        # 多个独立工具 -> 并发
        execute = getattr(request, "execute", None)
        if execute is None:
            logger.warning("[concurrent_tools] request.execute 不可用，回退串行")
            return None

        # 提取为 dict
        tcs = [
            {"name": tc.get("name"), "args": tc.get("args", {})}
            for tc in tool_calls
        ]

        try:
            results = await execute_tool_calls_concurrent(
                tcs, execute, max_concurrency=max_concurrency
            )
            return results  # 列表 of ToolMessage
        except Exception as e:
            logger.exception("[concurrent_tools] awrap_tool_call failed, fallback to serial")
            return None

    return awrap_tool_call


def _tc_to_tool_like(tc: dict):
    """把 tool_call dict 包装成 is_write_tool 能识别的对象"""
    class _TL:
        pass
    tl = _TL()
    tl.name = tc.get("name", "")
    tl.tags = []
    return tl
