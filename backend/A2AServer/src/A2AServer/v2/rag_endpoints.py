"""
PHA v2 RAG HTTP 端点（阶段21）
"""
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, Header
from pydantic import BaseModel

from . import rag

logger = logging.getLogger(__name__)

rag_router = APIRouter(prefix="/v2/rag", tags=["rag"])


class IndexRequest(BaseModel):
    user_id: str
    source_type: str
    source_id: str
    text: str
    record_type: str = ""
    title: str = ""


class FeedbackRequest(BaseModel):
    user_id: str
    chunk_id: str
    query: str = ""
    score_delta: float = 1.0


@rag_router.post("/index")
async def rag_index(req: IndexRequest):
    """索引一个文档"""
    if not req.user_id or not req.text:
        raise HTTPException(status_code=400, detail="missing user_id or text")
    if len(req.text) > 100000:
        raise HTTPException(status_code=413, detail="text too long (max 100KB)")
    try:
        result = await rag.get_rag_store().index_document(
            user_id=req.user_id,
            source_type=req.source_type,
            source_id=req.source_id,
            text=req.text,
            record_type=req.record_type,
            title=req.title,
        )
    except Exception as e:
        logger.exception("RAG index failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])
    return result


@rag_router.get("/search")
async def rag_search(
    user_id: str = Query(...),
    query: str = Query(...),
    top_k: int = Query(default=5, le=20),
    min_score: float = Query(default=0.5, ge=0.0, le=1.0),
    source_type: str = Query(default=""),
):
    """语义检索"""
    try:
        results = await rag.get_rag_store().search(
            user_id=user_id,
            query=query,
            top_k=top_k,
            min_score=min_score,
            source_type=source_type or None,
        )
    except Exception as e:
        logger.exception("RAG search failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "chunk_id": r.chunk_id,
                "score": round(r.score, 4),
                "feedback_score": r.feedback_score,
                "title": r.title,
                "source": f"{r.source_type}/{r.source_id}",
                "chunk_index": r.chunk_index,
                "text": r.chunk_text,
            }
            for r in results
        ],
    }


@rag_router.post("/feedback")
async def rag_feedback(req: FeedbackRequest):
    """加反馈（+1 点赞 / -1 点踩）"""
    if abs(req.score_delta) > 5:
        raise HTTPException(status_code=400, detail="score_delta must be in [-5, 5]")
    rag.get_rag_store().add_feedback(
        user_id=req.user_id,
        chunk_id=req.chunk_id,
        query=req.query,
        score_delta=req.score_delta,
    )
    return {"recorded": True}


@rag_router.get("/recall")
async def rag_recall(
    user_id: str = Query(...),
    query: str = Query(...),
    top_k: int = Query(default=3, le=10),
):
    """召回（搜索 + 整理）"""
    return await rag.get_rag_store().recall_for_user(user_id, query, top_k)


@rag_router.get("/stats")
async def rag_stats():
    """RAG 统计"""
    try:
        return rag.get_rag_store().stats()
    except Exception as e:
        logger.exception("RAG stats failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])
