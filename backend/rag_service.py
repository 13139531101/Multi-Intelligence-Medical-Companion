from __future__ import annotations

from datetime import datetime
from typing import Any

import anyio


async def backfill_rag(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    uid = api._resolve_user_id(request, getattr(payload, "user_id", None))
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500, detail="EmbeddingService不可用，无法回填RAG"
        )

    source_types = [
        str(x).strip()
        for x in (getattr(payload, "source_types", None) or [])
        if str(x).strip()
    ]
    if not source_types:
        raise api.HTTPException(status_code=400, detail="source_types不能为空")

    limit = int(getattr(payload, "limit", None) or 200)
    offset = int(getattr(payload, "offset", None) or 0)

    summary_filter = (
        "" if getattr(payload, "include_deleted", False) else " AND COALESCE(is_deleted, 0) = 0"
    )

    result: dict[str, Any] = {
        "success": True,
        "user_id": uid,
        "source_types": source_types,
        "limit": limit,
        "offset": offset,
        "dry_run": bool(getattr(payload, "dry_run", False)),
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
        "processed_docs": 0,
        "inserted_chunks": 0,
        "per_source": {},
        "errors": [],
    }

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            for st in source_types:
                st_key = st
                per: dict[str, Any] = {
                    "source_type": st_key,
                    "processed_docs": 0,
                    "inserted_chunks": 0,
                    "errors": [],
                }

                try:
                    if st_key == "health_records":
                        cursor.execute(
                            """
                            SELECT id, record_type, title, summary, content
                            FROM health_records
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            (uid, limit, offset),
                        )
                        rows = cursor.fetchall() or []
                        for r in rows:
                            try:
                                doc_id = str(r.get("id"))
                                record_type = r.get("record_type")
                                title = r.get("title")
                                text = api._make_rag_text(
                                    title, r.get("summary"), r.get("content")
                                )
                                per["processed_docs"] += 1
                                result["processed_docs"] += 1
                                if getattr(payload, "dry_run", False):
                                    continue
                                inserted = api._upsert_rag_document(
                                    cursor,
                                    user_id=uid,
                                    source_type="health_records",
                                    source_id=doc_id,
                                    record_type=(
                                        str(record_type)
                                        if record_type is not None
                                        else None
                                    ),
                                    title=title,
                                    text=text,
                                )
                                conn.commit()
                                per["inserted_chunks"] += int(inserted or 0)
                                result["inserted_chunks"] += int(inserted or 0)
                            except Exception as e:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                                msg = f"health_records:{r.get('id')}: {e}"
                                per["errors"].append(msg)
                                result["errors"].append(msg)

                    elif st_key == "visit_summaries":
                        cursor.execute(
                            f"""
                            SELECT
                                id, title, visit_date, doctor, hospital, department,
                                chief_complaint, symptoms, examination, diagnosis,
                                treatment, prescription, follow_up, summary_content, notes
                            FROM visit_summaries
                            WHERE user_id = %s{summary_filter}
                            ORDER BY created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            (uid, limit, offset),
                        )
                        rows = cursor.fetchall() or []
                        for r in rows:
                            try:
                                doc_id = str(r.get("id"))
                                title = r.get("title")
                                text = "\n".join(
                                    [
                                        f"标题: {title or ''}",
                                        f"就诊日期: {r.get('visit_date') or ''}",
                                        f"医院: {r.get('hospital') or ''}",
                                        f"科室: {r.get('department') or ''}",
                                        f"医生: {r.get('doctor') or ''}",
                                        f"主诉: {r.get('chief_complaint') or ''}",
                                        f"症状: {r.get('symptoms') or ''}",
                                        f"检查: {r.get('examination') or ''}",
                                        f"诊断: {r.get('diagnosis') or ''}",
                                        f"治疗: {r.get('treatment') or ''}",
                                        f"处方: {r.get('prescription') or ''}",
                                        f"复查/随访: {r.get('follow_up') or ''}",
                                        f"摘要: {r.get('summary_content') or ''}",
                                        f"备注: {r.get('notes') or ''}",
                                    ]
                                ).strip()
                                per["processed_docs"] += 1
                                result["processed_docs"] += 1
                                if getattr(payload, "dry_run", False):
                                    continue
                                inserted = api._upsert_rag_document(
                                    cursor,
                                    user_id=uid,
                                    source_type="visit_summaries",
                                    source_id=doc_id,
                                    record_type="visit_summary",
                                    title=title,
                                    text=text,
                                )
                                conn.commit()
                                per["inserted_chunks"] += int(inserted or 0)
                                result["inserted_chunks"] += int(inserted or 0)
                            except Exception as e:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                                msg = f"visit_summaries:{r.get('id')}: {e}"
                                per["errors"].append(msg)
                                result["errors"].append(msg)
                    else:
                        per["errors"].append(f"unknown source_type: {st_key}")
                        result["errors"].append(f"unknown source_type: {st_key}")
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    msg = f"{st_key}: {e}"
                    per["errors"].append(msg)
                    result["errors"].append(msg)

                result["per_source"][st_key] = per

    return result


