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
            continue
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
            yield _agui_event("RUN_ERROR", {"message": ev.get("message", "agent error")})
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
    body = await request.json()
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
