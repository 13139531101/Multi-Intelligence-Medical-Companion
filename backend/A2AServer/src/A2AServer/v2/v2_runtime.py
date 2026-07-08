"""
PHA v2 智能体运行时（LangChain 1.0 / LangGraph 1.0）

**作用**：
- 统一封装 LangChain 1.0 `create_agent` + `Middleware` + Checkpointer
- 替代 `BasicAgent` 中手写的 prompt 拼装、tool loop、memory 写回
- 提供标准化的流式输出，兼容现有 A2A JSON-RPC 协议

**设计原则**：
- 与 `BasicAgent` 共存（v1 走老路径，v2 走新路径）
- 失败自动 fallback 到 BasicAgent
- 不依赖 LangChain 1.0 时降级到 stub（不破坏旧环境）

详细方案见 docs/Chinese/REFACTOR_PLAN_v2.md
"""
from __future__ import annotations

import os
import logging
from typing import AsyncIterable, Any

logger = logging.getLogger(__name__)

# ---- LangChain 1.x 探测 ----
_LANGCHAIN_V2_OK = False
try:
    from langchain.agents import create_agent
    from langchain.agents.middleware import (
        SummarizationMiddleware,
        PIIRedactionMiddleware,
    )
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    _LANGCHAIN_V2_OK = True
except ImportError as e:
    logger.warning(
        "[v2_runtime] LangChain 1.x 不可用，V2 模式降级：%s", e
    )


# ============================================================
# 运行时：单例 + 全局配置
# ============================================================
class V2AgentRuntime:
    """PHA v2 智能体运行时（单例）"""

    def __init__(self):
        self._checkpointer = None
        self._middleware_initialized = False

    @property
    def available(self) -> bool:
        """v2 运行时是否可用（LangChain 1.x 是否装好）"""
        return _LANGCHAIN_V2_OK

    async def get_checkpointer(self):
        """获取 Checkpointer（生产 PostgresSaver，开发 InMemorySaver）"""
        if self._checkpointer is not None:
            return self._checkpointer

        if not _LANGCHAIN_V2_OK:
            return None

        db_url = os.getenv("PHA_CHECKPOINT_DB_URL") or os.getenv("DATABASE_URL")
        if db_url:
            try:
                # 生产：PostgresSaver（需先调 setup() 建表）
                self._checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
                await self._checkpointer.setup()
                logger.info("[v2_runtime] Checkpointer = AsyncPostgresSaver")
            except Exception as e:
                logger.warning(
                    "[v2_runtime] PostgresSaver 初始化失败，回退 InMemorySaver: %s", e
                )
                self._checkpointer = InMemorySaver()
        else:
            self._checkpointer = InMemorySaver()
            logger.info("[v2_runtime] Checkpointer = InMemorySaver (开发模式)")

        return self._checkpointer

    def get_middlewares(self, model: str):
        """获取标准 Middleware 列表（医疗场景）"""
        if not _LANGCHAIN_V2_OK:
            return []

        middlewares = [
            PIIRedactionMiddleware(patterns=["email", "phone", "id_card"]),
        ]

        # 长上下文自动压缩（节省 token）
        try:
            middlewares.append(SummarizationMiddleware(model=model))
        except Exception as e:
            logger.debug("[v2_runtime] SummarizationMiddleware 不可用: %s", e)

        return middlewares


_runtime: V2AgentRuntime | None = None


def get_runtime() -> V2AgentRuntime:
    """获取全局 v2 运行时单例"""
    global _runtime
    if _runtime is None:
        _runtime = V2AgentRuntime()
    return _runtime
