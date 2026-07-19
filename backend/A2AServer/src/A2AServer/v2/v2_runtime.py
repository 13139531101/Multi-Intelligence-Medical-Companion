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
TodoListMiddleware = None
LLMToolSelectorMiddleware = None
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
            TodoListMiddleware,
            LLMToolSelectorMiddleware,
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
        try:
            from langchain.agents.middleware import TodoListMiddleware
        except ImportError:
            pass
        try:
            from langchain.agents.middleware import LLMToolSelectorMiddleware
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
            # Built-in types: email, url, ip, mac_address, credit_card
            # Custom regex: phone (中国手机号 + 国际格式)
            # apply_to_output=True: LLM 输出也 redact (避免 LLM "泄露" 用户数据)
            # apply_to_tool_results=True: tool 输出也 redact (避免数据库里查出来的 PII 被 LLM re-emit)
            for pii_type in (
                "email",         # 邮箱
                "url",           # URL
                "ip",            # IP 地址 (哈希保留反向追溯)
                "credit_card",   # 信用卡号 (mask 保留后 4 位)
            ):
                strategy = "hash" if pii_type == "ip" else ("mask" if pii_type == "credit_card" else "redact")
                try:
                    m = PIIMiddleware(
                        pii_type=pii_type,
                        strategy=strategy,
                        apply_to_input=True,
                        apply_to_output=True,
                        apply_to_tool_results=True,
                    )
                    middlewares.append(m)
                except Exception as e:
                    logger.debug("[v2_runtime] PIIMiddleware[%s] 失败: %s", pii_type, e)
            # 自定义: phone (中国 11 位手机号 + 国际格式)
            try:
                # 匹配 +86 138xxxxxxx, 138xxxxxxx, 138-xxxx-xxxx 等
                phone_regex = (
                    r"(?:\+?86[-\s]?)?"              # 可选 +86
                    r"1[3-9]\d{9}"                     # 中国 11 位手机
                    r"|"
                    r"\+\d{1,3}[-\s]?\d{3,14}"        # 国际格式
                )
                m = PIIMiddleware(
                    pii_type="phone",
                    detector=phone_regex,
                    strategy="mask",
                    apply_to_input=True,
                    apply_to_output=True,
                    apply_to_tool_results=True,
                )
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] PIIMiddleware[phone custom] 失败: %s", e)

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
                    # 每个 tool 配置允许的决策 + 是否需要描述 + 等待提示
                    # 4 种: approve / edit / reject / respond
                    allowed = {
                        "delete_": ["approve", "reject"],          # 删除操作简单 confirm/cancel
                        "send_": ["approve", "reject", "respond"], # 通知 类
                        "default": ["approve", "edit", "reject"],  # 默认多种
                    }
                    m = HumanInTheLoopMiddleware(
                        interrupt_on=interrupt_cfg,
                        description_prefix=(
                            "🔒 [PHA 安全审核] 以下操作不可逆或影响大, 请确认:\n"
                            "  • ✅ 同意 (approve)\n"
                            "  • ✏️ 修改参数 (edit)\n"
                            "  • ❌ 拒绝 (reject)\n"
                        ),
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
                # trigger=8000 tokens 时开始清理太老的 tool 输出
                # keep=5: 保留最近 5 个 tool_use 不清
                # clear_at_least=2000: 至少清出 2000 tokens 才执行 (避免频繁触发)
                # clear_tool_inputs=False: 保留 tool inputs (LLM 需要看参数)
                # exclude_tools: 永远不清理的 tool (HITL 用)
                from langchain.agents.middleware.context_editing import ClearToolUsesEdit
                edit = ClearToolUsesEdit(
                    trigger=8000,
                    clear_at_least=2000,
                    keep=5,
                    clear_tool_inputs=False,
                    exclude_tools=("ask_user_for_clarification",),
                )
                m = ContextEditingMiddleware(edits=[edit], token_count_method="approximate")
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] ContextEditing 不可用: %s", e)

        # ============================================================
        # 10. TodoListMiddleware - 多步任务规划 (write_todos tool)
        # ============================================================
        if TodoListMiddleware is not None:
            try:
                # 自定义 system_prompt: 中文 + PHA 偏好 (≤7 步, 简单任务直接做)
                pha_todo_prompt = """## `write_todos` 任务规划工具

你可以使用 `write_todos` 工具来管理和规划复杂目标。
适用于 ≥3 步的复杂任务, 简单任务直接完成即可, **不要**强写 todos 浪费时间。

### 使用规则

1. **不要并行调用 write_todos** (一次只调一次)
2. **总数限制 ≤7 步** (避免 token 浪费)
3. **每完成一步立刻标记 completed**, 别 batch
4. **根据新信息更新列表**: 新任务可加, 失效任务可删
5. **每步简短 (一句话)** — "评估血压数据" / "添加提醒" / "修改用药时间"
6. **状态**: pending (未开始) / in_progress (进行中) / completed (已完成)

### 不要使用 write_todos 的场景

- 单步任务 (例如: 简单问候 / 闲聊)
- 用户只是想查信息
- 加 1 个提醒 / 改 1 个字段 — 直接做完即可, 不必写 todo

### 完成 todo 后

写 todos 是工作追踪, **不是答案**。最后必须给用户真实答复 (实际数据, 计算结果, 总结等)。
"""
                m = TodoListMiddleware(system_prompt=pha_todo_prompt)
                middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] TodoList 不可用: %s", e)

        # ============================================================
        # 11. LLMToolSelectorMiddleware - 智能选 tool 减少 LLM context
        # ============================================================
        # 仅当主模型是 OpenAI 时使用 (DeepSeek 不支持 strict JSON schema)
        if LLMToolSelectorMiddleware is not None and chat_model is not None:
            try:
                # 检查 model provider: deepseek / qwen 不支持 strict JSON mode
                model_str = model.lower() if isinstance(model, str) else ""
                skip = (
                    "deepseek" in model_str
                    or "qwen" in model_str
                    or "anthropic" in model_str
                )
                if skip:
                    logger.debug(
                        "[v2_runtime] LLMToolSelector 跳过: model=%s 不支持 strict JSON",
                        model,
                    )
                else:
                    # 从 ~14 tools 中, 选 ≤5 个最相关的, 减少 LLM 决策时间
                    m = LLMToolSelectorMiddleware(
                        model=chat_model,
                        max_tools=5,
                    )
                    middlewares.append(m)
            except Exception as e:
                logger.debug("[v2_runtime] LLMToolSelector 不可用: %s", e)

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
