from __future__ import annotations

"""
RAG 相关路由（薄路由层）

- 本文件只负责定义 FastAPI 路由与请求模型，并把具体业务逻辑委托给 service 层。
- legacy 模块（health_records_api）在当前代码结构里承担了若干请求/响应模型与部分共用逻辑，
  这里通过依赖注入的方式传给 rag_service，避免 service 层直接依赖 FastAPI。
"""

from fastapi import APIRouter, Request

import health_records_api as legacy

from services import rag_service
from ..schemas.models import RAGBackfillRequest

router = APIRouter()


@router.post("/api/rag/backfill")
async def backfill_rag(payload: RAGBackfillRequest, request: Request = None):
    """普通用户触发：对历史数据进行 RAG 回填（embedding/分块入库等）。"""
    return await rag_service.backfill_rag(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/backfill")
async def admin_backfill_rag(payload: RAGBackfillRequest, request: Request = None):
    """管理员触发：对指定用户/范围执行 RAG 回填。"""
    return await rag_service.admin_backfill_rag(
        legacy, payload=payload, request=request
    )


@router.get("/api/admin/monitor/summary")
async def admin_monitor_summary(request: Request = None):
    """管理员查看：RAG/入库监控摘要（任务与数据概览）。"""
    return await rag_service.admin_monitor_summary(legacy, request=request)


@router.post("/api/admin/monitor/check")
async def admin_monitor_check(
    payload: legacy.MonitorCheckRequest, request: Request = None
):
    """管理员校验：按条件检查 RAG 入库/数据一致性并返回检测结果。"""
    return await rag_service.admin_monitor_check(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/docs")
async def admin_list_rag_docs(
    payload: legacy.AdminRAGDocsListRequest, request: Request = None
):
    """管理员查询：按过滤条件分页列出已入库/可入库的文档记录。"""
    return await rag_service.admin_list_rag_docs(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/chunks")
async def admin_list_rag_chunks(
    payload: legacy.AdminRAGChunksListRequest, request: Request = None
):
    """管理员查询：分页列出 RAG 切分后的 chunk（用于排查分块与向量入库质量）。"""
    return await rag_service.admin_list_rag_chunks(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/search")
async def admin_rag_search(
    payload: legacy.AdminRAGSearchRequest, request: Request = None
):
    """管理员调试：在 RAG 索引中执行检索（便于验证召回效果）。"""
    return await rag_service.admin_rag_search(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/reindex")
async def admin_rag_reindex(
    payload: legacy.AdminRAGReindexRequest, request: Request = None
):
    """管理员触发：对单个文档/来源执行重建索引（重新分块+向量化+入库）。"""
    return await rag_service.admin_rag_reindex(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/reindex/bulk")
async def admin_rag_reindex_bulk(
    payload: legacy.AdminRAGReindexBulkRequest, request: Request = None
):
    """管理员触发：批量重建索引（用于数据大规模变更或模型切换后的重建）。"""
    return await rag_service.admin_rag_reindex_bulk(legacy, payload=payload, request=request)