async def admin_backfill_rag(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    uid = (getattr(payload, "user_id", None) or "").strip()
    if not uid:
        raise api.HTTPException(status_code=400, detail="user_id不能为空")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500, detail="EmbeddingService不可用，无法回填RAG"
        )

    source_types = [
        str(x).strip()
        for x in (getattr(payload, "source_types", None) or [])
        if str(x).strip()
    ]
    if not source_types:
        raise api.HTTPException(status_code=400, detail="source_types不能为空")

    limit = int(getattr(payload, "limit", None) or 200)
    offset = int(getattr(payload, "offset", None) or 0)

    summary_filter = (
        ""
        if getattr(payload, "include_deleted", False)
        else " AND COALESCE(is_deleted, 0) = 0"
    )

    result: dict[str, Any] = {
        "success": True,
        "user_id": uid,
        "source_types": source_types,
        "limit": limit,
        "offset": offset,
        "dry_run": bool(getattr(payload, "dry_run", False)),
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
        "processed_docs": 0,
        "inserted_chunks": 0,
        "per_source": {},
        "errors": [],
    }

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            for st in source_types:
                st_key = st
                per: dict[str, Any] = {
                    "source_type": st_key,
                    "processed_docs": 0,
                    "inserted_chunks": 0,
                    "errors": [],
                }

                try:
                    if st_key == "health_records":
                        cursor.execute(
                            """
                            SELECT id, record_type, title, summary, content
                            FROM health_records
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            (uid, limit, offset),
                        )
                        rows = cursor.fetchall() or []
                        for r in rows:
                            try:
                                doc_id = str(r.get("id"))
                                record_type = r.get("record_type")
                                title = r.get("title")
                                text = api._make_rag_text(
                                    title, r.get("summary"), r.get("content")
                                )
                                per["processed_docs"] += 1
                                result["processed_docs"] += 1
                                if result["dry_run"]:
                                    continue
                                inserted = api._upsert_rag_document(
                                    cursor,
                                    user_id=uid,
                                    source_type="health_records",
                                    source_id=doc_id,
                                    record_type=record_type,
                                    title=title,
                                    text=text,
                                )
                                conn.commit()
                                per["inserted_chunks"] += int(inserted or 0)
                                result["inserted_chunks"] += int(inserted or 0)
                            except Exception as e:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                                msg = f"health_records:{r.get('id')}: {e}"
                                per["errors"].append(msg)
                                result["errors"].append(msg)
                    elif st_key == "visit_summaries":
                        cursor.execute(
                            f"""
                            SELECT id, summary_title, summary_text
                            FROM visit_summaries
                            WHERE user_id = %s {summary_filter}
                            ORDER BY created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            (uid, limit, offset),
                        )
                        rows = cursor.fetchall() or []
                        for r in rows:
                            try:
                                doc_id = str(r.get("id"))
                                title = r.get("summary_title")
                                text = api._make_rag_text(title, "", r.get("summary_text"))
                                per["processed_docs"] += 1
                                result["processed_docs"] += 1
                                if result["dry_run"]:
                                    continue
                                inserted = api._upsert_rag_document(
                                    cursor,
                                    user_id=uid,
                                    source_type="visit_summaries",
                                    source_id=doc_id,
                                    record_type="visit_summary",
                                    title=title,
                                    text=text,
                                )
                                conn.commit()
                                per["inserted_chunks"] += int(inserted or 0)
                                result["inserted_chunks"] += int(inserted or 0)
                            except Exception as e:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                                msg = f"visit_summaries:{r.get('id')}: {e}"
                                per["errors"].append(msg)
                                result["errors"].append(msg)
                    else:
                        per["errors"].append(f"unknown source_type: {st_key}")
                        result["errors"].append(f"unknown source_type: {st_key}")
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    msg = f"{st_key}: {e}"
                    per["errors"].append(msg)
                    result["errors"].append(msg)

                result["per_source"][st_key] = per

    return result


