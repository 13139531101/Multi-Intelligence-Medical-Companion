"""
AG-UI ↔ /v2/chat/stream 翻译层.

CopilotKit 自带前端用 AG-UI SSE (TEXT_MESSAGE_CONTENT/TOOL_CALL_*/RUN_*).
我们后端走 /v2/chat/stream (routing/tool_call/tool_result/chunk/done).

这个 runtime 把后者翻成前者, 这样:
- 自写浮窗 (前端直接 fetch /api/copilotkit 拿 AG-UI) 也能工作
- CopilotKit 标准前端挂上也能工作 (虽然我们已经撤掉了)
"""
import json
import uuid
from typing import AsyncGenerator

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

# 同一进程的 /v2/chat/stream. 走 HTTP 而非内部 import — 解耦更好.
V2_CHAT_STREAM_URL = "http://localhost:13002/v2/chat/stream"


def _extract_user_message(messages: list) -> tuple[str, str]:
    """从 messages[] 拿最后一条 user 内容, 返回 (text, agent_hint)"""
    text = ""
    agent_hint = ""
    for m in messages or []:
        role = m.get("role") or m.get("type")
        if role in ("user", "human"):
            content = m.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            text = str(content)
        if m.get("agent"):
            agent_hint = m["agent"]
    return text, agent_hint


