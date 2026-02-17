from __future__ import annotations

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route("/api/rag/backfill", legacy.backfill_rag, methods=["POST"])
router.add_api_route(
    "/api/admin/monitor/summary", legacy.admin_monitor_summary, methods=["GET"]
)
router.add_api_route("/api/admin/monitor/check", legacy.admin_monitor_check, methods=["POST"])
router.add_api_route("/api/admin/rag/docs", legacy.admin_list_rag_docs, methods=["POST"])
router.add_api_route("/api/admin/rag/chunks", legacy.admin_list_rag_chunks, methods=["POST"])
router.add_api_route("/api/admin/rag/search", legacy.admin_rag_search, methods=["POST"])
router.add_api_route("/api/admin/rag/reindex", legacy.admin_rag_reindex, methods=["POST"])
router.add_api_route(
    "/api/admin/rag/reindex/bulk", legacy.admin_rag_reindex_bulk, methods=["POST"]
)
