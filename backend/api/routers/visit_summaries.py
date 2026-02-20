from __future__ import annotations

"""
就诊摘要（Visit Summaries）相关路由（薄路由层）

- 提供摘要的增删改查、图片识别生成摘要，以及批量采集图片后合并生成摘要的能力。
- 路由层只做参数声明与转发，具体逻辑在 visit_summaries_service。
"""

from typing import List, Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

import health_records_api as legacy

from services import visit_summaries_service
from ..schemas.models import VisitSummary, VisitSummaryBatchCompleteRequest, VisitSummaryCreate

router = APIRouter()


@router.get("/api/visit-summaries/count")
async def get_visit_summary_count(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """统计就诊摘要数量（可按用户过滤）。"""
    return await visit_summaries_service.get_visit_summary_count(
        legacy,
        user_id=user_id,
        request=request,
    )


@router.get("/api/visit-summaries/history", response_model=List[VisitSummary])
async def get_visit_summaries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """分页获取就诊摘要历史列表（可按用户过滤）。"""
    return await visit_summaries_service.get_visit_summaries(
        legacy,
        skip=skip,
        limit=limit,
        user_id=user_id,
        request=request,
    )


@router.get("/api/visit-summaries/{summary_id}", response_model=VisitSummary)
async def get_visit_summary_detail(
    summary_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """获取单条就诊摘要详情。"""
    return await visit_summaries_service.get_visit_summary_detail(
        legacy,
        summary_id=summary_id,
        user_id=user_id,
        request=request,
    )


@router.post("/api/visit-summaries/create", response_model=VisitSummary)
async def create_visit_summary(
    summary: VisitSummaryCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """创建就诊摘要（用于手工录入或前端编辑后提交）。"""
    return await visit_summaries_service.create_visit_summary(
        legacy,
        summary=summary,
        user_id=user_id,
        request=request,
    )


@router.post("/api/visit-summaries/analyze-image", response_model=VisitSummary)
async def analyze_visit_summary_image(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    visit_date: str = Form(None),
    request: Request = None,
):
    """上传图片并识别生成就诊摘要（OCR + 结构化提取/生成）。"""
    return await visit_summaries_service.analyze_visit_summary_image(
        legacy,
        file=file,
        user_id=user_id,
        visit_date=visit_date,
        request=request,
    )


@router.post("/api/visit-summaries/batch/collect-image")
async def collect_visit_summary_image(
    file: UploadFile = File(...),
    batch_id: str = Form(...),
    user_id: str = Form(None),
    request: Request = None,
):
    """批次采集：向指定 batch_id 追加上传图片（稍后统一合并生成摘要）。"""
    return await visit_summaries_service.collect_visit_summary_image(
        legacy,
        file=file,
        batch_id=batch_id,
        user_id=user_id,
        request=request,
    )


@router.post("/api/visit-summaries/batch/complete", response_model=VisitSummary)
async def complete_visit_summary_batch(
    payload: VisitSummaryBatchCompleteRequest,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """批次完成：合并 batch_id 下的图片并生成最终就诊摘要。"""
    return await visit_summaries_service.complete_visit_summary_batch(
        legacy,
        payload=payload,
        user_id=user_id,
        request=request,
    )


@router.put("/api/visit-summaries/update/{summary_id}", response_model=VisitSummary)
async def update_visit_summary(
    summary_id: str,
    summary: VisitSummaryCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """更新就诊摘要内容（用于二次编辑/纠错）。"""
    return await visit_summaries_service.update_visit_summary(
        legacy,
        summary_id=summary_id,
        summary=summary,
        user_id=user_id,
        request=request,
    )


@router.delete("/api/visit-summaries/delete/{summary_id}")
async def delete_visit_summary(
    summary_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """删除就诊摘要。"""
    return await visit_summaries_service.delete_visit_summary(
        legacy,
        summary_id=summary_id,
        user_id=user_id,
        request=request,
    )
