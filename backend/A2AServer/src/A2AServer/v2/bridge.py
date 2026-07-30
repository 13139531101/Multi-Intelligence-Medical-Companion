"""
PHA v2 桥接器（阶段4）

**作用**：把 A2A Message 转换为 v2 HostGraph 输入，调用 route_and_invoke，
把 v2 final_response 转换回 A2A Message 格式返回。

**协议兼容**：
- 输入：A2A JSON-RPC 2.0 Message（Pydantic）
- 输出：同样的 Message（v2 final_response.content -> Message.parts[0].text）

**降级机制**：
- LangChain 1.x 不可用 → 返回错误但不让 v1 路径阻塞
- v2 路由失败 → 自动 fallback 到 v1 adk_host_manager
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional, AsyncIterator

logger = logging.getLogger(__name__)


# 阶段48-13: LLM 总结工具结果
async def _llm_summarize_tool_results(
    query: str,
    tool_calls: list,
    tool_results: list,
    agent_name: str,
    *,
    timeout: float = 15.0,
) -> str:
    """阶段48-13: 直接调一次 LLM, 拿到工具结果后让它生成自然语言回答.

    用 ChatOpenAI + LangChain, 不走 agent loop.
    模型: PHA_SUMMARIZE_MODEL 环境变量, 默认 deepseek-chat.
    """
    if not tool_results:
        return ""

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
    except ImportError:
        logger.warning("[v2_bridge] langchain_openai 不可用, 跳过 summarize")
        return ""

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[v2_bridge] 无 API key, 跳过 summarize")
        return ""

    model_name = os.getenv("PHA_SUMMARIZE_MODEL", "deepseek-chat")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    try:
        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.3,
        )

        # 把工具结果整理
        tools_blob = []
        for tc, tr in zip(tool_calls, tool_results):
            output = str(tr.get("output", ""))[:800]
            tools_blob.append(f"**{tr.get('name', tc.get('name', '?'))}** 返回: {output}")
        tools_text = "\n\n".join(tools_blob) if tools_blob else "(无工具调用)"

        system_prompt = (
            "你是 PHA (Personal Health Assistant) 智能体的回复生成助手。"
            "用户的查询已经触发了一些工具调用, 工具结果已在上方。"
            "请用自然、亲切、简短的健康顾问语气总结这些工具结果,"
            "用 markdown 格式输出, 不要直接复制工具的 JSON 字段名, "
            "要让用户能直接读懂。不要瞎编数据, 严格按照工具返回的事实。"
        )

        user_msg = (
            f"用户问题: {query}\n\n"
            f"工具调用结果:\n{tools_text}\n\n"
            "请生成自然语言总结。"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ]

        # 用 asyncio.wait_for 包超时
        coro = llm.ainvoke(messages)
        result = await asyncio.wait_for(coro, timeout=timeout)
        summary = result.content if hasattr(result, "content") else str(result)
        summary = (summary or "").strip()
        if summary:
            logger.info(f"[v2_bridge] LLM 总结完成 (len={len(summary)})")
        return summary
    except asyncio.TimeoutError:
        logger.warning(f"[v2_bridge] LLM 总结超时 ({timeout}s)")
        return ""
    except Exception as e:
        logger.exception(f"[v2_bridge] LLM 总结异常: {e}")
        return ""

# ---- PHA v2 路径配置 ----
# 阶段27 修复：兼容容器浅路径（parents[5] 在 /app/A2AServer/v2/ 下越界）
_PHA_BACKEND = None
try:
    # 本机路径: .../A2AServer/v2/bridge.py → parents[5] 是项目根
    _candidate = Path(__file__).resolve().parents[5]
    if (_candidate / "backend" / "A2AServer" / "src").exists():
        _PHA_BACKEND = _candidate
except IndexError:
    pass

# 容器路径: /app/A2AServer/v2/bridge.py → parents[3] 是 /app，尝试更高
if _PHA_BACKEND is None:
    for n in [3, 2, 4, 5, 6]:
        try:
            cand = Path(__file__).resolve().parents[n]
            if (cand / "A2AServer").exists() and (cand / "A2AServer" / "v2" / "bridge.py").exists():
                _PHA_BACKEND = cand
                break
        except IndexError:
            continue

# 最后 fallback：尝试环境变量 PHA_PROJECT_ROOT，否则当前文件目录上溯到含 A2AServer 的
if _PHA_BACKEND is None:
    env_root = os.getenv("PHA_PROJECT_ROOT")
    if env_root:
        _PHA_BACKEND = Path(env_root)

if _PHA_BACKEND is None:
    logger.warning("[bridge] 无法定位 PHA 项目根，路径配置跳过")

if _PHA_BACKEND is not None:
    _backend_src = str(_PHA_BACKEND / "backend" / "A2AServer" / "src") if (_PHA_BACKEND / "backend").exists() else str(_PHA_BACKEND / "src") if (_PHA_BACKEND / "src").exists() else None
    if _backend_src:
        if _backend_src not in sys.path:
            sys.path.insert(0, _backend_src)
    logger.info(f"[bridge] PHA_BACKEND = {_PHA_BACKEND}")


def is_v2_enabled() -> bool:
    """
    v2 路径是否启用（环境变量控制）

    阶段27 改动：默认开启 v2。
    - 旧：PHA_USE_V2=false 默认 → 走 v1 ADK
    - 新：PHA_USE_V2=true 默认 → 走 v2 LangChain in-process（42 工具 + StateGraph）

    关闭方式：PHA_USE_V2=false（保留给 v1 兜底/回退）
    """
    return os.getenv("PHA_USE_V2", "true").lower() in {"true", "1", "yes", "on"}


def is_v2_request(request) -> bool:
    """
    根据 request header 判断是否走 v2 路径

    触发条件（任一）：
    1. Header `X-PHA-Version: v2`
    2. Header `X-Use-V2: true`
    3. 环境变量 `PHA_USE_V2=true`（全量切流）
    """
    try:
        if is_v2_enabled():
            return True
        if request is None:
            return False
        try:
            headers = request.headers
            if headers.get("x-pha-version", "").lower() == "v2":
                return True
            if headers.get("x-use-v2", "").lower() == "true":
                return True
        except Exception:
            pass
        return False
    except Exception as e:
        # 任何异常都默认走 v1（兜底）
        logger.warning(f"[bridge.is_v2_request] error: {type(e).__name__}: {e}, fallback False")
        return False


def _extract_text_from_message(message) -> str:
    """从 A2A Message 提取用户文本"""
    text = ""
    if hasattr(message, "parts") and message.parts:
        for p in message.parts:
            if hasattr(p, "text") and p.text:
                text += p.text
    return text


def _build_v2_message(
    content: str,
    conversation_id: str,
    *,
    agent: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """从 v2 final_response 构造 A2A Message"""
    try:
        from A2AServer.common.A2Atypes import Message, Part, TextPart

        msg_metadata = dict(metadata or {})
        msg_metadata.setdefault("conversation_id", conversation_id)
        if agent:
            msg_metadata.setdefault("agent", agent)
            msg_metadata.setdefault("selected_agent", agent)
        msg_metadata.setdefault("source", "pha-v2-host-graph")

        return Message(
            role="agent",
            parts=[TextPart(text=content or " ")],
            metadata=msg_metadata,
        )
    except Exception as e:
        logger.error("[v2_bridge] 构造 Message 失败: %s", e)
        return None


async def v2_process_message(message) -> dict:
    """
    v2 主处理函数：调用 HostGraph 返回结果

    Returns:
        dict: {message: A2A Message | None, error: str | None, used_v2: True}
    """
    try:
        from A2AServer.v2 import route_and_invoke
    except ImportError as e:
        logger.error("[v2_bridge] 导入 v2 失败: %s", e)
        return {"message": None, "error": f"v2 import failed: {e}", "used_v2": True}

    # 提取输入
    query = _extract_text_from_message(message)
    if not query:
        return {"message": None, "error": "empty query", "used_v2": True}

    # 提取 metadata
    metadata = getattr(message, "metadata", None) or {}
    conversation_id = (
        metadata.get("conversation_id")
        or getattr(message, "conversation_id", None)
        or "default"
    )
    user_id = (
        metadata.get("user_id")
        or os.getenv("A2A_CURRENT_USER_ID")
        or os.getenv("USER_ID")
        or "default_user"
    )

    # 调 HostGraph
    try:
        # 阶段30：multi 模式开关（默认 single 向后兼容）
        # 触发条件：
        # 1. metadata 里 "v2_mode" = "multi" 或
        # 2. 环境变量 PHA_V2_MODE = "multi" 或
        # 3. query 包含 [multi] 前缀（测试用）
        v2_mode = "single"
        parallel_agents = None
        if isinstance(metadata, dict):
            v2_mode = metadata.get("v2_mode", v2_mode)
            pa = metadata.get("parallel_agents")
            if isinstance(pa, list):
                parallel_agents = pa
        if os.getenv("PHA_V2_MODE", "").lower() == "multi":
            v2_mode = "multi"
        if query.startswith("[multi]"):
            v2_mode = "multi"
            query = query[len("[multi]"):].strip()
        if query.startswith("[multi:"):
            # 语法: [multi:health_advisor,medication_reminder]
            import re
            m = re.match(r"\[multi:([^\]]+)\]", query)
            if m:
                v2_mode = "multi"
                parallel_agents = [x.strip() for x in m.group(1).split(",") if x.strip()]
                query = query[m.end():].strip()

        result = await route_and_invoke(
            query=query,
            conversation_id=conversation_id,
            user_id=str(user_id),
            metadata=dict(metadata),
            mode=v2_mode,
            parallel_agents=parallel_agents,
        )
    except Exception as e:
        logger.exception("[v2_bridge] route_and_invoke 失败")
        return {"message": None, "error": str(e), "used_v2": True}

    # 构造返回 Message
    agent = result.get("agent", "unknown")
    content = result.get("content", "")
    msg = _build_v2_message(
        content=content,
        conversation_id=conversation_id,
        agent=agent,
        metadata={
            **metadata,
            "v2_routing": result.get("routing", {}),
            "v2_tool_calls": result.get("tool_calls", []),
            "v2_error": result.get("error", False),
        },
    )

    if msg is None:
        return {"message": None, "error": "build message failed", "used_v2": True}

    return {"message": msg, "error": None, "used_v2": True, "result": result}


async def v2_process_message_stream(message) -> AsyncIterator[dict]:
    """
    阶段48-11: v2 流式处理 — 真流式 yield 事件

    跟 v2_process_message 不同:
    - 不等所有都做完一次性返回
    - 实时 yield:
        - {"event": "routing", "agent": ..., "routing": {...}}
        - {"event": "tool_call", "name": ..., "args": {...}}
        - {"event": "tool_result", "name": ..., "output": ...}
        - {"event": "chunk", "text": ...}
        - {"event": "done", "content": ..., "agent": ...}

    Args:
        message: A2A Message

    Yields:
        dict: 事件对象
    """
    from A2AServer.v2 import agent_registry

    query = _extract_text_from_message(message)
    if not query:
        yield {"event": "error", "error": "empty query"}
        return

    metadata = getattr(message, "metadata", None) or {}
    conversation_id = (
        metadata.get("conversation_id")
        or getattr(message, "conversation_id", None)
        or f"stream_{uuid.uuid4().hex[:8]}"
    )
    user_id = (
        metadata.get("user_id")
        or os.getenv("A2A_CURRENT_USER_ID")
        or os.getenv("USER_ID")
        or "default_user"
    )

    # 解析 metadata 参数
    v2_mode = metadata.get("v2_mode", "single")
    selected_agent = metadata.get("selected_agent")
    parallel_agents = None
    if isinstance(metadata.get("parallel_agents"), list):
        parallel_agents = metadata["parallel_agents"]

    # Phase 1: 路由 + 锁定目标
    target_agent = None

    # Layer 1: metadata.selected_agent (锁定)
    if selected_agent:
        try:
            from A2AServer.v2.agent_registry import AgentRegistry
            spec = AgentRegistry.get(selected_agent) or AgentRegistry.by_alias(selected_agent)
            if spec is not None:
                target_agent = spec.name
        except Exception:
            pass

    # Layer 2: 关键词启发 (keyword matching)
    if not target_agent:
        try:
            from . import host_graph
            # 调用 layer2 函数
            HostState = host_graph.HostState
            fake_state = HostState(
                query=query, conversation_id=conversation_id, user_id=user_id,
                metadata=metadata, events=[],
            )
            routed = host_graph._layer2_heuristic(fake_state)
            if routed:
                target_agent = routed
        except Exception as e:
            logger.debug("[v2_stream] layer2 failed: %s", e)

    # Layer 3: LLM fallback (省略 — 走 v1 HostGraph 一样)

    # 阶段48-20: fallback agent 从 DomainManifest 读, 不再硬编码 health_advisor
    if not target_agent:
        try:
            from .domain_manifest import load_default
            target_agent = load_default().host_agent_name
        except Exception:
            target_agent = "health_advisor"  # legacy

    # 阶段48-11 push routing 事件
    yield {
        "event": "routing",
        "agent": target_agent,
        "routing": {"layer": 1 if selected_agent else 2, "target": target_agent},
        "conversation_id": conversation_id,
    }

    # Phase 2: 真流式调用 agent.stream
    try:
        from .agent_registry import AgentRegistry
        from .v2_runtime import get_runtime

        spec = AgentRegistry.get(target_agent)
        if spec is None or spec.cls is None:
            yield {"event": "error", "error": f"unknown agent: {target_agent}"}
            return

        if not get_runtime().available:
            yield {"event": "error", "error": "LangChain 不可用"}
            return

        agent = spec.cls()
        text = ""
        tool_calls_log = []
        tool_results_log = []

        # 阶段48-12: 最大 stream 时间和最大 yield 次数限制, 防 LangGraph 死循环
        import time as _t
        _stream_started = _t.time()
        _MAX_SEC = int(os.getenv("PHA_MAX_STREAM_SEC", "60"))  # 阶段48-27: 增加超时让 A2A 工具调用有足够时间
        _MAX_YIELDS = int(os.getenv("PHA_MAX_STREAM_YIELDS", "300"))

        yield_count = 0
        async for ev in agent.stream(
            query,
            conversation_id,
            user_id=user_id,
        ):
            yield_count += 1
            # 阶段48-12: 防卡死, 超时强制结束
            if _t.time() - _stream_started > _MAX_SEC:
                logger.warning(f"[v2_bridge] stream 超 {_MAX_SEC}s, 强制结束")
                if not text and tool_results_log:
                    text = "## 工具调用结果汇总\n\n" + "\n".join([
                        f"**{r['name']}**: {str(r['output'])[:300]}" for r in tool_results_log
                    ])
                yield {"event": "chunk", "text": "\n\n_(响应超时, 已汇总工具结果)_"}
                break
            if yield_count > _MAX_YIELDS:
                logger.warning(f"[v2_bridge] yields 超 {_MAX_YIELDS}, 强制结束")
                if not text and tool_results_log:
                    text = "## 工具调用结果汇总\n\n" + "\n".join([
                        f"**{r['name']}**: {str(r['output'])[:300]}" for r in tool_results_log
                    ])
                yield {"event": "chunk", "text": "\n\n_(轮次过多, 已汇总工具结果)_"}
                break

            ev_type = ev.get("type", "?")
            if ev_type == "tool_call":
                tool_calls_log.append({"name": ev.get("name"), "args": ev.get("args")})
                yield {
                    "event": "tool_call",
                    "name": ev.get("name"),
                    "args": ev.get("args"),
                }
            elif ev_type == "tool_result":
                tool_results_log.append({
                    "name": ev.get("name"),
                    "output": ev.get("output"),
                })
                yield {
                    "event": "tool_result",
                    "name": ev.get("name"),
                    "output": ev.get("output"),
                }
            elif ev_type == "interrupt":
                # 阶段48-16: HITL 中断 → emit interrupt SSE, 前端弹 confirm dialog
                yield {
                    "event": "interrupt",
                    "thread_id": ev.get("thread_id"),
                    "interrupt_data": ev.get("interrupt_data"),
                }
            elif ev_type == "normal":
                content = ev.get("content", "")
                if content and content.strip():
                    text += str(content)
                    yield {"event": "chunk", "text": str(content)}

        # 阶段48-13: 如果 LLM 没给最终文本, 自动调一次 LLM 总结工具结果
        # 而不是直接 dump JSON 给用户
        if not text and tool_results_log:
            logger.info(f"[v2_bridge] LLM 没出最终回答, 自动调 LLM 总结工具结果 (agent={target_agent})")
            try:
                summary_text = await _llm_summarize_tool_results(
                    query=query,
                    tool_calls=tool_calls_log,
                    tool_results=tool_results_log,
                    agent_name=target_agent,
                )
                if summary_text:
                    text = summary_text
                    # 阶段48-13: 模拟流式 chunk 让前端能逐字看到
                    for i in range(0, len(summary_text), 8):
                        chunk = summary_text[i:i+8]
                        yield {"event": "chunk", "text": chunk}
                        # 不要 await sleep — 应该立刻 yield 所有, 不让 UI 等太久
                else:
                    # 阶段48-13: LLM summarize 也失败, 才用最简 fallback
                    text = "工具调用未返回内容。"
                    yield {"event": "chunk", "text": text}
            except Exception as e:
                logger.exception(f"[v2_bridge] llm_summarize 失败: {e}")
                text = "工具调用未返回内容。"
                yield {"event": "chunk", "text": text}

        # done
        yield {
            "event": "done",
            "content": text,
            "agent": target_agent,
            "tool_calls": tool_calls_log,
            "tool_results": tool_results_log,
            "conversation_id": conversation_id,
        }

        # 阶段48-27: 如果工具返回了 page_update 指令，生成 PAGE_UPDATE 事件
        for tr in tool_results_log:
            output = tr.get("output")
            # 解析 JSON 字符串
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(output, dict) and output.get("page_update"):
                pu = output["page_update"]
                yield {
                    "event": "page_update",
                    "component": pu.get("component", "page"),
                    "action": pu.get("action", "setData"),
                    "params": pu.get("params", {}),
                    "summary": pu.get("summary", ""),
                }
            # 也支持直接返回 page_update 字段的结构
            elif isinstance(output, dict) and output.get("component") and output.get("action"):
                yield {
                    "event": "page_update",
                    "component": output.get("component"),
                    "action": output.get("action"),
                    "params": output.get("params", {}),
                    "summary": output.get("summary", ""),
                }
    except Exception as e:
        logger.exception("[v2_bridge] stream error")
        yield {"event": "error", "error": str(e)}


async def v2_process_message_resume(
    thread_id: str,
    decisions: list[dict],
    conversation_id: str,
    user_id: str | None = None,
    target_agent: str = "auto",
):
    """阶段48-16: 用户确认 (approve/reject) 后, 接着跑被 interrupted 的 graph.

    Args:
        thread_id: 之前 yield 的 thread_id
        decisions: 用户对每个 tool_call 的决策
            e.g. [{"type": "approve"}, {"type": "reject", "message": "..."}, ...]
        conversation_id: 同样 for thread_id
        user_id: PHA 用户 ID
        target_agent: 同 stream

    Yields:
        SSE 事件, 同 v2_process_message_stream
    """
    try:
        from .agent_registry import AgentRegistry
        # 阶段48-20: fallback agent 从 DomainManifest 读
        if target_agent == "auto" or not target_agent:
            try:
                from .domain_manifest import load_default
                target_agent = load_default().host_agent_name
            except Exception:
                target_agent = "health_advisor"  # legacy
        spec = AgentRegistry.get(target_agent)
        if spec is None or spec.cls is None:
            yield {"event": "error", "error": f"unknown agent: {target_agent}"}
            return

        agent = spec.cls()
        async for ev in agent.resume(
            thread_id=thread_id,
            decisions=decisions,
            session_id=conversation_id,
            user_id=user_id,
        ):
            ev_type = ev.get("type", "?")
            if ev_type == "tool_call":
                yield {"event": "tool_call", "name": ev.get("name"), "args": ev.get("args")}
            elif ev_type == "tool_result":
                yield {"event": "tool_result", "name": ev.get("name"), "output": ev.get("output")}
            elif ev_type == "interrupt":
                yield {"event": "interrupt", "thread_id": ev.get("thread_id"), "interrupt_data": ev.get("interrupt_data")}
            elif ev_type == "normal":
                yield {"event": "chunk", "text": ev.get("content", "")}
            elif ev_type == "complete":
                yield {"event": "done", "thread_id": ev.get("thread_id")}
            elif ev_type == "error":
                yield {"event": "error", "error": ev.get("content")}
    except Exception as e:
        logger.exception("[v2_bridge] resume error")
        yield {"event": "error", "error": str(e)}
