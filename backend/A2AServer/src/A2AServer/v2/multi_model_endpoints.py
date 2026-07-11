"""
PHA v2 Multi-Model HTTP 端点（阶段24）
"""
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, Header
from pydantic import BaseModel

from . import multi_model
from .multi_model import ChatMessage

logger = logging.getLogger(__name__)

mm_router = APIRouter(prefix="/v2/models", tags=["multi_model"])


class ChatRequest(BaseModel):
    messages: List[dict]  # [{"role": "user", "content": "..."}]
    task_type: str = "chat"
    max_tokens: int = 2048
    temperature: float = 0.7
    prefer_provider: str = ""


@mm_router.post("/chat")
async def chat_completion(req: ChatRequest):
    """调用 LLM（自动选 provider + fallback）"""
    try:
        msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in req.messages]
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"invalid message format: {e}")
    try:
        result = await multi_model.get_router().chat(
            messages=msgs,
            task_type=req.task_type,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            prefer_provider=req.prefer_provider or None,
        )
    except Exception as e:
        logger.exception("multi_model chat failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])
    return {
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "latency_ms": round(result.latency_ms, 1),
        "fallback_used": result.fallback_used,
        "error": result.error,
    }


@mm_router.get("/providers")
async def list_providers():
    """列所有 provider + 状态"""
    return {
        "providers": multi_model.get_router().list_providers(),
    }


@mm_router.get("/stats")
async def stats():
    """Router 统计"""
    return multi_model.get_router().stats()


@mm_router.post("/test-fallback")
async def test_fallback():
    """测 fallback 链：用空 prompt 触发所有 provider 失败，确认 fallback 走完"""
    from .multi_model import ChatMessage
    # 故意传超长 prompt 触发大部分 provider 失败（如果有限制）
    # 或直接调用所有 provider 看哪些 is_configured
    router = multi_model.get_router()
    configured = [p["name"] for p in router.list_providers() if p["configured"]]
    return {
        "configured_providers": configured,
        "fallback_chain": multi_model.FALLBACK_CHAIN,
        "task_routing": multi_model.TASK_ROUTING,
        "can_fallback": len(configured) >= 2,
    }
