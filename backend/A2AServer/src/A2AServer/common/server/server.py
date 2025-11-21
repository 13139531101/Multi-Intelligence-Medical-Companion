from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
from starlette.requests import Request
import os
import jwt
import sys
from A2AServer.common.A2Atypes import (
    A2ARequest,
    JSONRPCResponse,
    InvalidRequestError,
    JSONParseError,
    GetTaskRequest,
    CancelTaskRequest,
    SendTaskRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    InternalError,
    AgentCard,
    TaskResubscriptionRequest,
    SendTaskStreamingRequest,
)
from pydantic import ValidationError
import json
from typing import AsyncIterable, Any
from A2AServer.common.server.task_manager import TaskManager

import logging

logger = logging.getLogger(__name__)


class A2AServer:
    def __init__(
        self,
        host="0.0.0.0",
        port=5000,
        endpoint="/",
        agent_card: AgentCard = None,
        task_manager: TaskManager = None,
    ):
        self.host = host
        self.port = port
        self.endpoint = endpoint
        # Gate requests until MCP tools preload completes
        self.ready_event = asyncio.Event()
        self.task_manager = task_manager
        self.agent_card = agent_card
        self.app = Starlette()
        # 添加 CORS 中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.add_route(self.endpoint, self._process_request, methods=["POST"])
        self.app.add_route(
            "/.well-known/agent.json", self._get_agent_card, methods=["GET"]
        )

        # 在应用生命周期内统一调度 Agent 的异步初始化与清理，避免多次创建事件循环
        self.app.add_event_handler("startup", self._on_startup)
        self.app.add_event_handler("shutdown", self._on_shutdown)

    def start(self):
        if self.agent_card is None:
            raise ValueError("agent_card is not defined")

        if self.task_manager is None:
            raise ValueError("request_handler is not defined")

        import uvicorn

        uvicorn.run(self.app, host=self.host, port=self.port, lifespan="on", log_config=None)

    def _get_agent_card(self, request: Request) -> JSONResponse:
        return JSONResponse(self.agent_card.model_dump(exclude_none=True))

    async def _process_request(self, request: Request):
        # If a task request arrives before MCP preload completes, reject fast
        if request.method in ("POST", "PUT", "PATCH") and not self.ready_event.is_set():
            return JSONResponse({
                "error": "Server is initializing MCP tools. Please retry shortly."
            }, status_code=503)
        try:
            try:
                auth = request.headers.get("authorization") or request.headers.get("Authorization")
                if isinstance(auth, str) and auth.lower().startswith("bearer "):
                    token = auth.split(" ", 1)[1].strip()
                    secret = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
                    alg = os.getenv("JWT_ALGORITHM", "HS256")
                    payload = jwt.decode(token, secret, algorithms=[alg])
                    uid = payload.get("user_id") or payload.get("sub") or payload.get("id")
                    if uid is not None:
                        os.environ["A2A_CURRENT_USER_ID"] = str(uid)
                        os.environ["DEFAULT_USER_ID"] = str(uid)
            except Exception:
                pass
            body = await request.json()
            json_rpc_request = A2ARequest.validate_python(body)

            if isinstance(json_rpc_request, GetTaskRequest):
                result = await self.task_manager.on_get_task(json_rpc_request)
            elif isinstance(json_rpc_request, SendTaskRequest):
                result = await self.task_manager.on_send_task(json_rpc_request)
            elif isinstance(json_rpc_request, SendTaskStreamingRequest):
                result = await self.task_manager.on_send_task_subscribe(
                    json_rpc_request
                )
            elif isinstance(json_rpc_request, CancelTaskRequest):
                result = await self.task_manager.on_cancel_task(json_rpc_request)
            elif isinstance(json_rpc_request, SetTaskPushNotificationRequest):
                result = await self.task_manager.on_set_task_push_notification(json_rpc_request)
            elif isinstance(json_rpc_request, GetTaskPushNotificationRequest):
                result = await self.task_manager.on_get_task_push_notification(json_rpc_request)
            elif isinstance(json_rpc_request, TaskResubscriptionRequest):
                result = await self.task_manager.on_resubscribe_to_task(
                    json_rpc_request
                )
            else:
                logger.warning(f"Unexpected request type: {type(json_rpc_request)}")
                raise ValueError(f"Unexpected request type: {type(request)}")

            return self._create_response(result)

        except Exception as e:
            return self._handle_exception(e)

    async def _on_startup(self):
        # 在服务器启动时预加载 MCP 工具，确保与主事件循环对齐
        try:
            if self.task_manager and hasattr(self.task_manager, "agent") and getattr(self.task_manager, "agent", None):
                # 若主进程已预加载，则跳过重复加载
                if not getattr(self.task_manager.agent, "tool_ready", False):
                    logger.info("正在服务器启动阶段预加载 MCP 工具...")
                    await self.task_manager.agent.setup_tools()
                else:
                    logger.info("检测到 MCP 工具已在主进程预加载，启动阶段跳过")
                logger.info("MCP 工具预加载完成")
                # Mark server ready to accept task requests
                self.ready_event.set()
        except Exception as e:
            logger.error(f"MCP 工具预加载失败：{e}")

    async def _on_shutdown(self):
        # 在服务器关闭时清理 Agent 资源，避免后台 I/O 任务泄漏
        try:
            if self.task_manager and hasattr(self.task_manager, "agent") and getattr(self.task_manager, "agent", None):
                await self.task_manager.agent.cleanup()
                if sys.platform.startswith("win"):
                    try:
                        await asyncio.shield(asyncio.sleep(0.05))
                    except BaseException:
                        pass
        except Exception as e:
            logger.debug(f"忽略关闭阶段的清理错误: {e!r}")

    def _handle_exception(self, e: Exception) -> JSONResponse:
        if isinstance(e, json.decoder.JSONDecodeError):
            json_rpc_error = JSONParseError()
        elif isinstance(e, ValidationError):
            json_rpc_error = InvalidRequestError(data=json.loads(e.json()))
        else:
            logger.error(f"Unhandled exception: {e}")
            json_rpc_error = InternalError()

        response = JSONRPCResponse(id=None, error=json_rpc_error)
        return JSONResponse(response.model_dump(exclude_none=True), status_code=400)

    def _create_response(self, result: Any) -> JSONResponse | EventSourceResponse:
        if isinstance(result, AsyncIterable):

            async def event_generator(result) -> AsyncIterable[dict[str, str]]:
                async for item in result:
                    yield {"data": item.model_dump_json(exclude_none=True)}

            return EventSourceResponse(event_generator(result))
        elif isinstance(result, JSONRPCResponse):
            return JSONResponse(result.model_dump(exclude_none=True))
        else:
            logger.error(f"Unexpected result type: {type(result)}")
            raise ValueError(f"Unexpected result type: {type(result)}")
