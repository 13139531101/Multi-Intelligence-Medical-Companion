"""
PHA v2 智能体基类（V2Agent）

**作用**：
- 替代 `BasicAgent.stream()` 的核心逻辑
- 基于 LangChain 1.0 `create_agent` + Middleware
- 保持与 BasicAgent **完全一致**的流式输出格式（兼容 A2A 协议）

**差异**：
- BasicAgent 内部用 _build_initial_conversation + _stream_response_generator 手写循环
- V2Agent 内部用 create_agent 标准化 + Middleware 自动处理

**向后兼容**：
- 如果 LangChain 1.x 不可用，V2Agent.stream() 会自动降级返回错误事件
- BasicAgent 仍可继续工作
"""
from __future__ import annotations

import logging
import os
import json
from typing import AsyncIterable, Any

from .v2_runtime import get_runtime

logger = logging.getLogger(__name__)


class V2Agent:
    """
    PHA v2 智能体基类

    用法：
        class HealthAdvisorV2(V2Agent):
            name = "health_advisor"
            system_prompt = "你是健康顾问..."

            def get_tools(self):
                return [diagnosis_tool, knowledge_tool, ...]

        agent = HealthAdvisorV2()
        async for event in agent.stream(query, session_id, user_id):
            print(event)

    **单例化（阶段8 优化）**：
    - 类级别 `_agent_instance` 缓存：相同类（HealthAdvisorV2）共享同一个 LangGraph agent
    - 第一次创建耗时 ~3s，后续请求直接复用，节省 3s/请求
    - 安全性：LangGraph agent 是无状态的（state 由 thread_id 隔离），共用安全
    """

    name: str = "v2_agent"
    system_prompt: str = "You are a helpful AI assistant."

    # === 类级别单例缓存（阶段8 优化）===
    # key: (class, model) 元组；value: LangGraph agent 实例
    _agent_instance_cache: dict = {}
    _agent_instance_lock = None  # 延迟初始化的 asyncio.Lock

    def __init__(self, model: str | None = None):
        # 自动识别 LLM 提供方：DeepSeek（默认）/ OpenAI / 其它
        if model is None:
            # 阶段27 修复：只要 DEEPSEEK_API_KEY 存在就走 DeepSeek
            # （OPENAI_API_KEY 经常被 .env 复用装 DeepSeek key，不能据此走 OpenAI）
            if os.getenv("DEEPSEEK_API_KEY"):
                # DeepSeek（OpenAI 兼容协议）
                self.model = os.getenv("PHA_LLM_MODEL", "deepseek-chat")
            elif os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_BASE"):
                self.model = os.getenv("PHA_LLM_MODEL", "openai:gpt-4o-mini")
            elif os.getenv("OPENAI_API_KEY"):
                # 有 OPENAI_API_KEY 但无 BASE → 假设是 DeepSeek key 复用
                self.model = os.getenv("PHA_LLM_MODEL", "deepseek-chat")
            else:
                self.model = os.getenv("PHA_LLM_MODEL", "openai:gpt-4o-mini")
        else:
            self.model = model
        # 实例级别 _agent 保留，但优先用类单例
        self._agent = None
        self._tools = None

    def get_tools(self) -> list:
        """子类重写：返回 LangChain BaseTool 列表"""
        return []

    def _build_chat_model(self):
        """阶段48-14: 构造 chat_model 实例.
        用于 create_agent + middlewares (e.g. SummarizationMiddleware).
        返回 None 时让 create_agent 用 str model path.
        """
        if self.model.startswith("deepseek"):
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.model,
                api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                temperature=0,
            )
        elif self.model.startswith("openai:"):
            from langchain_openai import ChatOpenAI
            model_name = self.model.split(":", 1)[1]
            return ChatOpenAI(
                model=model_name,
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_API_BASE"),
                temperature=0,
            )
        return None

    def _concurrent_kwargs(self) -> dict:
        """
        阶段13 集成：返回 create_agent 的并发工具 kwargs

        注意：LangChain 1.0 `create_agent()` 不直接接受 `awrap_tool_call`，
        所以这里返回空 dict。要启用并发工具调用需要：
        1. 等 LangChain 1.x 升级暴露 ToolNode 替换
        2. 或者用户用 `concurrent_tools.execute_tool_calls_concurrent` 手动包装

        保留此方法是为了将来兼容性。
        """
        return {}  # 暂不集成到 create_agent（LangChain API 限制）

    async def _ensure_agent(self):
        """
        懒加载 + 类单例：第一次调用时创建 agent，相同类后续直接复用

        阶段8 优化：每个 V2Agent 子类共享一个 LangGraph agent 实例
        节省每次请求的 ~3s 初始化时间
        """
        # 优先返回实例级缓存（向后兼容）
        if self._agent is not None:
            return self._agent

        # 类级别单例缓存
        cache_key = (type(self), self.model)
        if cache_key in self._agent_instance_cache:
            self._agent = self._agent_instance_cache[cache_key]
            logger.debug(
                "[v2_agent:%s] reused class-singleton agent (model=%s)",
                self.name,
                self.model,
            )
            # 阶段14 监控
            try:
                from .monitoring import record_agent_reuse
                record_agent_reuse()
            except ImportError:
                pass
            return self._agent

        runtime = get_runtime()
        if not runtime.available:
            return None

        # 延迟导入 LangChain 1.x（确保失败时不阻塞）
        from langchain.agents import create_agent
        from langchain.chat_models import init_chat_model

        self._tools = self.get_tools()
        checkpointer = await runtime.get_checkpointer()

        # 阶段48-14: 构造 chat_model 实例 (用于中间件 + create_agent)
        chat_model = self._build_chat_model()

        # 阶段48-14: middlewares 需要 chat_model 实例 (SummarizationMiddleware 用 model 做 summary)
        middlewares = runtime.get_middlewares(self.model, chat_model=chat_model, agent_name=self.name)

        # DeepSeek / 自定义 endpoint：用 ChatOpenAI + base_url
        # DeepSeek 兼容 OpenAI 协议，不需要 langchain-deepseek 单独包
        if chat_model is not None:
            agent = create_agent(
                model=chat_model,
                tools=self._tools,
                system_prompt=self.system_prompt,
                middleware=middlewares,
                checkpointer=checkpointer,
            )
        else:
            # 未知模型: 直接传字符串
            agent = create_agent(
                model=self.model,
                tools=self._tools,
                system_prompt=self.system_prompt,
                middleware=middlewares,
                checkpointer=checkpointer,
            )

        # 缓存到类级别
        self._agent_instance_cache[cache_key] = agent
        self._agent = agent

        # 阶段14 监控
        try:
            from .monitoring import record_agent_new
            record_agent_new()
        except ImportError:
            pass

        logger.info(
            "[v2_agent:%s] created (singleton): model=%s, tools=%d, middlewares=%d",
            self.name,
            self.model,
            len(self._tools),
            len(middlewares),
        )
        return agent

    async def resume(
        self,
        thread_id: str,
        decisions: list[dict],
        session_id: str,
        user_id: str | None = None,
        user_parts: list | None = None,
    ) -> AsyncIterable[dict[str, Any]]:
        """阶段48-16: 阶段 HITL 中断后, 用 decisions 接着跑.

        Args:
            thread_id: graph thread_id (例如 '{user_id}:{session_id}')
            decisions: list of {"type": "approve"|"edit"|"reject"|"respond", "args": ..., "message": ...}
            session_id: v2 chat session (为了 yield 同 stream 一致的事件)
            user_id: 用户 id
            user_parts: tool call payload

        Yields:
            同 stream() 一致, 可继续吐 chunk, 并在再 interrupt 时再次 yield
        """
        import time as _time
        _stream_start = _time.time()
        _stream_error = False

        agent = await self._ensure_agent()
        if agent is None:
            yield {"type": "error", "content": "agent 未初始化"}
            return

        try:
            from langchain_core.messages import HumanMessage
            from .mcp_tool_adapter import set_user_context
            if user_id:
                set_user_context(user_id=user_id, conversation_id=session_id or "")
                import os as _os
                _os.environ["PHA_USER_ID"] = user_id

            cfg = {"configurable": {"thread_id": thread_id}}

            from langgraph.types import Command
            # 调用 ainvoke 时传 Command(resume=decisions)
            result = await agent.ainvoke(
                Command(resume={"decisions": decisions}),
                config=cfg,
                stream_mode="values",
            )
            # result 是最后一帧 state dict
            msgs = result.get("messages", []) if isinstance(result, dict) else []
            # 找到 last AI message
            from langchain_core.messages import AIMessage
            last_ai = None
            for msg in reversed(msgs):
                if isinstance(msg, AIMessage):
                    last_ai = msg
                    break
            if last_ai and last_ai.content:
                txt = str(last_ai.content)
                # 模拟流式 chunk
                for i in range(0, len(txt), 8):
                    yield {"type": "normal", "content": txt[i:i+8]}

            # 再检查 interrupt (级联)
            last_state = await agent.aget_state(cfg)
            interrupts = (
                last_state.values.get("__interrupt__", [])
                if hasattr(last_state, "values") and isinstance(last_state.values, dict)
                else []
            )
            if interrupts:
                intr = interrupts[0]
                intr_value = getattr(intr, "value", intr)
                yield {
                    "type": "interrupt",
                    "thread_id": thread_id,
                    "interrupt_data": intr_value if isinstance(intr_value, (list, dict)) else {"raw": str(intr_value)},
                }

            yield {"type": "complete", "content": " ", "thread_id": thread_id}
        except Exception as e:
            logger.exception("[v2_agent:%s] resume error", self.name)
            yield {
                "type": "error",
                "content": f"resume 失败: {e}",
                "require_user_input": False,
            }

    async def stream(
        self,
        query: str,
        session_id: str,
        user_id: str | None = None,
        user_parts: list | None = None,
    ) -> AsyncIterable[dict[str, Any]]:
        """
        流式推理（与 BasicAgent.stream 保持相同事件格式）

        输出事件类型：
        - {"type": "status", "content": "Processing request..."}
        - {"type": "reasoning", "content": "..."}
        - {"type": "normal", "content": "..."}
        - {"type": "tool_call", "name": "...", "args": {...}}
        - {"type": "tool_result", "name": "...", "output": "..."}
        - {"type": "complete", "content": " "}
        - {"type": "error", "content": "...", "require_user_input": True}
        """
        # 阶段14 监控：记录端到端延迟
        import time as _time
        _stream_start = _time.time()
        _stream_error = False

        agent = await self._ensure_agent()
        if agent is None:
            yield {
                "type": "error",
                "content": "LangChain 1.x 不可用，V2Agent 已降级。请安装 langchain>=1.2.10",
                "require_user_input": True,
            }
            return

        # 起始事件（与 BasicAgent 兼容）
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "updates": "Processing request...",
        }

        # thread_id = user_id:session_id（隔离多用户多会话）
        thread_id = f"{user_id or 'anon'}:{session_id}"
        cfg = {"configurable": {"thread_id": thread_id}}

        # 阶段12 限流检查
        if os.getenv("PHA_RATE_LIMIT", "true").lower() in {"true", "1", "yes", "on"}:
            try:
                from .rate_limit import get_rate_limiter, RateLimitError
                limiter = get_rate_limiter()
                _rl = await limiter.allow_llm_call(user_id=user_id, agent_name=self.name)
                if not _rl:
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": "请求过于频繁，请稍后再试。",
                        "type": "error",
                        "rate_limited": True,
                    }
                    return
            except ImportError:
                pass

        try:
            # 阶段48-13: set user_id context so MCP tools 自动注入
            try:
                from .mcp_tool_adapter import set_user_context
                set_user_context(user_id=user_id or "", conversation_id=session_id or "")
                # 阶段48-13: 同时存到 os.environ (process-level, 跨 asyncio task)
                if user_id:
                    os.environ["PHA_USER_ID"] = user_id
            except Exception:
                pass

            # 阶段48-12: stream_mode 改为 "messages" — 增量 yield, 不再传累积 state
            # + recursion_limit 防无限循环
            # + 去重 dedup_set 防止反复 yield 同 message id 的 tool_call
            import time as _t
            _stream_start = _t.time()
            _MAX_ITER = int(os.getenv("PHA_MAX_TOOL_ITER", "6"))  # 阶段48-12
            _MAX_STREAM_SEC = int(os.getenv("PHA_MAX_STREAM_SEC", "45"))

            # 阶段48-12: 用 messages 模式 (LangGraph 0.3+), 每个 chunk 是一个增量 message
            try:
                stream_iter = agent.astream(
                    {"messages": [{"role": "user", "content": query}]},
                    config={**cfg, "recursion_limit": 100},
                    stream_mode="messages",
                )
                logger.debug(f"[v2_agent:trace] USING messages mode, recursion_limit=100")
                using_messages_mode = True
            except Exception as _e_mode:
                logger.warning(f"[v2_agent] stream_mode=messages 失败, 退回 values + 去重: {_e_mode}")
                stream_iter = agent.astream(
                    {"messages": [{"role": "user", "content": query}]},
                    config={**cfg, "recursion_limit": 100},
                    stream_mode="values",
                )
                using_messages_mode = False

            # 阶段48-12: 去重 + 累加器
            # - seen_tool_calls: 去重 tool_call (避免同 tc_id 多次 yield)
            # - seen_ai_accumulators: 同 msg_id 累加, yield 增量
            seen_tool_calls = set()
            seen_ai_accumulators = {}  # {msg_id: accumulated_content_so_far}
            seen_tc_accumulators = {}  # {tool_id: accumulated_args_str} 阶段48-12
            iter_count = 0

            async for chunk in stream_iter:
                iter_count += 1
                # 超时保护
                if _t.time() - _stream_start > _MAX_STREAM_SEC:
                    logger.error("[v2_agent] stream 超时 (%.1fs), 强制结束", _t.time() - _stream_start)
                    yield {"is_task_complete": True, "require_user_input": False, "content": "响应超时, 请稍后重试。", "type": "normal"}
                    return

                if using_messages_mode:
                    # messages 模式: chunk 是 (msg, _metadata) 元组, 或者是单 msg
                    # 阶段48-12 debug: 加日志看 chunk 类型
                    if isinstance(chunk, tuple):
                        msg = chunk[0]
                    else:
                        msg = chunk
                    messages = [msg]
                else:
                    # values 模式: chunk 是完整 state (累积 messages)
                    messages = chunk.get("messages", []) if isinstance(chunk, dict) else []

                # debug 关掉
                pass

                for msg in messages:
                    msg_id = getattr(msg, "id", None) or getattr(msg, "message_id", None) or ""
                    msg_type = getattr(msg, "type", "ai")
                    content = getattr(msg, "content", "")
                    tool_calls = getattr(msg, "tool_calls", []) or []

                    # 阶段48-12 重写: chunk 是 AIMessageChunk 增量, 同 msg_id 的多个 chunk 共享 run id
                    # 累积: 对每 msg_id 累加 content (str concat), 持续 yield 增量 (diff)
                    # 不要 in-place dedup — 让 UI 看到完整流

                    # 工具调用 — 按 (tool_call_id) 去重, 第一次 yield 时累加完整 args
                    seen_tc_args: dict = getattr(msg, "_seen_tc_args", None)  # placeholder noop
                    for tc in tool_calls:
                        tc_id = tc.get("id") or ""
                        tc_name = tc.get("name", "") or ""
                        tc_args_raw = tc.get("args", "")

                        # 阶段48-12: 累加 args (LLM 模型 chunk 输出 args 是 string 累加)
                        # 跨 chunks 累加到 full_args
                        if isinstance(tc_args_raw, str):
                            prev_args = seen_tc_accumulators.get(tc_id or tc_name, "")
                            if tc_args_raw.startswith(prev_args) or tc_args_raw and not prev_args:
                                seen_tc_accumulators[tc_id or tc_name] = tc_args_raw
                                full_args_str = tc_args_raw
                            else:
                                seen_tc_accumulators[tc_id or tc_name] = prev_args + tc_args_raw
                                full_args_str = prev_args + tc_args_raw
                            # 解析为 dict
                            try:
                                tc_args_parsed = json.loads(full_args_str) if full_args_str.strip() else {}
                            except json.JSONDecodeError:
                                tc_args_parsed = {"_raw": full_args_str}
                        else:
                            tc_args_parsed = tc_args_raw
                            full_args_str = json.dumps(tc_args_raw, ensure_ascii=False)

                        # 阶段48-12: 等到 args 看起来完整才 yield (含 '}' 或完整关键词)
                        # 简化: chunk 都没 id 时直接 yield; 但有 id 时等到 full content
                        if not tc_id:
                            sig_key = ("tc_sig", tc_name, full_args_str)
                            if sig_key in seen_tool_calls:
                                continue
                            seen_tool_calls.add(sig_key)
                            yield {
                                "type": "tool_call",
                                "id": tc_id,
                                "name": tc_name,
                                "args": tc_args_parsed if tc_args_parsed else {"_raw": full_args_str},
                            }
                        else:
                            # 用 tc_id 跟踪 — 但只在 iter 看到完整 args 才 yield
                            sig_key = ("tc_id", tc_id)
                            if sig_key in seen_tool_calls:
                                continue
                            # 只在 args 看起来完整 (含 '}' 或看到 args dict) 触发 yield
                            if isinstance(tc.get("args"), dict):
                                seen_tool_calls.add(sig_key)
                                yield {
                                    "type": "tool_call",
                                    "id": tc_id,
                                    "name": tc_name,
                                    "args": tc_args_parsed,
                                }
                            else:
                                # 字符串 chunk, 继续累加, 暂不 yield
                                continue

                    # ai 文本 — 直接 yield
                    # chunk.content 已是该 chunk 的有效 token (LangChain 不会累加)
                    if msg_type == "ai" and content:
                        yield {
                            "is_task_complete": False,
                            "require_user_input": False,
                            "content": content,
                            "type": "normal",
                        }
                    elif msg_type == "tool" and content:
                        # tool result 用 (msg_id) 唯一
                        tool_name = getattr(msg, "name", "")
                        tr_key = ("tr", msg_id, tool_name)
                        if tr_key in seen_tool_calls:
                            continue
                        seen_tool_calls.add(tr_key)
                        yield {
                            "type": "tool_result",
                            "name": tool_name,
                            "output": str(content)[:500],
                        }

            # 结束事件
            # 阶段48-16: 检测 HITL interrupt, 让前端弹出确认 dialog
            # 检查 graph state 的 __interrupt__ 值
            try:
                # 用 aget_state 获取最新 state (包括被 interrupt 触发 pending 的)
                last_state = await agent.aget_state(cfg)
                interrupts = []
                # 多种 interrupt sources
                state_dict = (
                    last_state.values if hasattr(last_state, "values") and isinstance(last_state.values, dict)
                    else (last_state if isinstance(last_state, dict) else {})
                )
                if "__interrupt__" in state_dict and state_dict["__interrupt__"]:
                    interrupts = state_dict["__interrupt__"]
                elif hasattr(last_state, "tasks") and last_state.tasks:
                    # 待处理任务中可能有 interrupt
                    for task in last_state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            interrupts.extend(task.interrupts)

                if interrupts:
                    intr = interrupts[0]
                    if hasattr(intr, "value"):
                        intr_value = intr.value
                    elif isinstance(intr, dict):
                        intr_value = intr.get("value", intr)
                    else:
                        intr_value = str(intr)
                    logger.info("[v2_agent:%s] HITL interrupt detected: thread=%s", self.name, thread_id)
                    yield {
                        "type": "interrupt",
                        "thread_id": thread_id,
                        "interrupt_data": intr_value if isinstance(intr_value, (list, dict)) else {"raw": str(intr_value)},
                    }
            except Exception as e:
                logger.debug("[v2_agent:%s] interrupt detect error: %s", self.name, e)

            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": " ",
                "type": "normal",
            }

        except Exception as e:
            logger.exception("[v2_agent:%s] stream error", self.name)
            _stream_error = True
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "updates": f"Error processing request: {str(e)}",
            }
        finally:
            # 阶段14 监控：保证 stream 退出时记录
            try:
                from .monitoring import record_request
                record_request(_time.time() - _stream_start, error=_stream_error)
            except ImportError:
                pass
