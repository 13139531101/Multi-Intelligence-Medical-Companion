from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from fastapi import Query, Request

import health_records_api as legacy

import dashboard_service
from ..schemas.models import DashboardActivity, DashboardStats

router = APIRouter()


@router.get("/api/health-records/status")
async def get_api_status():
    return await dashboard_service.get_api_status(legacy)


@router.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await dashboard_service.get_dashboard_stats(
        legacy,
        user_id=user_id,
        request=request,
    )


@router.get("/api/dashboard/recent-activities", response_model=List[DashboardActivity])
async def get_dashboard_recent_activities(
    limit: int = Query(10, ge=1, le=50),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await dashboard_service.get_dashboard_recent_activities(
        legacy,
        limit=limit,
        user_id=user_id,
        request=request,
    )
