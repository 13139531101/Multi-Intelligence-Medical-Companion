from __future__ import annotations

from fastapi import APIRouter

import health_records_api as legacy

router = APIRouter()

router.add_api_route(
    "/api/health-trends/backfill", legacy.backfill_health_trends, methods=["POST"]
)
router.add_api_route(
    "/api/health-trends/indicators", legacy.get_health_trend_indicators, methods=["GET"]
)
router.add_api_route(
    "/api/health-trends/indicator", legacy.get_health_trend_indicator, methods=["GET"]
)
