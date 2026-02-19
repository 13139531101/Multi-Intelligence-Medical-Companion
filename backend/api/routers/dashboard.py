from __future__ import annotations

"""
仪表盘（Dashboard）相关路由（薄路由层）

- 主要用于首页统计与最近活动聚合展示。
- 具体统计/聚合逻辑由 dashboard_service 提供。
"""

from typing import List, Optional

from fastapi import APIRouter
from fastapi import Query, Request

import health_records_api as legacy

import dashboard_service
from ..schemas.models import DashboardActivity, DashboardStats

router = APIRouter()


@router.get("/api/health-records/status")
async def get_api_status():
    """健康检查：用于前端探测服务是否可用。"""
    return await dashboard_service.get_api_status(legacy)


@router.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """获取首页统计（健康档案/咨询/用药/就诊摘要等聚合数据）。"""
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
    """获取最近活动列表（用于首页动态流展示）。"""
    return await dashboard_service.get_dashboard_recent_activities(
        legacy,
        limit=limit,
        user_id=user_id,
        request=request,
    )
