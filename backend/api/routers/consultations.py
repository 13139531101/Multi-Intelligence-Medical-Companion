from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query, Request

import health_records_api as legacy

import consultations_service
from ..schemas.models import ChatMessageCreate, Consultation, ConsultationCreate

router = APIRouter()


@router.get("/api/consultations/history", response_model=List[Consultation])
async def get_consultation_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    include_summary: bool = Query(False),
    include_health_records: bool = Query(False),
    request: Request = None,
):
    return await consultations_service.get_consultation_history(
        legacy,
        skip=skip,
        limit=limit,
        user_id=user_id,
        include_summary=include_summary,
        include_health_records=include_health_records,
        request=request,
    )


@router.post("/api/consultations/create", response_model=Consultation)
async def create_consultation(
    consultation: ConsultationCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.create_consultation(
        legacy,
        consultation=consultation,
        user_id=user_id,
        request=request,
    )


@router.delete("/api/consultations/delete/{consultation_id}")
async def delete_consultation(
    consultation_id: int,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.delete_consultation(
        legacy,
        consultation_id=consultation_id,
        user_id=user_id,
        request=request,
    )


@router.post("/api/consultations/message")
async def save_consultation_message(
    message: ChatMessageCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.save_consultation_message(
        legacy,
        message=message,
        user_id=user_id,
        request=request,
    )


@router.get("/api/consultations/{consultation_id}/messages")
async def get_consultation_messages(
    consultation_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.get_consultation_messages(
        legacy,
        consultation_id=consultation_id,
        user_id=user_id,
        request=request,
    )
