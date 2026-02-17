from __future__ import annotations

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route("/api/medical-kb/docs", legacy.upsert_medical_kb_doc, methods=["POST"])
router.add_api_route(
    "/api/medical-kb/docs/bulk", legacy.bulk_upsert_medical_kb_docs, methods=["POST"]
)
router.add_api_route(
    "/api/admin/medical-kb/import", legacy.admin_import_medical_kb, methods=["POST"]
)
router.add_api_route(
    "/api/admin/medical-kb/docs/{doc_id}",
    legacy.admin_delete_medical_kb_doc,
    methods=["DELETE"],
)
router.add_api_route("/api/medical-kb/docs", legacy.list_medical_kb_docs, methods=["GET"])
router.add_api_route("/api/medical-kb/stats", legacy.get_medical_kb_stats, methods=["GET"])
router.add_api_route(
    "/api/medical-kb/docs/{doc_id}", legacy.delete_medical_kb_doc, methods=["DELETE"]
)
