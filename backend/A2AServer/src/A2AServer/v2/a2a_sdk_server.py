"""
PHA v2 a2a-sdk Server 端（阶段5）

**作用**：提供一个**完全兼容 a2a-sdk 0.3.x 协议**的 JSON-RPC server endpoint。

**特性**：
- 实现 a2a-sdk 标准 endpoint：`/.well-known/agent-card.json`（服务发现）
- 实现 a2a-sdk 标准 `message/send` 和 `message/stream` JSON-RPC 方法
- 内部用 v2 HostGraph 处理请求
- 与现有 hostAgentAPI 共存（不冲突）

**启动方式**（独立端口或挂载到现有 app）：
```python
from A2AServer.v2.a2a_sdk_server import create_a2a_sdk_app
app = create_a2a_sdk_app()  # FastAPI app
# uvicorn app:app --port 10020
```

**客户端调用**（标准 a2a-sdk）：
```python
from a2a.client import A2AClient
from a2a.types import SendMessageRequest, MessageSendParams, Message, TextPart, Part, Role
import httpx, uuid

async with httpx.AsyncClient() as http:
    client = A2AClient(httpx_client=http, url="http://localhost:10020")
    request = SendMessageRequest(
        id=str(uuid.uuid4()),
        params=MessageSendParams(
            message=Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text="我最近头疼"))],
            )
        ),
    )
    response = await client.send_message(request)
```
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---- sys.path ----
_PHA_ROOT = Path(__file__).resolve().parents[5]
for p in [str(_PHA_ROOT), str(_PHA_ROOT / "backend" / "A2AServer" / "src")]:
    if p not in sys.path:
        sys.path.insert(0, p)


# ============================================================
# a2a-sdk 探测
# ============================================================
def _check_a2a_sdk():
    try:
        import a2a
        from a2a.types import (
            Message, TextPart, Part, Role,
            MessageSendParams, SendMessageRequest, SendMessageResponse,
            AgentCard, JSONRPCResponse, Task, TaskStatus,
        )
        return True
    except ImportError as e:
        logger.error("[a2a_sdk_server] a2a-sdk 不可用: %s", e)
        return False


_A2A_SDK_OK = _check_a2a_sdk()


# ============================================================
# A2A SDK Server - FastAPI app
# ============================================================
def create_a2a_sdk_app():
    """
    创建标准 a2a-sdk 协议的 FastAPI app

    Returns:
        FastAPI instance
    """
    if not _A2A_SDK_OK:
        raise RuntimeError("a2a-sdk 不可用，无法创建 server")

    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse

    from a2a.types import (
        Message as SdkMessage,
        TextPart as SdkTextPart,
        Part as SdkPart,
        Role as SdkRole,
        MessageSendParams as SdkMessageSendParams,
        SendMessageRequest as SdkSendMessageRequest,
        SendMessageResponse as SdkSendMessageResponse,
        AgentCard as SdkAgentCard,
        JSONRPCResponse,
        Task as SdkTask,
        TaskStatus as SdkTaskStatus,
    )

    from .a2a_sdk_compat import (
        build_pha_agent_card,
        sdk_to_pha_message,
    )
    from .bridge import v2_process_message

    app = FastAPI(
        title="PHA v2 a2a-sdk Server",
        description="PHA 多智能体健康助理 (a2a-sdk 0.3.x 兼容)",
        version="2.0.0",
    )

    # ---- 1. 服务发现：AgentCard ----
    @app.get("/.well-known/agent-card.json")
    async def get_agent_card():
        """a2a-sdk 标准服务发现 endpoint"""
        card = build_pha_agent_card(
            name="PHA HostGraph v2",
            description="PHA 多智能体健康助理 - 基于 LangGraph 1.0 + LangChain 1.0 + DeepSeek",
            url=os.getenv("PHA_A2A_SDK_URL", "http://localhost:10020"),
            version="2.0.0",
        )
        return card.model_dump(exclude_none=True) if card else {"error": "no card"}

    # ---- 2. JSON-RPC endpoint ----
    @app.post("/")
    async def jsonrpc_root(request: Request):
        return await _handle_jsonrpc(request, SdkSendMessageRequest, SdkMessageSendParams, SdkMessage, SdkTextPart, SdkPart, SdkRole)

    @app.post("")
    async def jsonrpc_root_no_slash(request: Request):
        return await _handle_jsonrpc(request, SdkSendMessageRequest, SdkMessageSendParams, SdkMessage, SdkTextPart, SdkPart, SdkRole)

    # ---- 3. 健康检查 ----
    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "pha-v2-a2a-sdk",
            "version": "2.0.0",
        }

    # ---- 内部 handler ----
    async def _handle_jsonrpc(
        request,
        SdkSendMessageRequest,
        SdkMessageSendParams,
        SdkMessage,
        SdkTextPart,
        SdkPart,
        SdkRole,
    ):
        from fastapi.responses import JSONResponse
        try:
            body = await request.json()
            logger.info(f"[a2a_sdk_server] JSON-RPC request: method={body.get('method')}, id={body.get('id')}")

            method = body.get("method")
            req_id = body.get("id", str(uuid.uuid4()))

            if method == "message/send":
                # 解析标准 a2a-sdk 请求
                params = body.get("params", {})
                sdk_msg = params.get("message")

                # 转 PHA Message -> 调 v2 bridge
                pha_msg_dict = {"role": "user", "parts": [], "metadata": {}}
                if sdk_msg:
                    pha_msg_dict["role"] = "user" if str(sdk_msg.get("role", "user")).lower() == "user" else "agent"
                    pha_msg_dict["metadata"] = sdk_msg.get("metadata", {}) or {}
                    for p in sdk_msg.get("parts", []):
                        root = p.get("root", p)
                        text = root.get("text", "")
                        if text:
                            from A2AServer.common.A2Atypes import TextPart as PhaTextPart
                            pha_msg_dict["parts"].append(PhaTextPart(text=str(text)))

                # 构造 PHA Message 对象
                from A2AServer.common.A2Atypes import Message
                pha_message = Message(
                    role=pha_msg_dict["role"],
                    parts=pha_msg_dict["parts"] or [__import__("A2AServer.common.A2Atypes", fromlist=["TextPart"]).TextPart(text=" ")],
                    metadata=pha_msg_dict["metadata"] or None,
                )
                # 注入 conversation_id
                context_id = params.get("contextId")
                if context_id:
                    pha_message.metadata = pha_message.metadata or {}
                    pha_message.metadata["conversation_id"] = context_id

                # 调 v2
                result = await v2_process_message(pha_message)
                sdk_response_msg = result.get("message")

                # 构造 a2a-sdk 标准响应
                if sdk_response_msg:
                    content = ""
                    for p in sdk_response_msg.parts:
                        text = getattr(p, "text", None)
                        if text:
                            content += str(text)

                    sdk_msg_out = {
                        "kind": "message",
                        "messageId": str(uuid.uuid4()),
                        "role": "agent",
                        "parts": [{"kind": "text", "text": content}],
                        "metadata": {
                            **(sdk_response_msg.metadata or {}),
                            "pha_v2": True,
                            "agent": result.get("result", {}).get("agent"),
                        },
                    }

                    response_payload = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "kind": "message",
                            "message": sdk_msg_out,
                            "contextId": context_id or str(uuid.uuid4()),
                        },
                    }
                else:
                    response_payload = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": f"v2 processing failed: {result.get('error', 'unknown')}",
                        },
                    }

                return JSONResponse(content=response_payload)

            elif method in ("agent/card", "agent.getCard"):
                card = build_pha_agent_card()
                if card:
                    response_payload = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": card.model_dump(exclude_none=True),
                    }
                else:
                    response_payload = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32603, "message": "no card"},
                    }
                return JSONResponse(content=response_payload)

            else:
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"method not found: {method}",
                    },
                })

        except Exception as e:
            logger.exception("[a2a_sdk_server] handler failed")
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": body.get("id", "unknown") if "body" in dir() else "unknown",
                "error": {"code": -32603, "message": f"internal error: {str(e)}"},
            }, status_code=500)

    return app


# ============================================================
# Standalone 启动入口
# ============================================================
def main():
    """standalone 启动"""
    import uvicorn
    port = int(os.getenv("PHA_A2A_SDK_PORT", "10020"))
    app = create_a2a_sdk_app()
    logger.info(f"[a2a_sdk_server] starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