def _agui_event(event: str, data: dict) -> str:
    """AG-UI 格式: type 在 data 里. data: {...}\\n\\n"""
    payload = {**data, "type": event}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_agui(
    message: str, agent_hint: str, auth_header: str
) -> AsyncGenerator[str, None]:
    """调 /v2/chat/stream 把事件翻译成 AG-UI 流出去."""
    import asyncio

    run_id = str(uuid.uuid4())
    thread_id = "default"
    msg_id = str(uuid.uuid4())
    text_started = False
    tool_call_ids: dict = {}
    queue: asyncio.Queue = asyncio.Queue()

    async def pump():
        """从 /v2/chat/stream 读 SSE, 把事件塞 queue. 用 aiter_bytes + \\n\\n split."""
        payload = {"message": message}
        if agent_hint:
            payload["metadata"] = {"selected_agent": agent_hint}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                req = client.build_request(
                    "POST",
                    V2_CHAT_STREAM_URL,
                    json=payload,
                    headers={"Authorization": auth_header},
                )
                resp = await client.send(req, stream=True)
                # 修复: 此前从不检查状态码。401/403/500 的响应体是 JSON, 不含
                # 任何 "data:" 行 → 队列里只有 _eof_ → 前端只收到 RUN_STARTED +
                # RUN_FINISHED, 表现为"空回复且无任何报错"。
                if resp.status_code != 200:
                    _body = await resp.aread()
                    await resp.aclose()
                    _snippet = _body.decode("utf-8", errors="replace")[:300]
                    await queue.put({
                        "event": "error",
                        "error": (
                            f"上游 /v2/chat/stream 返回 HTTP {resp.status_code}: {_snippet}"
                        ),
                    })
                    await queue.put({"event": "_eof_"})
                    return
                try:
                    buf = ""
                    async for chunk in resp.aiter_bytes():
                        if not chunk:
                            continue
                        buf += chunk.decode("utf-8", errors="replace")
                        while "\n\n" in buf:
                            block, buf = buf.split("\n\n", 1)
                            event_type = None
                            data_str = None
                            for ln in block.split("\n"):
                                ln = ln.rstrip("\r")
                                if ln.startswith(":"):
                                    continue
                                if ln.startswith("event:"):
                                    event_type = ln[len("event:"):].strip()
                                elif ln.startswith("data:"):
                                    data_str = ln[len("data:"):].lstrip()
                            if data_str is None:
                                continue
                            try:
                                ev = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            if event_type:
                                ev["event"] = ev.get("event") or event_type
                            else:
                                ev["event"] = ev.get("event") or ev.get("type")
                            await queue.put(ev)
                    if buf.strip():
                        tail_event = None
                        for ln in buf.split("\n"):
                            ln = ln.rstrip("\r")
                            if ln.startswith("event:"):
                                tail_event = ln[len("event:"):].strip()
                            elif ln.startswith("data:"):
                                try:
                                    ev = json.loads(ln[len("data:"):].lstrip())
                                    ev["event"] = (
                                        ev.get("event") or tail_event or ev.get("type")
                                    )
                                    await queue.put(ev)
                                except json.JSONDecodeError:
                                    pass
                finally:
                    await resp.aclose()
            await queue.put({"event": "_eof_"})
        except Exception as e:
            import logging
            logging.exception(f"[copilotkit_runtime] pump exception: {e}")
            await queue.put({"event": "error", "message": f"pump exception: {e}"})
            await queue.put({"event": "_eof_"})

    pump_task = asyncio.create_task(pump())

    yield _agui_event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})

    while True:
        ev = await queue.get()
        kind = ev.get("event") or ev.get("type")
        if kind == "_eof_":
            break
        elif kind == "routing":
            # 修复: 此前 `continue` 直接吞掉, 前端 useChat.jsx 的 `case "routing"`
            # 永远不触发。透传 agent 名, 让前端能显示"由 XX 智能体处理"。
            yield _agui_event("routing", {
                "agent": ev.get("agent", ""),
                "routing": ev.get("routing", {}),
            })
        elif kind == "rag_context":
            # 阶段48-fix: bridge.v2_process_message_stream 在真正调 agent 之前会
            # 先跑 Magnetic RAG(多跳+KG扩展+rerank) 和 CRAG(纠错), 然后发这个事件。
            # 分发链此前无此分支 → 被静默丢弃, 前端完全看不到"这一轮到底检索到了
            # 什么、CRAG 有没有触发联网纠错"。透传出去让前端能显示检索徽标。
            yield _agui_event(
                "rag_context",
                {
                    "chunks": ev.get("chunks", 0),
                    "score": ev.get("score", 0.0),
                    "isRelevant": ev.get("is_relevant", False),
                    "cragAction": ev.get("crag_action", ""),
                    "sourceMix": ev.get("source_mix", ""),
                },
            )
        elif kind == "chunk":
            content = ev.get("text") or ev.get("content", "")
            if not content:
                continue
            if not text_started:
                yield _agui_event(
                    "TEXT_MESSAGE_START",
                    {"messageId": msg_id, "role": "assistant"},
                )
                text_started = True
            yield _agui_event(
                "TEXT_MESSAGE_CONTENT",
                {"messageId": msg_id, "delta": content},
            )
        elif kind == "tool_call":
            name = ev.get("name", "unknown")
            args = ev.get("args", {})
            tc_id = str(uuid.uuid4())
            tool_call_ids[name] = tc_id
            yield _agui_event(
                "TOOL_CALL_START",
                {
                    "toolCallId": tc_id,
                    "toolCallName": name,
                    "parentMessageId": msg_id,
                },
            )
            yield _agui_event(
                "TOOL_CALL_ARGS",
                {"toolCallId": tc_id, "delta": json.dumps(args, ensure_ascii=False)},
            )
        elif kind == "tool_result":
            name = ev.get("name", "")
            tc_id = tool_call_ids.get(name) or str(uuid.uuid4())
            yield _agui_event("TOOL_CALL_END", {"toolCallId": tc_id})
            # bridge 发送 output 字段，不是 result
            raw_output = ev.get("output") or ev.get("result")
            # 尝试解析 JSON 字符串
            result = raw_output
            if isinstance(raw_output, str):
                try:
                    result = json.loads(raw_output)
                except (json.JSONDecodeError, TypeError):
                    result = raw_output
            yield _agui_event(
                "TOOL_CALL_RESULT",
                {
                    "toolCallId": tc_id,
                    # 修复: 前端 useChat.jsx 用 toolCallName 匹配结果, 此前没发 →
                    # 工具结果永远挂不到 chip 上, UI 显示不出。
                    "toolCallName": name,
                    "content": json.dumps(result, ensure_ascii=False)
                    if not isinstance(result, str)
                    else result,
                },
            )
            # 注意: 这里**故意不再**从工具结果里推导 PAGE_UPDATE。
            #
            # bridge.v2_process_message_stream 在发完 done 之后, 会遍历同一份
            # tool_results_log 发一个语义化的 {"event":"page_update"} 事件（它覆盖
            # 的形状是这里的两倍: page_update 包裹式 和 component/action 直给式）。
            # 两处都发 → 同一次工具调用会产出**两个** PAGE_UPDATE → 前端对同一份
            # 数据执行两次 setData, 页面闪烁、弹窗重复。
            # 统一以 bridge 的 page_update 事件为唯一来源, 见下面的 kind == "page_update"。
        elif kind == "page_update":
            # 直接的 page_update 事件
            yield _agui_event(
                "PAGE_UPDATE",
                {
                    "component": ev.get("component", "page"),
                    "action": ev.get("action", "setData"),
                    "params": ev.get("params", {}),
                    "displaySummary": ev.get("summary", ""),
                },
            )
        elif kind == "clarification":
            # 修复: 此前无此分支 → 事件被静默丢弃。clarify 是 host_graph 的真实
            # 节点 (bridge.py 发 {"event":"clarification","question":...}) 且它
            # 不发 done, 所以用户只看到一条空回复, 澄清问题永远不显示。
            yield _agui_event("clarification", {
                "question": ev.get("question", ""),
                "reason": ev.get("reason", ""),
            })
        elif kind == "interrupt":
            # 修复: 同上, HITL 中断此前无分支 → 前端收不到确认请求。
            yield _agui_event("interrupt", {
                "thread_id": ev.get("thread_id"),
                "interrupt_data": ev.get("interrupt_data"),
            })
        elif kind == "done":
            if text_started:
                yield _agui_event("TEXT_MESSAGE_END", {"messageId": msg_id})
            # 修复: 此前遇 done 立即 break, 但 bridge.py 是「先发 done、再发
            # page_update」→ 尾部 page_update 永远读不到。改为不 break,
            # 继续 drain 队列直到 pump 放入的 _eof_。
            continue
        elif kind == "error":
            # 修复: bridge/api 发的是 {"error": ...}, 此前读 ev["message"] →
            # 永远落到兜底文案 "agent error", 真实错误丢失。
            yield _agui_event("RUN_ERROR", {
                "message": ev.get("error") or ev.get("message") or "agent error",
            })
            break

    try:
        await pump_task
    except Exception:
        pass

    yield _agui_event("RUN_FINISHED", {"runId": run_id, "threadId": thread_id})


