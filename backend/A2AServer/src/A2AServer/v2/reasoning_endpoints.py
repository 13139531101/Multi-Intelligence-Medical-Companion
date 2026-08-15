"""
PHASE 8: 推理过程可视化 HTTP 端点
"""
import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/reasoning", tags=["reasoning-tracer"])


@router.get("/traces")
async def list_traces(limit: int = 20):
    """列出最近的推理链"""
    from .reasoning_tracer import get_tracer
    return {"traces": get_tracer().list_traces(limit=limit)}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """获取单个推理链详情"""
    from .reasoning_tracer import get_tracer
    trace = get_tracer().get_trace(trace_id)
    if not trace:
        return {"error": f"trace not found: {trace_id}"}
    return {"trace": trace.to_dict()}


@router.get("/stats")
async def reasoning_stats():
    """推理追踪统计"""
    from .reasoning_tracer import get_tracer
    return get_tracer().stats()
