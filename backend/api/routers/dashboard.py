from __future__ import annotations

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route("/api/health-records/status", legacy.get_api_status, methods=["GET"])
router.add_api_route(
    "/api/dashboard/stats",
    legacy.get_dashboard_stats,
    methods=["GET"],
    response_model=legacy.DashboardStats,
)
router.add_api_route(
    "/api/visit-summaries/count", legacy.get_visit_summary_count, methods=["GET"]
)
router.add_api_route(
    "/api/dashboard/recent-activities", legacy.get_dashboard_recent_activities, methods=["GET"]
)
