from __future__ import annotations

from fastapi import APIRouter, Request

import health_records_api as legacy

import rag_service
from ..schemas.models import RAGBackfillRequest

router = APIRouter()


@router.post("/api/rag/backfill")
async def backfill_rag(payload: RAGBackfillRequest, request: Request = None):
    return await rag_service.backfill_rag(legacy, payload=payload, request=request)


@router.get("/api/admin/monitor/summary")
async def admin_monitor_summary(request: Request = None):
    return await rag_service.admin_monitor_summary(legacy, request=request)


@router.post("/api/admin/monitor/check")
async def admin_monitor_check(
    payload: legacy.MonitorCheckRequest, request: Request = None
):
    return await rag_service.admin_monitor_check(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/docs")
async def admin_list_rag_docs(
    payload: legacy.AdminRAGDocsListRequest, request: Request = None
):
    return await rag_service.admin_list_rag_docs(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/chunks")
async def admin_list_rag_chunks(
    payload: legacy.AdminRAGChunksListRequest, request: Request = None
):
    return await rag_service.admin_list_rag_chunks(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/search")
async def admin_rag_search(
    payload: legacy.AdminRAGSearchRequest, request: Request = None
):
    return await rag_service.admin_rag_search(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/reindex")
async def admin_rag_reindex(
    payload: legacy.AdminRAGReindexRequest, request: Request = None
):
    return await rag_service.admin_rag_reindex(legacy, payload=payload, request=request)


@router.post("/api/admin/rag/reindex/bulk")
async def admin_rag_reindex_bulk(
    payload: legacy.AdminRAGReindexBulkRequest, request: Request = None
):
    return await rag_service.admin_rag_reindex_bulk(legacy, payload=payload, request=request)
