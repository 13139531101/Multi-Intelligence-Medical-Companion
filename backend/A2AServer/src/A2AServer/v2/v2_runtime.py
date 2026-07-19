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
from typing import AsyncIterable, Any, List

logger = logging.getLogger(__name__)

# ---- LangChain 1.x 探测 ----
# 真正调用 create_agent 的是 v2_agent.py；这里只测 langgraph.checkpoint 是否装好
# （v2_agent.py 内部自己 import langchain.agents.create_agent）
_LANGCHAIN_V2_OK = False
# 解包装各种 middleware, 失败用 None 占位
SummarizationMiddleware = None
PIIMiddleware = None
HumanInTheLoopMiddleware = None
ToolCallLimitMiddleware = None
ModelFallbackMiddleware = None
ModelCallLimitMiddleware = None
ToolRetryMiddleware = None
ModelRetryMiddleware = None
ContextEditingMiddleware = None
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
            HumanInTheLoopMiddleware,
            ToolCallLimitMiddleware,
            ModelFallbackMiddleware,
            ModelCallLimitMiddleware,
            ToolRetryMiddleware,
            ModelRetryMiddleware,
            ContextEditingMiddleware,
        )
    except ImportError as e:
        # 解封失败时每个单独 import
        logger.debug("[v2_runtime] 个别 middleware import 失败: %s", e)
        try:
            from langchain.agents.middleware import SummarizationMiddleware, PIIMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import HumanInTheLoopMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import ToolCallLimitMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import ModelFallbackMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import ModelCallLimitMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import ToolRetryMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import ModelRetryMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import ContextEditingMiddleware
        except ImportError:
            pass
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

    def get_middlewares(self, model: str, chat_model=None, agent_name: str = "default"):
        """获取标准 Middleware 列表（医疗场景）.

        阶段48-16: 加 7 种新 middleware, 总共 ~10 个.
          - PIIMiddleware x 2 (email, url redact)
          - SummarizationMiddleware (长上下文压缩)
          - HumanInTheLoopMiddleware (危险操作确认)
          - ToolCallLimitMiddleware (防 LLM 死循环)
          - ModelCallLimitMiddleware (LLM 调轮次)
          - ToolRetryMiddleware (tool 调用重试)
          - ModelRetryMiddleware (LLM 重试)
          - ModelFallbackMiddleware (DeepSeek → OpenAI fallback)
          - ContextEditingMiddleware (长对话裁剪)

        Args:
            model: model name 字符串
            chat_model: 可选, chat_model 实例
            agent_name: 决定哪些 tool 是 dangerous
        """
        if not _LANGCHAIN_V2_OK:
            return []

        middlewares: List = []

        # ============================================================
        # 1. PIIMiddleware - 邮箱 / URL 脱敏
        # ============================================================
        if PIIMiddleware is not None:
            for pii_type in ("email", "url"):
                try:
                    m = PIIMiddleware(pii_type=pii_type, strategy="redact")
                    middlewares.append(m)
                except Exception as e:
                    logger.debug("[v2_runtime] PIIMiddleware[%s] 失败: %s", pii_type, e)

        # ============================================================
        # 2. SummarizationMiddleware - 长上下文自动压缩 (节省 token)
        # ============================================================
        if SummarizationMiddleware is not None:
            try:
                if chat_model is not None:
                    m = SummarizationMiddleware(model=chat_model)
                else:
                    m = SummarizationMiddleware(model=model)
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] SummarizationMiddleware 不可用: %s", e)

        # ============================================================
        # 3. HumanInTheLoopMiddleware - 危险操作确认
        # ============================================================
        if HumanInTheLoopMiddleware is not None:
            try:
                from .dangerous_tools import get_interrupt_config
                interrupt_cfg = get_interrupt_config(agent_name)
                if interrupt_cfg:
                    m = HumanInTheLoopMiddleware(
                        interrupt_on=interrupt_cfg,
                        description_prefix="[PHA 安全] 该操作需要您确认后才会执行",
                    )
                    middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] HumanInTheLoop 不可用: %s", e)

        # ============================================================
        # 4. ToolCallLimitMiddleware - 防止 LLM tool 调用死循环
        # ============================================================
        if ToolCallLimitMiddleware is not None:
            try:
                # 单次 run LLM 调 tool 最多 12 次 (足够, 防止死循环)
                m = ToolCallLimitMiddleware(thread_limit=12, exit_behavior="continue")
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ToolCallLimit 不可用: %s", e)

        # ============================================================
        # 5. ModelCallLimitMiddleware - LLM 总轮次限制 (整个 thread)
        # ============================================================
        if ModelCallLimitMiddleware is not None:
            try:
                m = ModelCallLimitMiddleware(thread_limit=30, exit_behavior="end")
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ModelCallLimit 不可用: %s", e)

        # ============================================================
        # 6. ToolRetryMiddleware - tool 失败自动重试 (DB 抖动)
        # ============================================================
        if ToolRetryMiddleware is not None:
            try:
                m = ToolRetryMiddleware(
                    max_retries=2,
                    backoff_factor=0.5,
                    initial_delay=0.5,
                    max_delay=8.0,
                )
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ToolRetry 不可用: %s", e)

        # ============================================================
        # 7. ModelRetryMiddleware - LLM 临时失败自动重试 (rate limit)
        # ============================================================
        if ModelRetryMiddleware is not None:
            try:
                m = ModelRetryMiddleware(
                    max_retries=2,
                    backoff_factor=0.5,
                    initial_delay=1.0,
                    max_delay=10.0,
                )
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ModelRetry 不可用: %s", e)

        # ============================================================
        # 8. ModelFallbackMiddleware - DeepSeek 挂了 → OpenAI fallback
        # ============================================================
        if ModelFallbackMiddleware is not None and chat_model is not None:
            try:
                from langchain_openai import ChatOpenAI
                fallback = ChatOpenAI(
                    model="gpt-4o-mini",
                    api_key=os.getenv("OPENAI_API_KEY") or "sk-fake",
                    base_url=os.getenv("OPENAI_API_BASE"),
                    temperature=0,
                )
                m = ModelFallbackMiddleware(chat_model, fallback)
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ModelFallback 不可用 (OPENAI_API_KEY 未设?): %s", e)

        # ============================================================
        # 9. ContextEditingMiddleware - 长对话裁剪早期消息
        # ============================================================
        if ContextEditingMiddleware is not None:
            try:
                # 默认用 ClearToolUsesEdit (跟 Anthropic default 一致)
                m = ContextEditingMiddleware(token_count_method="approximate")
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ContextEditing 不可用: %s", e)

        if middlewares:
            logger.info(
                "[v2_runtime] %s 加载 %d 个 middlewares: %s",
                agent_name, len(middlewares),
                [type(m).__name__ for m in middlewares],
            )
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
