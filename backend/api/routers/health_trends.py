from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

import health_records_api as legacy

import health_records_service

router = APIRouter()


@router.post("/api/health-trends/backfill")
async def backfill_health_trends(
    days: int = Query(365),
    limit: int = Query(200),
    dry_run: bool = Query(True),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await health_records_service.backfill_health_trends(
        legacy,
        days=days,
        limit=limit,
        dry_run=dry_run,
        user_id=user_id,
        request=request,
    )


@router.get("/api/health-trends/indicators")
async def get_health_trend_indicators(
    days: int = Query(180),
    include_points: bool = Query(True),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await health_records_service.get_health_trend_indicators(
        legacy,
        days=days,
        include_points=include_points,
        user_id=user_id,
        request=request,
    )


@router.get("/api/health-trends/indicator")
async def get_health_trend_indicator(
    name: str = Query(...),
    days: int = Query(180),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await health_records_service.get_health_trend_indicator(
        legacy,
        name=name,
        days=days,
        user_id=user_id,
        request=request,
    )
