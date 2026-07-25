"""
阶段48-25: CopilotKit runtime — 适配 CopilotKit 前端 ↔ 我们 /v2/chat/stream

CopilotKit 前端用 AG-UI 协议 (16 种 SSE 事件).
我们后端是 /v2/chat/stream (5 种事件: routing/tool_call/tool_result/chunk/done).

这个 runtime 是个薄翻译层:
  - 接收 CopilotKit RunAgentInput (含 messages[], thread_id, run_id)
  - 翻译成我们 /v2/chat/stream 入参
  - 把我们 SSE 流出的事件, 转成 AG-UI 标准事件再发出去

这样前端能用 CopilotKit (浮窗, generative UI, shared state),
后端不动 — 仍是 Python / LangGraph / DeepSeek.
"""
import json
import uuid
from typing import AsyncGenerator

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

# 我们 /v2/chat/stream 完整地址 (跟 hostapi 同进程, 直接调函数不走 HTTP 也行,
# 但走 HTTP 简单, 不用 import 内部 — 解耦更好)
V2_CHAT_STREAM_URL = "http://localhost:13002/v2/chat/stream"


def _extract_user_message(messages: list) -> tuple[str, str]:
    """从 CopilotKit messages[] 拿最后一条 user 内容, 返回 (text, agent_hint)"""
    text = ""
    agent_hint = ""
    for m in messages or []:
        role = m.get("role") or m.get("type")
        if role == "user" or role == "human":
            content = m.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    [c.get("text", "") if isinstance(c, dict) else str(c) for c in content]
                )
            text = str(content)
        if m.get("agent"):
            agent_hint = m["agent"]
    return text, agent_hint


def _agui_event(event: str, data: dict) -> str:
    """生成一行 AG-UI 协议 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_agui(message: str, agent_hint: str, auth_header: str) -> AsyncGenerator[str, None]:
    """
    内部: 调 /v2/chat/stream, 把 SSE 翻译成 AG-UI 事件

    阶段48-25 v2: 用 queue 收集, 然后 yield — 避免 async generator 在 httpx
    stream 上下文之外 yield 导致 stream 已关的问题.
    """
    import asyncio

    run_id = str(uuid.uuid4())
    thread_id = "default"
    msg_id = str(uuid.uuid4())
    text_started = False
    tool_call_ids = {}
    queue: asyncio.Queue = asyncio.Queue()

    async def pump():
        """调 /v2/chat/stream, 把事件塞进 queue.

        SSE 格式:
          event: <type>
          data: <json>
          \\n
        我们的 /v2/chat/stream 每条 SSE 是 event + data 两行 + 空行.
        需要 state machine 累积 (data 可能多行).
        """
        payload = {"message": message}
        if agent_hint:
            payload["metadata"] = {"selected_agent": agent_hint}
        try:
            import logging
            current_event_type = None
            current_data_lines = []
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    V2_CHAT_STREAM_URL,
                    json=payload,
                    headers={"Authorization": auth_header},
                ) as resp:
                    async for line in resp.aiter_lines():
                        # httpx iter_lines 会带 \\n, 去掉
                        line = line.rstrip("\r\n")
                        if line.startswith(":"):
                            # SSE 注释行, 跳过
                            continue
                        if line == "":
                            # 空行 = 一条 SSE 结束, 处理累积的 event/data
                            if current_event_type and current_data_lines:
                                data_str = "\n".join(current_data_lines).strip()
                                try:
                                    ev = json.loads(data_str)
                                    ev["event"] = ev.get("event") or current_event_type
                                    await queue.put(ev)
                                except json.JSONDecodeError:
                                    pass
                            current_event_type = None
                            current_data_lines = []
                            continue
                        if line.startswith("event:"):
                            current_event_type = line[len("event:"):].strip()
                        elif line.startswith("data:"):
                            current_data_lines.append(line[len("data:"):].lstrip())
                    # 处理尾部
                    if current_event_type and current_data_lines:
                        data_str = "\n".join(current_data_lines).strip()
                        try:
                            ev = json.loads(data_str)
                            ev["event"] = ev.get("event") or current_event_type
                            await queue.put(ev)
                        except json.JSONDecodeError:
                            pass
            await queue.put({"event": "_eof_"})
        except Exception as e:
            import logging
            logging.exception(f"[copilotkit_runtime] pump exception: {e}")
            await queue.put({"event": "error", "message": f"pump exception: {e}"})
            await queue.put({"event": "_eof_"})

    pump_task = asyncio.create_task(pump())

    # RUN_STARTED
    yield _agui_event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})

    while True:
        ev = await queue.get()
        kind = ev.get("event") or ev.get("type")
        if kind == "_eof_":
            break
        elif kind == "routing":
            continue
        elif kind == "chunk":
            content = ev.get("content", "")
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
                {"toolCallId": tc_id, "toolCallName": name, "parentMessageId": msg_id},
            )
            yield _agui_event(
                "TOOL_CALL_ARGS",
                {"toolCallId": tc_id, "delta": json.dumps(args, ensure_ascii=False)},
            )
        elif kind == "tool_result":
            name = ev.get("name", "")
            tc_id = tool_call_ids.get(name) or str(uuid.uuid4())
            yield _agui_event(
                "TOOL_CALL_END",
                {"toolCallId": tc_id},
            )
            result = ev.get("result")
            yield _agui_event(
                "TOOL_CALL_RESULT",
                {
                    "toolCallId": tc_id,
                    "content": json.dumps(result, ensure_ascii=False)
                    if not isinstance(result, str)
                    else result,
                },
            )
        elif kind == "done":
            if text_started:
                yield _agui_event("TEXT_MESSAGE_END", {"messageId": msg_id})
            break
        elif kind == "error":
            err_msg = ev.get("message", "agent error")
            yield _agui_event("RUN_ERROR", {"message": err_msg})
            break

    try:
        await pump_task
    except Exception:
        pass

    # RUN_FINISHED
    yield _agui_event("RUN_FINISHED", {"runId": run_id, "threadId": thread_id})


async def copilotkit_endpoint(request: Request):
    """
    阶段48-25: CopilotKit 入口端点.

    CopilotKit 前端会 POST 到这里, body 是 RunAgentInput:
      { thread_id, run_id, messages: [...], tools: [], state: {} }

    我们翻译后调 /v2/chat/stream, 再把结果翻译成 AG-UI SSE 返回.
    """
    body = await request.json()
    messages = body.get("messages") or []
    text, agent_hint = _extract_user_message(messages)
    auth_header = request.headers.get("Authorization", "")

    if not text:
        # 空消息直接返回
        async def empty_stream():
            run_id = str(uuid.uuid4())
            yield _agui_event("RUN_STARTED", {"runId": run_id, "threadId": body.get("thread_id", "default")})
            yield _agui_event("RUN_FINISHED", {"runId": run_id, "threadId": body.get("thread_id", "default")})

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