async def admin_monitor_summary(api: Any, *, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    db_ok = False
    db_error = ""
    try:
        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = True
    except Exception as e:
        db_ok = False
        db_error = str(e)

    es = api._get_embedding_service()
    embedding = {
        "available": es is not None,
        "model": getattr(es, "model_name", None) if es is not None else None,
        "dimension": getattr(es, "dimension", None) if es is not None else None,
    }

    system: dict[str, Any] = {"available": getattr(api, "psutil", None) is not None}
    if getattr(api, "psutil", None) is not None:
        try:
            vm = api.psutil.virtual_memory()
            du = api.psutil.disk_usage(api.os.getcwd())
            system.update(
                {
                    "cpu_percent": float(api.psutil.cpu_percent(interval=0.05)),
                    "mem_percent": float(vm.percent),
                    "mem_used": int(vm.used),
                    "mem_total": int(vm.total),
                    "disk_percent": float(du.percent),
                    "disk_used": int(du.used),
                    "disk_total": int(du.total),
                }
            )
        except Exception:
            pass

    rag: dict[str, Any] = {
        "vector_dim": getattr(api, "_RAG_VECTOR_DIM", None),
        "embedding_model": getattr(api, "_RAG_EMBEDDING_MODEL", None),
        "source_types": ["health_records", "visit_summaries", "medical_kb"],
    }
    try:
        rag["chunk_mode"] = str(api._rag_chunk_mode())
    except Exception:
        rag["chunk_mode"] = str(api.os.getenv("RAG_CHUNK_MODE", "") or "").strip() or "sliding"
    try:
        rag["chunk_mode_medical_kb"] = str(api._rag_chunk_mode_for_source("medical_kb"))
    except Exception:
        rag["chunk_mode_medical_kb"] = "paragraph"
    try:
        st = api._rag_chunk_settings()
        rag.update(
            {
                "chunk_size": int(st.get("chunk_size") or 0),
                "chunk_overlap": int(st.get("overlap") or 0),
                "max_chunks": int(st.get("max_chunks") or 0),
            }
        )
    except Exception:
        try:
            rag["chunk_size"] = int(api.os.getenv("RAG_CHUNK_SIZE", "650"))
        except Exception:
            rag["chunk_size"] = 650
        try:
            rag["chunk_overlap"] = int(api.os.getenv("RAG_CHUNK_OVERLAP", "120"))
        except Exception:
            rag["chunk_overlap"] = 120
        try:
            rag["max_chunks"] = int(api.os.getenv("RAG_MAX_CHUNKS", "0"))
        except Exception:
            rag["max_chunks"] = 0

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "db": {"ok": db_ok, "error": db_error},
        "embedding": embedding,
        "system": system,
        "rag": rag,
    }


