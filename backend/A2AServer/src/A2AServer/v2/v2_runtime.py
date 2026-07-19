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
# 真正调用 create_agent 的是 v2_agent.py；这里只测 langgraph.checkpoint 是否装好
# （v2_agent.py 内部自己 import langchain.agents.create_agent）
_LANGCHAIN_V2_OK = False
try:
    from langgraph.checkpoint.memory import InMemorySaver
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:
        AsyncPostgresSaver = None
    # Middleware 是 LangChain 1.0+ 新特性，独立子包
    try:
        from langchain.agents.middleware import (
            SummarizationMiddleware,
            PIIMiddleware,           # 1.3.x 是 PIIMiddleware (不是 PIIRedactionMiddleware)
        )
    except ImportError:
        SummarizationMiddleware = None
        PIIMiddleware = None
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
        if db_url and AsyncPostgresSaver is not None:
            try:
                # 生产：PostgresSaver（langgraph-checkpoint-postgres 2.x API）
                # 2.x 的 from_conn_string 返回 AsyncContextManager，需 async with
                try:
                    # 尝试 2.x API（async context manager）
                    cm = AsyncPostgresSaver.from_conn_string(db_url)
                    saver = await cm.__aenter__()
                    try:
                        await saver.setup()
                    except Exception:
                        pass  # setup 可能已被调过
                    self._checkpointer = saver
                    logger.info("[v2_runtime] Checkpointer = AsyncPostgresSaver (langgraph-checkpoint-postgres 2.x)")
                    return self._checkpointer
                except Exception:
                    # 回退 1.x API
                    self._checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
                    await self._checkpointer.setup()
                    logger.info("[v2_runtime] Checkpointer = AsyncPostgresSaver (1.x)")
                    return self._checkpointer
            except Exception as e:
                logger.warning(
                    "[v2_runtime] PostgresSaver 初始化失败，回退 InMemorySaver: %s", e
                )

        self._checkpointer = InMemorySaver()
        logger.info("[v2_runtime] Checkpointer = InMemorySaver (开发模式)")
        return self._checkpointer

    def get_middlewares(self, model: str, chat_model=None):
        """获取标准 Middleware 列表（医疗场景）

        Args:
            model: model name 字符串 (用来判断 provider)
            chat_model: 可选, chat_model 实例 (用于 SummarizationMiddleware)
        """
        if not _LANGCHAIN_V2_OK:
            return []

        middlewares = []

        if PIIMiddleware is not None:
            try:
                # 阶段48-14: PII redaction — 医疗场景要脱敏用户隐私
                # 一个 pii_type 一个 instance, 加多个支持多种类型
                for pii_type in ("email", "url"):
                    try:
                        m = PIIMiddleware(pii_type=pii_type, strategy="redact")
                        middlewares.append(m)
                    except Exception as e:
                        logger.debug("[v2_runtime] PIIMiddleware[%s] 失败: %s", pii_type, e)
            except Exception as e:
                logger.debug("[v2_runtime] PIIMiddleware 初始化失败: %s", e)

        # 长上下文自动压缩（节省 token）
        # SummarizationMiddleware 调 init_chat_model(model_str), 需要已装的 provider
        # 优先用 chat_model 实例 (避免 init_chat_model 找不到 langchain_deepseek 等)
        if SummarizationMiddleware is not None:
            try:
                if chat_model is not None:
                    m = SummarizationMiddleware(model=chat_model)
                else:
                    # 直接传字符串, 失败就被 catched 跳过
                    m = SummarizationMiddleware(model=model)
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] SummarizationMiddleware 不可用: %s", e)

        if middlewares:
            logger.info("[v2_runtime] 加载 %d 个 middlewares: %s",
                        len(middlewares),
                        [type(m).__name__ for m in middlewares])
        return middlewares


_runtime: V2AgentRuntime | None = None


def get_runtime() -> V2AgentRuntime:
    """获取全局 v2 运行时单例"""
    global _runtime
    if _runtime is None:
        _runtime = V2AgentRuntime()
    return _runtime


# ============================================================
# 预热（阶段10 P0 优化）
# ============================================================
async def warmup_v2():
    """
    启动时预热 v2 runtime + 4 个 V2Agent

    节省首次请求的 ~3-5s 初始化时间
    适用：服务启动时调用一次

    预热内容：
    1. 初始化 Checkpointer
    2. 创建 4 个 V2Agent（触发 LangGraph 编译 + 工具加载）
    3. 触发 Embedding 模型初始化（如果用了 DashScope）
    """
    import time
    start = time.time()
    runtime = get_runtime()
    if not runtime.available:
        logger.warning("[v2_runtime] warmup skipped: LangChain 1.x 不可用")
        return False

    logger.info("[v2_runtime] starting warmup...")

    # 1. Checkpointer
    try:
        await runtime.get_checkpointer()
    except Exception as e:
        logger.warning(f"[v2_runtime] warmup checkpointer 失败: {e}")

    # 2. 4 个 V2Agent（触发 LangGraph 编译 + 工具发现）
    try:
        from .sub_agents import (
            HealthAdvisorV2,
            HealthRecordsV2,
            MedicationReminderV2,
            VisitSummaryV2,
        )
        for cls in [HealthAdvisorV2, HealthRecordsV2, MedicationReminderV2, VisitSummaryV2]:
            try:
                instance = cls()
                await instance._ensure_agent()  # 触发懒加载
                logger.info(f"[v2_runtime] warmup {cls.__name__} ok")
            except Exception as e:
                logger.warning(f"[v2_runtime] warmup {cls.__name__} 失败: {e}")
    except Exception as e:
        logger.warning(f"[v2_runtime] warmup sub_agents 失败: {e}")

    elapsed = time.time() - start
    logger.info(f"[v2_runtime] warmup 完成 (耗时 {elapsed:.1f}s)")
    return True


def warmup_v2_sync():
    """同步版本的预热（用于启动脚本）"""
    import asyncio
    try:
        return asyncio.run(warmup_v2())
    except Exception as e:
        logger.warning(f"[v2_runtime] warmup_sync 失败: {e}")
        return False
