from __future__ import annotations

import io
import json
import os
import zipfile
import uuid
from urllib.parse import urlparse
from xml.etree import ElementTree
from typing import Any

import anyio
import requests


def _decode_text_bytes(data: bytes) -> str:
    b = data or b""
    if not b:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    try:
        return b.decode("latin-1", errors="ignore")
    except Exception:
        return ""


def _extract_text_from_docx_bytes(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml_bytes = z.read("word/document.xml")
    except Exception:
        return ""

    try:
        root = ElementTree.fromstring(xml_bytes)
    except Exception:
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for p in root.findall(".//w:p", ns):
        texts: list[str] = []
        for t in p.findall(".//w:t", ns):
            if t.text:
                texts.append(t.text)
        s = "".join(texts).strip()
        if s:
            paragraphs.append(s)
    return "\n\n".join(paragraphs).strip()


def _extract_text_from_pdf_bytes(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        raise RuntimeError("缺少依赖 pypdf，请安装后再上传 PDF")

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in getattr(reader, "pages", []) or []:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = (t or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def _extract_text_from_upload(data: bytes, filename: str) -> str:
    name = (filename or "").strip().lower()
    if name.endswith(".pdf"):
        return _extract_text_from_pdf_bytes(data)
    if name.endswith(".docx"):
        return _extract_text_from_docx_bytes(data)
    if name.endswith(".txt") or name.endswith(".md"):
        return _decode_text_bytes(data).strip()
    raise ValueError("仅支持上传 PDF / DOCX / TXT / MD 文件")


def _get_json_path(data: Any, path: str) -> Any:
    cur = data
    for p in [x for x in (path or "").split(".") if x]:
        if isinstance(cur, dict):
            cur = cur.get(p)
            continue
        return None
    return cur


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

    embedding_ok = bool(inserted and int(inserted) > 0)
    warning = (
        None
        if embedding_ok
        else "嵌入生成失败或超时，未写入向量分块，暂时无法用于检索"
    )

    return {
        "success": True,
        "doc_id": doc_id,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "inserted_chunks": int(inserted or 0),
        "embedding_ok": embedding_ok,
        "warning": warning,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_upload_medical_kb_file(
    api: Any,
    *,
    file: Any,
    global_kb: bool,
    user_id: str | None,
    doc_id: str | None,
    doc_type: str | None,
    title: str | None,
    request: Any,
) -> dict[str, Any]:
    api._require_admin(request)

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    if bool(global_kb):
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (user_id or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    max_mb = int(os.environ.get("A2A_MEDICAL_KB_MAX_UPLOAD_MB") or "20")
    max_bytes = max(1, max_mb) * 1024 * 1024

    filename = (getattr(file, "filename", None) or "").strip()
    if not filename:
        raise api.HTTPException(status_code=400, detail="文件名为空")

    raw = await file.read()
    if not raw:
        raise api.HTTPException(status_code=400, detail="文件内容为空")
    if len(raw) > max_bytes:
        raise api.HTTPException(
            status_code=413, detail=f"文件过大，最大允许 {max_mb}MB"
        )

    try:
        content = _extract_text_from_upload(raw, filename)
    except ValueError as e:
        raise api.HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise api.HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise api.HTTPException(status_code=500, detail=f"解析文件失败: {e}")

    content = (content or "").strip()
    if not content:
        raise api.HTTPException(
            status_code=422,
            detail="未能从文件中提取到可用文本（PDF 可能是扫描件）",
        )

    doc_id2 = (doc_id or "").strip() or str(uuid.uuid4())
    doc_type2 = (doc_type or "").strip() or "medical_kb"
    title2 = (title or "").strip() or filename
    text = "\n".join([f"标题: {title2}", f"内容: {content}"]).strip()

    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                inserted = api._upsert_rag_document(
                    cursor,
                    user_id=kb_uid,
                    source_type="medical_kb",
                    source_id=doc_id2,
                    record_type=doc_type2,
                    title=title2,
                    text=text,
                )
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"知识库入库失败: {e}")

    embedding_ok = bool(inserted and int(inserted) > 0)
    warning = (
        None
        if embedding_ok
        else "嵌入生成失败或超时，未写入向量分块，暂时无法用于检索"
    )

    return {
        "success": True,
        "doc_id": doc_id2,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "title": title2,
        "filename": filename,
        "bytes": len(raw),
        "inserted_chunks": int(inserted or 0),
        "embedding_ok": embedding_ok,
        "warning": warning,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_import_medical_kb_from_api(
    api: Any, *, payload: Any, request: Any
) -> dict[str, Any]:
    api._require_admin(request)

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    if bool(getattr(payload, "global_kb", True)):
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (getattr(payload, "user_id", None) or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    url = (getattr(payload, "url", None) or "").strip()
    if not url:
        raise api.HTTPException(status_code=400, detail="url不能为空")
    pr = urlparse(url)
    if pr.scheme not in ("http", "https"):
        raise api.HTTPException(status_code=400, detail="仅支持 http/https url")

    allowed_hosts = [
        x.strip().lower()
        for x in (os.environ.get("A2A_KB_IMPORT_ALLOWED_HOSTS") or "").split(",")
        if x.strip()
    ]
    if allowed_hosts:
        host = (pr.hostname or "").strip().lower()
        if host not in allowed_hosts:
            raise api.HTTPException(status_code=403, detail="目标主机不在允许列表中")

    method = (getattr(payload, "method", None) or "GET").strip().upper()
    if method not in ("GET", "POST"):
        raise api.HTTPException(status_code=400, detail="method仅支持 GET/POST")

    headers = getattr(payload, "headers", None) or None
    params = getattr(payload, "params", None) or None
    body_json = getattr(payload, "body_json", None)
    timeout = float(getattr(payload, "timeout", None) or 20.0)

    def _do_request():
        return requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=body_json,
            timeout=timeout,
        )

    try:
        resp = await anyio.to_thread.run_sync(_do_request)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise api.HTTPException(status_code=502, detail=f"调用上游 API 失败: {e}")

    items_path = (getattr(payload, "items_path", None) or "").strip()
    if items_path:
        items = _get_json_path(data, items_path)
    else:
        items = data.get("items") if isinstance(data, dict) else data

    if isinstance(items, dict):
        items_list = [items]
    elif isinstance(items, list):
        items_list = items
    else:
        items_list = [items]

    max_items = int(getattr(payload, "max_items", None) or 50)
    doc_type = (getattr(payload, "doc_type", None) or "").strip() or "medical_kb"
    doc_id_field = (getattr(payload, "doc_id_field", None) or "").strip()
    title_field = (getattr(payload, "title_field", None) or "").strip()
    content_field = (getattr(payload, "content_field", None) or "").strip()
    content_fields = getattr(payload, "content_fields", None) or []
    content_fields = [str(x).strip() for x in content_fields if str(x).strip()]

    results: list[dict[str, Any]] = []
    total_chunks = 0
    ingested = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            for i, item in enumerate(items_list[:max_items]):
                doc_id_val = ""
                title_val = ""
                content_val = ""
                if isinstance(item, dict):
                    if doc_id_field:
                        doc_id_val = str(item.get(doc_id_field) or "").strip()
                    if title_field:
                        title_val = str(item.get(title_field) or "").strip()
                    if content_field:
                        content_val = str(item.get(content_field) or "").strip()
                    elif content_fields:
                        parts: list[str] = []
                        for f in content_fields:
                            v = item.get(f)
                            if v is None:
                                continue
                            s = str(v).strip()
                            if s:
                                parts.append(f"{f}: {s}")
                        content_val = "\n".join(parts).strip()
                    else:
                        content_val = json.dumps(item, ensure_ascii=False, indent=2)
                else:
                    content_val = str(item).strip()

                doc_id2 = doc_id_val or str(uuid.uuid4())
                title2 = title_val or f"API导入-{i+1}"
                content2 = (content_val or "").strip()
                if not content2:
                    results.append(
                        {"success": False, "doc_id": doc_id2, "error": "内容为空"}
                    )
                    continue

                text = "\n".join([f"标题: {title2}", f"内容: {content2}"]).strip()
                try:
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=kb_uid,
                        source_type="medical_kb",
                        source_id=doc_id2,
                        record_type=doc_type,
                        title=title2,
                        text=text,
                    )
                    conn.commit()
                    inserted_i = int(inserted or 0)
                    if inserted_i > 0:
                        total_chunks += inserted_i
                        ingested += 1
                        results.append(
                            {
                                "success": True,
                                "doc_id": doc_id2,
                                "inserted_chunks": inserted_i,
                            }
                        )
                    else:
                        results.append(
                            {
                                "success": False,
                                "doc_id": doc_id2,
                                "error": "嵌入生成失败或超时，未写入向量分块",
                            }
                        )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append({"success": False, "doc_id": doc_id2, "error": str(e)})

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "requested": len(items_list[:max_items]),
        "ingested": ingested,
        "inserted_chunks": total_chunks,
        "docs": results,
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