async def admin_monitor_check(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    targets = getattr(payload, "targets", None) or []
    timeout = float(getattr(payload, "timeout", None) or 1.5)
    results: list[dict[str, Any]] = []
    for t in targets:
        results.append(await anyio.to_thread.run_sync(api._probe_target, t, timeout))
    ok_count = sum(1 for r in results if r.get("ok"))
    return {"success": True, "count": len(results), "ok": ok_count, "items": results}


async def admin_list_rag_docs(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    uid = (getattr(payload, "user_id", None) or "").strip()
    st = (getattr(payload, "source_type", None) or "").strip()
    q = (getattr(payload, "q", None) or "").strip()
    limit = int(getattr(payload, "limit", None) or 50)
    offset = int(getattr(payload, "offset", None) or 0)

    where = ["1=1"]
    params: list[Any] = []
    if uid:
        where.append("user_id = %s")
        params.append(uid)
    if st:
        where.append("source_type = %s")
        params.append(st)
    if q:
        where.append("(source_id ILIKE %s OR COALESCE(title, '') ILIKE %s)")
        like = f"%{q}%"
        params.extend([like, like])

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            try:
                api._ensure_rag_schema(cursor)
                cursor.execute(
                    f"""
                    SELECT
                        user_id,
                        source_type,
                        source_id,
                        record_type,
                        title,
                        chunk_count,
                        embedding_model,
                        embedding_dim,
                        created_at,
                        updated_at
                    FROM rag_documents
                    WHERE {' AND '.join(where)}
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params + [limit, offset]),
                )
                rows = cursor.fetchall() or []
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"RAG 查询失败: {e}")

    return {"success": True, "count": len(rows), "items": rows, "limit": limit, "offset": offset}


async def admin_list_rag_chunks(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    uid = (getattr(payload, "user_id", None) or "").strip()
    st = (getattr(payload, "source_type", None) or "").strip()
    sid = (getattr(payload, "source_id", None) or "").strip()
    if not uid or not st or not sid:
        raise api.HTTPException(status_code=400, detail="user_id/source_type/source_id不能为空")

    limit = int(getattr(payload, "limit", None) or 200)
    offset = int(getattr(payload, "offset", None) or 0)

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    source_type,
                    source_id,
                    record_type,
                    title,
                    chunk_index,
                    chunk_text,
                    embedding_model,
                    embedding_dim,
                    created_at,
                    updated_at
                FROM rag_chunks
                WHERE user_id = %s AND source_type = %s AND source_id = %s
                ORDER BY chunk_index ASC
                LIMIT %s OFFSET %s
                """,
                (uid, st, sid, limit, offset),
            )
            rows = cursor.fetchall() or []

    return {"success": True, "count": len(rows), "items": rows, "limit": limit, "offset": offset}


async def admin_rag_search(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    q = (getattr(payload, "query", None) or "").strip()
    if not q:
        raise api.HTTPException(status_code=400, detail="query不能为空")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(status_code=500, detail="EmbeddingService不可用")

    q_emb = es.generate_embedding(q)
    if not q_emb or len(q_emb) != api._RAG_VECTOR_DIM:
        raise api.HTTPException(status_code=500, detail="Embedding维度不匹配")

    uid = (getattr(payload, "user_id", None) or "").strip()
    include_global = bool(getattr(payload, "include_global", True))
    uids: list[str] = []
    if uid:
        uids.append(uid)
    if include_global and api._GLOBAL_KB_USER_ID not in uids:
        uids.append(api._GLOBAL_KB_USER_ID)
    if not uids:
        raise api.HTTPException(status_code=400, detail="user_id为空且include_global为false")

    st = [str(x).strip() for x in (getattr(payload, "source_types", None) or []) if str(x).strip()]
    if not st:
        st = ["medical_kb"]

    placeholders_st = ",".join(["%s"] * len(st))
    where_uid = "(" + " OR ".join(["user_id = %s"] * len(uids)) + ")"
    qv = api._vector_literal(q_emb)

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                f"""
                SELECT
                    user_id,
                    source_type,
                    source_id,
                    record_type,
                    COALESCE(title, '') AS title,
                    COALESCE(chunk_text, '') AS chunk_text,
                    score,
                    created_at,
                    updated_at
                FROM (
                    SELECT
                        user_id,
                        source_type,
                        source_id,
                        record_type,
                        title,
                        chunk_text,
                        1 - (embedding <=> {qv}::vector) AS score,
                        (embedding <=> {qv}::vector) AS distance,
                        created_at,
                        updated_at,
                        row_number() OVER (
                            PARTITION BY user_id, source_type, source_id
                            ORDER BY (embedding <=> {qv}::vector) ASC
                        ) AS rn
                    FROM rag_chunks
                    WHERE {where_uid}
                      AND source_type IN ({placeholders_st})
                ) t
                WHERE rn = 1
                ORDER BY distance ASC
                LIMIT %s
                """,
                tuple(uids + st + [int(getattr(payload, "limit", None) or 10)]),
            )
            rows = cursor.fetchall() or []

    return {
        "success": True,
        "query": q,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
        "count": len(rows),
        "items": rows,
    }


async def admin_rag_reindex(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    uid = (getattr(payload, "user_id", None) or "").strip()
    st = (getattr(payload, "source_type", None) or "").strip()
    sid = (getattr(payload, "source_id", None) or "").strip()
    if not uid or not st or not sid:
        raise api.HTTPException(status_code=400, detail="user_id/source_type/source_id不能为空")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(status_code=500, detail="EmbeddingService不可用")

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                """
                SELECT record_type, title, full_text
                FROM rag_documents
                WHERE user_id = %s AND source_type = %s AND source_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (uid, st, sid),
            )
            row = cursor.fetchone()
            if not row:
                raise api.HTTPException(status_code=404, detail="未找到RAG文档")

            inserted = api._upsert_rag_document(
                cursor,
                user_id=uid,
                source_type=st,
                source_id=sid,
                record_type=row.get("record_type"),
                title=row.get("title"),
                text=row.get("full_text") or "",
            )
            conn.commit()

    return {
        "success": True,
        "user_id": uid,
        "source_type": st,
        "source_id": sid,
        "inserted_chunks": int(inserted or 0),
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_rag_reindex_bulk(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    uid = (getattr(payload, "user_id", None) or "").strip()
    st = (getattr(payload, "source_type", None) or "").strip()
    if not uid or not st:
        raise api.HTTPException(status_code=400, detail="user_id/source_type不能为空")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(status_code=500, detail="EmbeddingService不可用")

    source_ids = [str(x).strip() for x in (getattr(payload, "source_ids", None) or []) if str(x).strip()]
    limit = int(getattr(payload, "limit", None) or 2000)

    results: list[dict[str, Any]] = []
    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            if not source_ids:
                cursor.execute(
                    """
                    SELECT source_id
                    FROM rag_documents
                    WHERE user_id = %s AND source_type = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (uid, st, limit),
                )
                rows = cursor.fetchall() or []
                source_ids = [str(r.get("source_id") or "") for r in rows if r.get("source_id")]

            for sid in source_ids:
                try:
                    cursor.execute(
                        """
                        SELECT record_type, title, full_text
                        FROM rag_documents
                        WHERE user_id = %s AND source_type = %s AND source_id = %s
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (uid, st, sid),
                    )
                    row = cursor.fetchone()
                    if not row:
                        results.append({"source_id": sid, "success": False, "error": "未找到RAG文档"})
                        continue
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type=st,
                        source_id=sid,
                        record_type=row.get("record_type"),
                        title=row.get("title"),
                        text=row.get("full_text") or "",
                    )
                    conn.commit()
                    results.append(
                        {"source_id": sid, "success": True, "inserted_chunks": int(inserted or 0)}
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append({"source_id": sid, "success": False, "error": str(e)})

    return {
        "success": True,
        "user_id": uid,
        "source_type": st,
        "count": len(results),
        "items": results,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }
