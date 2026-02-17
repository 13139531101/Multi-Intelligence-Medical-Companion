from __future__ import annotations

from typing import List

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route(
    "/api/visit-summaries/history",
    legacy.get_visit_summaries,
    methods=["GET"],
    response_model=List[legacy.VisitSummary],
)
router.add_api_route(
    "/api/visit-summaries/{summary_id}",
    legacy.get_visit_summary_detail,
    methods=["GET"],
    response_model=legacy.VisitSummary,
)
router.add_api_route(
    "/api/visit-summaries/create",
    legacy.create_visit_summary,
    methods=["POST"],
    response_model=legacy.VisitSummary,
)
router.add_api_route(
    "/api/visit-summaries/analyze-image",
    legacy.analyze_visit_summary_image,
    methods=["POST"],
    response_model=legacy.VisitSummary,
)
router.add_api_route(
    "/api/visit-summaries/batch/collect-image",
    legacy.collect_visit_summary_image,
    methods=["POST"],
)
router.add_api_route(
    "/api/visit-summaries/batch/complete",
    legacy.complete_visit_summary_batch,
    methods=["POST"],
    response_model=legacy.VisitSummary,
)
router.add_api_route(
    "/api/visit-summaries/update/{summary_id}",
    legacy.update_visit_summary,
    methods=["PUT"],
    response_model=legacy.VisitSummary,
)
router.add_api_route(
    "/api/visit-summaries/delete/{summary_id}",
    legacy.delete_visit_summary,
    methods=["DELETE"],
)
