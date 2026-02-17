from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

import health_records_api as legacy

import health_records_service
from ..schemas.models import (
    HealthInsightsResponse,
    HealthRecord,
    HealthRecordCreate,
    HealthRecordUpdate,
    HealthStatistics,
    ImportanceLevel,
    RecordType,
)

router = APIRouter()


@router.get("/api/health-records", response_model=List[HealthRecord])
async def get_health_records(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    record_type: Optional[RecordType] = Query(None, description="记录类型筛选"),
    importance: Optional[ImportanceLevel] = Query(None, description="重要性筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    request: Request = None,
):
    return await health_records_service.get_health_records(
        legacy,
        skip=skip,
        limit=limit,
        record_type=record_type,
        importance=importance,
        search=search,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        request=request,
    )


@router.get("/api/health-records/{record_id}", response_model=HealthRecord)
async def get_health_record(
    record_id: str,
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    request: Request = None,
):
    return await health_records_service.get_health_record(
        legacy,
        record_id=record_id,
        user_id=user_id,
        request=request,
    )


@router.post("/api/health-records", response_model=HealthRecord)
async def create_health_record(
    record: HealthRecordCreate,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    return await health_records_service.create_health_record(
        legacy,
        record=record,
        user_id=user_id,
        request=request,
    )


@router.put("/api/health-records/{record_id}", response_model=HealthRecord)
async def update_health_record(
    record_id: str,
    record_update: HealthRecordUpdate,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    return await health_records_service.update_health_record(
        legacy,
        record_id=record_id,
        record_update=record_update,
        user_id=user_id,
        request=request,
    )


@router.delete("/api/health-records/{record_id}")
async def delete_health_record(
    record_id: str,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    return await health_records_service.delete_health_record(
        legacy,
        record_id=record_id,
        user_id=user_id,
        request=request,
    )


@router.get("/api/health-records/statistics", response_model=HealthStatistics)
async def get_health_statistics():
    return await health_records_service.get_health_statistics(legacy)


@router.get("/api/health-records/insights", response_model=HealthInsightsResponse)
async def get_health_insights(
    analysis_type: str = Query("comprehensive", description="分析类型"),
    include_recommendations: bool = Query(True, description="包含建议"),
    include_trends: bool = Query(True, description="包含趋势"),
    include_risks: bool = Query(True, description="包含风险"),
):
    return await health_records_service.get_health_insights(
        legacy,
        analysis_type=analysis_type,
        include_recommendations=include_recommendations,
        include_trends=include_trends,
        include_risks=include_risks,
    )


@router.post("/api/health-records/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    skip_ocr: Optional[str] = Form(None),
    request: Request = None,
):
    return await health_records_service.upload_file(
        legacy,
        file=file,
        user_id=user_id,
        skip_ocr=skip_ocr,
        request=request,
    )


@router.post("/api/health-records/upload/multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    user_id: str = Form(None),
    request: Request = None,
):
    return await health_records_service.upload_multiple_files(
        legacy,
        files=files,
        user_id=user_id,
        request=request,
    )


@router.post("/api/health-records/sync-to-hrm")
async def sync_sqlite_to_hrm(user_id: str = Query(..., description="需要同步的用户ID")):
    return await health_records_service.sync_sqlite_to_hrm(legacy, user_id=user_id)


@router.get("/api/health-records/{record_id}/extracted")
async def get_record_extracted_info(record_id: str):
    return await health_records_service.get_record_extracted_info(
        legacy,
        record_id=record_id,
    )


@router.get("/api/health-records/files/{file_id}")
async def get_file_attachment(file_id: str):
    return await health_records_service.get_file_attachment(
        legacy,
        file_id=file_id,
    )
