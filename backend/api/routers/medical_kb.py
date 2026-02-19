from __future__ import annotations

"""
医疗知识库（Medical KB）相关路由（薄路由层）

- 本文件仅负责 FastAPI 路由定义与参数声明；具体业务逻辑下沉到 medical_kb_service。
- legacy（health_records_api）用于复用鉴权、数据库连接与部分请求模型，作为依赖注入参数传入 service。
"""

from typing import Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

import health_records_api as legacy

import medical_kb_service

router = APIRouter()


@router.post("/api/medical-kb/docs")
async def upsert_medical_kb_doc(
    payload: legacy.MedicalKBDocUpsertRequest, request: Request = None
):
    """创建或更新一条知识库文档元数据（通常用于程序化写入/同步）。"""
    return await medical_kb_service.upsert_medical_kb_doc(
        legacy, payload=payload, request=request
    )


@router.post("/api/medical-kb/docs/bulk")
async def bulk_upsert_medical_kb_docs(
    payload: legacy.MedicalKBDocBulkUpsertRequest, request: Request = None
):
    """批量创建或更新知识库文档元数据（用于批处理导入）。"""
    return await medical_kb_service.bulk_upsert_medical_kb_docs(
        legacy, payload=payload, request=request
    )


@router.post("/api/admin/medical-kb/import")
async def admin_import_medical_kb(
    payload: legacy.AdminMedicalKBImportRequest, request: Request = None
):
    """管理员导入：按 doc_id/doc_type/title 等信息触发知识库入库/重建。"""
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
    """管理员上传：上传文件并写入知识库（支持全局/用户级知识库）。"""
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
    """管理员导入：从外部 API 拉取内容并入库（用于快速导入结构化知识）。"""
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
    """管理员删除：删除指定 doc_id 的知识库文档及其向量/分块数据。"""
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
    """查询知识库文档列表（支持用户级/全局、分页）。"""
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
    """查询知识库统计信息（文档数、分块数等）。"""
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
    """用户删除：删除自己名下（或指定范围）的知识库文档。"""
    return await medical_kb_service.delete_medical_kb_doc(
        legacy,
        doc_id=doc_id,
        user_id=user_id,
        global_kb=global_kb,
        request=request,
    )