async def copilotkit_endpoint(request: Request):
    """/api/copilotkit 入口.

    支持两种入参:
    1. CopilotKit RunAgentInput: { messages, thread_id, run_id, ... }
    2. 自写浮窗直接格式:       { message, agent_hint? }
    """
    # 修复: 非 UTF-8 / 非法 JSON 的请求体会让 request.json() 抛异常 → 整个
    # endpoint 500，前端只看到 "Internal Server Error" 且没有任何 AG-UI 事件。
    # 这里降级成一条正常的 AG-UI 错误流。
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        # 注意: Python 在 except 块结束时隐式 `del e`。而 bad_body_stream() 是
        # 生成器, 函数体要等到 StreamingResponse 真正迭代时才执行 —— 那时 e 早已
        # 被解绑, 直接 NameError, 于是"错误流"自己又崩了, 用户还是只看到空回复。
        # 所以必须在进入 except 块时就把消息取出来存成普通局部变量。
        _parse_err = str(e)

        async def bad_body_stream():
            run_id = str(uuid.uuid4())
            yield _agui_event("RUN_STARTED", {"runId": run_id, "threadId": "default"})
            yield _agui_event("RUN_ERROR", {"message": f"请求体解析失败: {_parse_err}"})
            yield _agui_event("RUN_FINISHED", {"runId": run_id, "threadId": "default"})

        return StreamingResponse(
            bad_body_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if not isinstance(body, dict):
        body = {}
    messages = body.get("messages") or []
    text, agent_hint = _extract_user_message(messages)
    if not text and "message" in body:
        text = body["message"]
    auth_header = request.headers.get("Authorization", "")

    if not text:
        async def empty_stream():
            run_id = str(uuid.uuid4())
            yield _agui_event(
                "RUN_STARTED",
                {"runId": run_id, "threadId": body.get("thread_id", "default")},
            )
            yield _agui_event(
                "RUN_FINISHED",
                {"runId": run_id, "threadId": body.get("thread_id", "default")},
            )

        return StreamingResponse(
            empty_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _stream_agui(text, agent_hint, auth_header),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream",
        },
    )
