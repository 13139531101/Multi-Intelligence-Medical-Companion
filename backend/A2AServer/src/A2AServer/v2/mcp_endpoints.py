"""阶段41-2: MCP HTTP 端点（含可视化 + 远程 MCP 注册）"""
import asyncio
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .mcp_loader import get_mcp_loader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/mcp", tags=["mcp"])


@router.get("/servers")
async def list_servers():
    """列出所有 MCP servers"""
    return {"servers": get_mcp_loader().list_servers()}


@router.get("/calls/active")
async def active_calls():
    """正在进行的调用（用于实时可视化）"""
    return {"active": get_mcp_loader().get_active_calls()}


@router.get("/calls/history")
async def call_history(limit: int = 20):
    """历史调用"""
    return {"history": get_mcp_loader().get_call_history(limit)}


@router.post("/register")
async def register_remote_mcp(req: Request):
    """注册远程 MCP
    body: {name, url, type, display_name?, description?}
    """
    body = await req.json()
    name = body.get("name")
    url = body.get("url")
    mcp_type = body.get("type", "http")

    if not name or not url:
        return {"error": "name and url required"}

    from .mcp_loader import MCPType
    server = get_mcp_loader().register_remote(
        name=name, url=url,
        mcp_type=MCPType(mcp_type),
        display_name=body.get("display_name"),
        description=body.get("description", ""),
    )
    return {"registered": server.to_dict()}


@router.post("/call/{mcp_name}")
async def call_mcp(mcp_name: str, req: Request):
    """调用 MCP
    body: {method, args}
    """
    body = await req.json()
    method = body.get("method", "")
    args = body.get("args", {})
    return get_mcp_loader().call(mcp_name, method, args)


@router.get("/health")
async def health_check():
    """所有 MCP 健康检查"""
    return get_mcp_loader().health_check()


@router.get("/visualize/stream")
async def visualize_stream():
    """SSE 流：实时推送 MCP 调用过程
    用法：
        const es = new EventSource('/v2/mcp/visualize/stream');
        es.addEventListener('call_start', e => console.log(JSON.parse(e.data)));
        es.addEventListener('call_end', e => console.log(JSON.parse(e.data)));
    """
    queue: asyncio.Queue = asyncio.Queue()

    def listener(event: str, data: dict):
        try:
            queue.put_nowait((event, data))
        except Exception:
            pass

    get_mcp_loader().add_listener(listener)

    async def event_stream():
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            # 清理 listener
            try:
                get_mcp_loader()._listeners.remove(listener)
            except ValueError:
                pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")