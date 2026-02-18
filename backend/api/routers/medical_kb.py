from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

import health_records_api as legacy

import medical_kb_service

router = APIRouter()


@router.post("/api/medical-kb/docs")
async def upsert_medical_kb_doc(
    payload: legacy.MedicalKBDocUpsertRequest, request: Request = None
):
    return await medical_kb_service.upsert_medical_kb_doc(
        legacy, payload=payload, request=request
    )


@router.post("/api/medical-kb/docs/bulk")
async def bulk_upsert_medical_kb_docs(
    payload: legacy.MedicalKBDocBulkUpsertRequest, request: Request = None
):
    return await medical_kb_service.bulk_upsert_medical_kb_docs(
        legacy, payload=payload, request=request
    )


@router.post("/api/admin/medical-kb/import")
async def admin_import_medical_kb(
    payload: legacy.AdminMedicalKBImportRequest, request: Request = None
):
    return await medical_kb_service.admin_import_medical_kb(
        legacy, payload=payload, request=request
    )


@router.post("/api/admin/medical-kb/upload")
async def admin_upload_medical_kb_file(
    file: UploadFile = File(...),
    global_kb: bool = Form(True),
    user_id: Optional[str] = Form(None),
    doc_id: Optional[str] = Form(None),
    doc_type: Optional[str] = Form("medical_kb"),
    title: Optional[str] = Form(None),
    request: Request = None,
):
    return await medical_kb_service.admin_upload_medical_kb_file(
        legacy,
        file=file,
        global_kb=global_kb,
        user_id=user_id,
        doc_id=doc_id,
        doc_type=doc_type,
        title=title,
        request=request,
    )


@router.post("/api/admin/medical-kb/import-from-api")
async def admin_import_medical_kb_from_api(
    payload: legacy.AdminMedicalKBImportFromAPIRequest, request: Request = None
):
    return await medical_kb_service.admin_import_medical_kb_from_api(
        legacy, payload=payload, request=request
    )


@router.delete("/api/admin/medical-kb/docs/{doc_id}")
async def admin_delete_medical_kb_doc(
    doc_id: str,
    global_kb: bool = Query(True),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await medical_kb_service.admin_delete_medical_kb_doc(
        legacy,
        doc_id=doc_id,
        global_kb=global_kb,
        user_id=user_id,
        request=request,
    )


@router.get("/api/medical-kb/docs")
async def list_medical_kb_docs(
    user_id: Optional[str] = Query(None),
    global_kb: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    request: Request = None,
):
    return await medical_kb_service.list_medical_kb_docs(
        legacy,
        user_id=user_id,
        global_kb=global_kb,
        limit=limit,
        offset=offset,
        request=request,
    )


@router.get("/api/medical-kb/stats")
async def get_medical_kb_stats(
    user_id: Optional[str] = Query(None),
    global_kb: bool = Query(True),
    request: Request = None,
):
    return await medical_kb_service.get_medical_kb_stats(
        legacy, user_id=user_id, global_kb=global_kb, request=request
    )


@router.delete("/api/medical-kb/docs/{doc_id}")
async def delete_medical_kb_doc(
    doc_id: str,
    user_id: Optional[str] = Query(None),
    global_kb: bool = Query(True),
    request: Request = None,
):
    return await medical_kb_service.delete_medical_kb_doc(
        legacy,
        doc_id=doc_id,
        user_id=user_id,
        global_kb=global_kb,
        request=request,
    )
