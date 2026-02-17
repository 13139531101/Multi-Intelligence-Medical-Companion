from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

import health_records_api as legacy

import visit_summaries_service
from ..schemas.models import VisitSummary, VisitSummaryBatchCompleteRequest, VisitSummaryCreate

router = APIRouter()


@router.get("/api/visit-summaries/count")
async def get_visit_summary_count(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
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
    return await visit_summaries_service.delete_visit_summary(
        legacy,
        summary_id=summary_id,
        user_id=user_id,
        request=request,
    )
