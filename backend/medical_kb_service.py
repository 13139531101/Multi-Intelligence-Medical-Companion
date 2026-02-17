from __future__ import annotations

import uuid
from typing import Any


async def upsert_medical_kb_doc(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    uid = api._resolve_user_id(request, getattr(payload, "user_id", None))
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    title = (getattr(payload, "title", None) or "").strip()
    content = (getattr(payload, "content", None) or "").strip()
    if not title or not content:
        raise api.HTTPException(status_code=400, detail="title 与 content 不能为空")

    kb_uid = api._GLOBAL_KB_USER_ID if bool(getattr(payload, "global_kb", True)) else uid
    doc_id = (getattr(payload, "doc_id", None) or "").strip() or str(uuid.uuid4())
    doc_type = (getattr(payload, "doc_type", None) or "").strip() or "medical_kb"

    text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()

    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                inserted = api._upsert_rag_document(
                    cursor,
                    user_id=kb_uid,
                    source_type="medical_kb",
                    source_id=doc_id,
                    record_type=doc_type,
                    title=title,
                    text=text,
                )
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"知识库入库失败: {e}")

    return {
        "success": True,
        "doc_id": doc_id,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "inserted_chunks": int(inserted or 0),
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def bulk_upsert_medical_kb_docs(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    uid = api._resolve_user_id(request, getattr(payload, "user_id", None))
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    kb_uid = api._GLOBAL_KB_USER_ID if bool(getattr(payload, "global_kb", True)) else uid
    docs = getattr(payload, "docs", None) or []
    if not docs:
        raise api.HTTPException(status_code=400, detail="docs不能为空")

    results: list[dict[str, Any]] = []
    total_chunks = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (getattr(d, "title", None) or "").strip()
                content = (getattr(d, "content", None) or "").strip()
                if not title or not content:
                    results.append(
                        {
                            "success": False,
                            "doc_id": getattr(d, "doc_id", None),
                            "error": "title 与 content 不能为空",
                        }
                    )
                    continue
                doc_id = (getattr(d, "doc_id", None) or "").strip() or str(uuid.uuid4())
                doc_type = (getattr(d, "doc_type", None) or "").strip() or "medical_kb"
                text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()
                try:
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=kb_uid,
                        source_type="medical_kb",
                        source_id=doc_id,
                        record_type=doc_type,
                        title=title,
                        text=text,
                    )
                    conn.commit()
                    total_chunks += int(inserted or 0)
                    results.append(
                        {
                            "success": True,
                            "doc_id": doc_id,
                            "inserted_chunks": int(inserted or 0),
                        }
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append(
                        {"success": False, "doc_id": doc_id, "error": str(e)}
                    )

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "docs": results,
        "inserted_chunks": total_chunks,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_import_medical_kb(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    docs = getattr(payload, "docs", None) or []
    if not docs:
        raise api.HTTPException(status_code=400, detail="docs不能为空")

    if bool(getattr(payload, "global_kb", True)):
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (getattr(payload, "user_id", None) or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    results: list[dict[str, Any]] = []
    total_chunks = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (getattr(d, "title", None) or "").strip()
                content = (getattr(d, "content", None) or "").strip()
                if not title or not content:
                    results.append(
                        {
                            "success": False,
                            "doc_id": getattr(d, "doc_id", None),
                            "error": "title 与 content 不能为空",
                        }
                    )
                    continue
                doc_id = (getattr(d, "doc_id", None) or "").strip() or str(uuid.uuid4())
                doc_type = (getattr(d, "doc_type", None) or "").strip() or "medical_kb"
                text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()
                try:
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=kb_uid,
                        source_type="medical_kb",
                        source_id=doc_id,
                        record_type=doc_type,
                        title=title,
                        text=text,
                    )
                    conn.commit()
                    total_chunks += int(inserted or 0)
                    results.append(
                        {
                            "success": True,
                            "doc_id": doc_id,
                            "inserted_chunks": int(inserted or 0),
                        }
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append(
                        {"success": False, "doc_id": doc_id, "error": str(e)}
                    )

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "docs": results,
        "inserted_chunks": total_chunks,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_delete_medical_kb_doc(
    api: Any,
    *,
    doc_id: str,
    global_kb: bool,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    api._require_admin(request)

    did = (doc_id or "").strip()
    if not did:
        raise api.HTTPException(status_code=400, detail="doc_id不能为空")

    if global_kb:
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (user_id or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    deleted = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                api._ensure_rag_schema(cursor)
                cursor.execute(
                    """
                    DELETE FROM rag_documents
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                cursor.execute(
                    """
                    DELETE FROM rag_chunks
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                deleted = int(cursor.rowcount or 0)
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"删除知识库文档失败: {e}")

    return {
        "success": True,
        "doc_id": did,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "deleted_chunks": deleted,
    }

async def list_medical_kb_docs(
    api: Any,
    *,
    user_id: Any,
    global_kb: bool,
    limit: int,
    offset: int,
    request: Any,
) -> dict[str, Any]:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    kb_uid = api._GLOBAL_KB_USER_ID if global_kb else uid

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                """
                SELECT
                    source_id AS doc_id,
                    COALESCE(title, '') AS title,
                    COALESCE(record_type, '') AS doc_type,
                    chunk_count AS chunks,
                    created_at,
                    updated_at
                FROM (
                    SELECT DISTINCT ON (source_id)
                        source_id, title, record_type, chunk_count, created_at, updated_at
                    FROM rag_documents
                    WHERE user_id = %s AND source_type = 'medical_kb'
                    ORDER BY source_id, updated_at DESC
                ) t
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
                """,
                (kb_uid, limit, offset),
            )
            rows = cursor.fetchall() or []

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "count": len(rows),
        "items": rows,
        "limit": limit,
        "offset": offset,
    }


async def get_medical_kb_stats(
    api: Any, *, user_id: Any, global_kb: bool, request: Any
) -> dict[str, Any]:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    kb_uid = api._GLOBAL_KB_USER_ID if global_kb else uid

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                """
                SELECT
                    COUNT(1) AS docs,
                    COALESCE(SUM(chunk_count), 0) AS chunks,
                    MAX(updated_at) AS last_updated
                FROM rag_documents
                WHERE user_id = %s AND source_type = 'medical_kb'
                """,
                (kb_uid,),
            )
            total = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT embedding_model, COUNT(1) AS docs
                FROM rag_documents
                WHERE user_id = %s AND source_type = 'medical_kb'
                GROUP BY embedding_model
                ORDER BY COUNT(1) DESC
                """,
                (kb_uid,),
            )
            models = cursor.fetchall() or []

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "docs": int(total.get("docs") or 0),
        "chunks": int(total.get("chunks") or 0),
        "last_updated": total.get("last_updated"),
        "models": models,
    }


async def delete_medical_kb_doc(
    api: Any, *, doc_id: str, user_id: Any, global_kb: bool, request: Any
) -> dict[str, Any]:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    kb_uid = api._GLOBAL_KB_USER_ID if global_kb else uid
    did = (doc_id or "").strip()
    if not did:
        raise api.HTTPException(status_code=400, detail="doc_id不能为空")

    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                api._ensure_rag_schema(cursor)
                cursor.execute(
                    """
                    DELETE FROM rag_documents
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                cursor.execute(
                    """
                    DELETE FROM rag_chunks
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                deleted = int(cursor.rowcount or 0)
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"删除知识库文档失败: {e}")

    return {
        "success": True,
        "doc_id": did,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "deleted_chunks": deleted,
    }
