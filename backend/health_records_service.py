from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import anyio
from fastapi import HTTPException, Request, UploadFile


async def get_health_records(
    api: Any,
    *,
    skip: int,
    limit: int,
    record_type: Any,
    importance: Any,
    search: str | None,
    start_date: date | None,
    end_date: date | None,
    user_id: str | None,
    request: Request | None,
):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                conditions = []
                params = []
                uid = api._resolve_user_id(request, user_id)
                if uid:
                    conditions.append("user_id = %s")
                    params.append(uid)
                if record_type:
                    conditions.append("record_type = %s")
                    params.append(record_type.value)
                if importance:
                    conditions.append("importance = %s")
                    params.append(importance.value)
                if search:
                    conditions.append(
                        "(title ILIKE %s OR summary ILIKE %s OR content ILIKE %s)"
                    )
                    sp = f"%{search}%"
                    params.extend([sp, sp, sp])
                if start_date:
                    conditions.append("record_date >= %s")
                    params.append(start_date)
                if end_date:
                    conditions.append("record_date <= %s")
                    params.append(end_date)
                where_clause = (
                    " AND ".join(conditions) if conditions else "TRUE"
                )
                query = f"""
                    SELECT * FROM health_records
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, skip])
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [api.row_to_health_record(row) for row in rows]
    except Exception as e:
        api.logger.error(f"获取健康档案列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_health_record(
    api: Any,
    *,
    record_id: str,
    user_id: str | None,
    request: Request | None,
):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                uid = api._resolve_user_id(request, user_id)
                if uid:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, uid),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s",
                        (record_id,),
                    )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=404, detail="健康档案不存在或无权限访问"
                    )
                return api.row_to_health_record(row)
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"获取健康档案详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def create_health_record(
    api: Any,
    *,
    record: Any,
    user_id: str | None,
    request: Request | None,
):
    try:
        file_ids: list[str] = []
        try:
            if isinstance(record.metadata, dict):
                mfiles = record.metadata.get("files") or record.metadata.get(
                    "uploaded_files"
                )
                if isinstance(mfiles, list):
                    file_ids.extend(
                        [str(x) for x in mfiles if isinstance(x, (str, int))]
                    )
            if isinstance(record.files, list):
                file_ids.extend(
                    [str(x) for x in record.files if isinstance(x, (str, int))]
                )
        except Exception:
            pass

        record_id = api.generate_id()
        now = datetime.now()
        uid = api._resolve_user_id(request, user_id)

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                target_existing_id = None
                if file_ids:
                    placeholders = ",".join(["%s"] * len(file_ids))
                    try:
                        cursor.execute(
                            f"SELECT record_id FROM file_attachments WHERE id IN ({placeholders})",
                            tuple(file_ids),
                        )
                        existing_links = [
                            r[0] for r in cursor.fetchall() if r and r[0]
                        ]
                        if existing_links:
                            cursor.execute(
                                "SELECT id, user_id, metadata, content FROM health_records WHERE id = %s",
                                (existing_links[0],),
                            )
                            linked = cursor.fetchone()
                            if linked and (
                                not user_id or str(linked[1]) == str(user_id)
                            ):
                                target_existing_id = linked[0]
                                try:
                                    old_meta = (
                                        linked[2]
                                        if isinstance(linked[2], dict)
                                        else {}
                                    )
                                except Exception:
                                    old_meta = {}
                                new_meta = record.metadata or {}
                                merged_meta = {
                                    **(old_meta or {}),
                                    **(new_meta or {}),
                                }
                                merged_meta = api._prepare_metadata_with_tests(
                                    record.content
                                    or record.summary
                                    or linked[3]
                                    or "",
                                    merged_meta,
                                )
                                update_fields = [
                                    "title = %s",
                                    "record_type = %s",
                                    "summary = %s",
                                    "importance = %s",
                                    "tags = %s",
                                    "metadata = %s",
                                    "record_date = %s",
                                    "updated_at = %s",
                                ]
                                params = [
                                    record.title,
                                    record.record_type.value,
                                    record.summary,
                                    record.importance.value,
                                    api.Json(record.tags or []),
                                    api.Json(merged_meta),
                                    record.record_date,
                                    now,
                                ]
                                cursor.execute(
                                    f"UPDATE health_records SET {', '.join(update_fields)} WHERE id = %s",
                                    tuple(params + [target_existing_id]),
                                )
                                conn.commit()
                                cursor.execute(
                                    "SELECT * FROM health_records WHERE id = %s",
                                    (target_existing_id,),
                                )
                                row = cursor.fetchone()
                                return api.row_to_health_record(row)
                    except Exception:
                        pass

                try:
                    content_empty = (record.content is None) or (
                        isinstance(record.content, str)
                        and record.content.strip() == ""
                    )
                    summary_empty = (record.summary is None) or (
                        isinstance(record.summary, str)
                        and record.summary.strip() == ""
                    )
                    no_files = not file_ids
                    if content_empty and summary_empty and no_files:
                        cursor.execute(
                            """
                            SELECT * FROM health_records
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                            (uid,),
                        )
                        recent = cursor.fetchone()

                        def _has_ocr_marks(r: dict | None) -> bool:
                            if not r:
                                return False
                            try:
                                md = r.get("metadata")
                                if isinstance(md, str):
                                    md = api.deserialize_metadata(md)
                                if isinstance(md, dict):
                                    if (
                                        md.get("uploaded_files")
                                        or md.get("file_id")
                                        or md.get("ocr_info")
                                    ):
                                        return True
                                tags_v = r.get("tags")
                                if isinstance(tags_v, str):
                                    tags_v = api.deserialize_tags(tags_v)
                                return isinstance(tags_v, list) and (
                                    "ocr" in tags_v or "auto_import" in tags_v
                                )
                            except Exception:
                                return False

                        def _within_minutes(
                            r: dict | None, minutes: int = 10
                        ) -> bool:
                            if not r:
                                return False
                            try:
                                created_at = r.get("created_at")
                                if isinstance(created_at, str):
                                    created_dt = datetime.fromisoformat(
                                        created_at
                                    )
                                else:
                                    created_dt = created_at
                                return (
                                    datetime.now() - created_dt
                                ).total_seconds() <= minutes * 60
                            except Exception:
                                return False

                        if (
                            recent
                            and _has_ocr_marks(recent)
                            and _within_minutes(recent, 10)
                        ):
                            try:
                                merged_meta: dict = {}
                                try:
                                    old_meta = recent.get("metadata")
                                    if isinstance(old_meta, str):
                                        old_meta = api.deserialize_metadata(
                                            old_meta
                                        )
                                    if isinstance(old_meta, dict):
                                        merged_meta.update(old_meta)
                                except Exception:
                                    pass
                                if isinstance(record.metadata, dict):
                                    merged_meta.update(record.metadata)
                                merged_meta = api._prepare_metadata_with_tests(
                                    record.content
                                    or record.summary
                                    or recent.get("content")
                                    or recent.get("summary")
                                    or "",
                                    merged_meta,
                                )
                                update_fields = [
                                    "title = %s",
                                    "record_type = %s",
                                    "summary = %s",
                                    "importance = %s",
                                    "tags = %s",
                                    "metadata = %s",
                                    "record_date = %s",
                                    "updated_at = %s",
                                ]
                                params = [
                                    record.title,
                                    record.record_type.value,
                                    recent.get("summary"),
                                    record.importance.value,
                                    api.Json(record.tags or []),
                                    api.Json(merged_meta),
                                    record.record_date,
                                    now,
                                ]
                                cursor.execute(
                                    f"UPDATE health_records SET {', '.join(update_fields)} WHERE id = %s",
                                    tuple(params + [recent.get("id")]),
                                )
                                conn.commit()
                                cursor.execute(
                                    "SELECT * FROM health_records WHERE id = %s",
                                    (recent.get("id"),),
                                )
                                row = cursor.fetchone()
                                api.logger.info(
                                    f"create dedup merged into recent id={recent.get('id')} user_id={uid}"
                                )
                                return api.row_to_health_record(row)
                            except Exception:
                                pass
                except Exception:
                    pass

                record.metadata = api._prepare_metadata_with_tests(
                    record.content or record.summary, record.metadata
                )
                cursor.execute(
                    """
                    INSERT INTO health_records (
                        id, user_id, title, record_type, summary, content, importance,
                        tags, metadata, record_date, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record_id,
                        uid,
                        record.title,
                        record.record_type.value,
                        record.summary,
                        record.content,
                        record.importance.value,
                        api.Json(record.tags or []),
                        api.Json(record.metadata or {}),
                        record.record_date,
                        now,
                        now,
                    ),
                )
                if file_ids:
                    placeholders = ",".join(["%s"] * len(file_ids))
                    cursor.execute(
                        f"""
                        UPDATE file_attachments
                        SET record_id = %s
                        WHERE id IN ({placeholders})
                          AND record_id IS NULL
                        """,
                        tuple([record_id] + file_ids),
                    )
                conn.commit()
                cursor.execute(
                    "SELECT * FROM health_records WHERE id = %s", (record_id,)
                )
                row = cursor.fetchone()
                created = api.row_to_health_record(row)
                try:
                    text = api._make_rag_text(
                        created.title, created.summary, created.content
                    )
                    rt = (
                        created.record_type.value
                        if hasattr(created.record_type, "value")
                        else str(created.record_type)
                    )
                    api._upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type="health_records",
                        source_id=str(created.id),
                        record_type=rt,
                        title=created.title,
                        text=text,
                    )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    api.logger.warning(f"创建记录后RAG入库失败：{e}")

                try:
                    api._save_to_hrm(
                        user_id=uid,
                        record_type=created.record_type,
                        title=created.title,
                        content=created.content or (created.summary or ""),
                        extracted_data=created.metadata or {},
                    )
                except Exception as e:
                    api.logger.warning(f"创建记录后HRM双写失败：{e}")

                try:
                    if api.health_records_memory_service is not None:
                        if (
                            not api.health_records_memory_service.is_available()
                        ):
                            await api.health_records_memory_service.initialize()
                        imp_map = {
                            "low": 0.2,
                            "medium": 0.5,
                            "high": 0.8,
                            "critical": 1.0,
                        }
                        imp_key = (
                            created.importance.value
                            if hasattr(created.importance, "value")
                            else str(created.importance)
                        )
                        imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                        await api.health_records_memory_service.store_health_record(
                            user_id=uid,
                            record_type=created.record_type,
                            record_data={
                                "id": created.id,
                                "title": created.title,
                                "content": created.content,
                                "metadata": created.metadata or {},
                                "record_date": (
                                    str(created.record_date)
                                    if created.record_date
                                    else None
                                ),
                            },
                            summary=created.summary or "",
                            importance=imp_val,
                            tags=created.tags or [],
                        )
                except Exception as e:
                    api.logger.warning(f"创建记录后写入记忆失败：{e}")

                return created

    except Exception as e:
        api.logger.error(f"创建健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def update_health_record(
    api: Any,
    *,
    record_id: str,
    record_update: Any,
    user_id: str | None,
    request: Request | None,
):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                uid = api._resolve_user_id(request, user_id)
                if user_id:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, user_id),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s",
                        (record_id,),
                    )
                existing_record = cursor.fetchone()
                if not existing_record:
                    raise HTTPException(
                        status_code=404, detail="健康档案不存在或无权限访问"
                    )

                update_fields = []
                params = []

                if record_update.title is not None:
                    update_fields.append("title = %s")
                    params.append(record_update.title)

                if record_update.record_type is not None:
                    update_fields.append("record_type = %s")
                    params.append(record_update.record_type.value)

                if record_update.summary is not None:
                    update_fields.append("summary = %s")
                    params.append(record_update.summary)

                if record_update.content is not None:
                    update_fields.append("content = %s")
                    params.append(record_update.content)

                if record_update.importance is not None:
                    update_fields.append("importance = %s")
                    params.append(record_update.importance.value)

                if record_update.tags is not None:
                    update_fields.append("tags = %s")
                    params.append(api.Json(record_update.tags))

                existing_meta = existing_record.get("metadata")
                if isinstance(existing_meta, str):
                    existing_meta = api.deserialize_metadata(existing_meta)
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                incoming_meta = (
                    record_update.metadata
                    if isinstance(record_update.metadata, dict)
                    else None
                )
                file_ids: list[str] = []
                if isinstance(incoming_meta, dict):
                    mfiles = incoming_meta.get("files") or incoming_meta.get(
                        "uploaded_files"
                    )
                    if isinstance(mfiles, list):
                        file_ids.extend(
                            [
                                str(x)
                                for x in mfiles
                                if isinstance(x, (str, int))
                            ]
                        )

                if record_update.record_date is not None:
                    update_fields.append("record_date = %s")
                    params.append(record_update.record_date)

                if (
                    record_update.metadata is not None
                    or record_update.content is not None
                    or record_update.summary is not None
                ):
                    merged_meta = (
                        {**existing_meta, **incoming_meta}
                        if incoming_meta is not None
                        else dict(existing_meta)
                    )
                    content_for_extract = record_update.content
                    if content_for_extract is None:
                        content_for_extract = existing_record.get("content")
                    if not content_for_extract:
                        content_for_extract = record_update.summary
                    if not content_for_extract:
                        content_for_extract = existing_record.get("summary")
                    prepared_meta = api._prepare_metadata_with_tests(
                        content_for_extract, merged_meta
                    )
                    update_fields.append("metadata = %s")
                    params.append(api.Json(prepared_meta))

                if not update_fields:
                    return api.row_to_health_record(existing_record)

                update_fields.append("updated_at = %s")
                params.append(datetime.now())
                params.append(record_id)

                if user_id:
                    query = f"UPDATE health_records SET {', '.join(update_fields)} WHERE id = %s AND user_id = %s"
                    params.append(user_id)
                else:
                    query = f"UPDATE health_records SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, params)
                if file_ids:
                    placeholders = ",".join(["%s"] * len(file_ids))
                    cursor.execute(
                        f"""
                        UPDATE file_attachments
                        SET record_id = %s
                        WHERE id IN ({placeholders})
                          AND record_id IS NULL
                        """,
                        tuple([record_id] + file_ids),
                    )
                conn.commit()

                if user_id:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, user_id),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s",
                        (record_id,),
                    )
                row = cursor.fetchone()
                updated = api.row_to_health_record(row)

                try:
                    text = api._make_rag_text(
                        updated.title, updated.summary, updated.content
                    )
                    rt = (
                        updated.record_type.value
                        if hasattr(updated.record_type, "value")
                        else str(updated.record_type)
                    )
                    api._upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type="health_records",
                        source_id=str(updated.id),
                        record_type=rt,
                        title=updated.title,
                        text=text,
                    )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    api.logger.warning(f"更新记录后RAG入库失败：{e}")
                try:
                    api._save_to_hrm(
                        user_id=uid,
                        record_type=updated.record_type,
                        title=updated.title,
                        content=updated.content or (updated.summary or ""),
                        extracted_data=updated.metadata or {},
                    )
                except Exception as e:
                    api.logger.warning(f"更新记录后HRM双写失败：{e}")
                try:
                    if api.health_records_memory_service is not None:
                        if (
                            not api.health_records_memory_service.is_available()
                        ):
                            await api.health_records_memory_service.initialize()
                        mem_id = None
                        try:
                            meta = updated.metadata or {}
                            mem_id = meta.get("memory_id")
                        except Exception:
                            mem_id = None
                        if mem_id and getattr(
                            api.health_records_memory_service,
                            "memory_system",
                            None,
                        ):
                            try:
                                api.health_records_memory_service.memory_system.update_memory(
                                    memory_id=mem_id,
                                    content={
                                        "text": f"更新健康档案: {updated.title}",
                                        "structured_data": {
                                            "record_id": updated.id,
                                            "record_type": updated.record_type,
                                            "content": updated.content,
                                            "metadata": updated.metadata or {},
                                        },
                                    },
                                )
                            except Exception:
                                imp_map = {
                                    "low": 0.2,
                                    "medium": 0.5,
                                    "high": 0.8,
                                    "critical": 1.0,
                                }
                                imp_key = (
                                    updated.importance.value
                                    if hasattr(updated.importance, "value")
                                    else str(updated.importance)
                                )
                                imp_val = imp_map.get(
                                    str(imp_key).lower(), 0.5
                                )
                                await api.health_records_memory_service.store_health_record(
                                    user_id=uid,
                                    record_type=updated.record_type,
                                    record_data={
                                        "id": updated.id,
                                        "title": updated.title,
                                        "content": updated.content,
                                        "metadata": updated.metadata or {},
                                    },
                                    summary=updated.summary or "",
                                    importance=imp_val,
                                    tags=updated.tags or [],
                                )
                        else:
                            imp_map = {
                                "low": 0.2,
                                "medium": 0.5,
                                "high": 0.8,
                                "critical": 1.0,
                            }
                            imp_key = (
                                updated.importance.value
                                if hasattr(updated.importance, "value")
                                else str(updated.importance)
                            )
                            imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                            await api.health_records_memory_service.store_health_record(
                                user_id=uid,
                                record_type=updated.record_type,
                                record_data={
                                    "id": updated.id,
                                    "title": updated.title,
                                    "content": updated.content,
                                    "metadata": updated.metadata or {},
                                },
                                summary=updated.summary or "",
                                importance=imp_val,
                                tags=updated.tags or [],
                            )
                except Exception as e:
                    api.logger.warning(f"更新记录后写入记忆失败：{e}")
                return updated

    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"更新健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def delete_health_record(
    api: Any,
    *,
    record_id: str,
    user_id: str | None,
    request: Request | None,
):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                uid = api._resolve_user_id(request, user_id)
                if uid:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, uid),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s",
                        (record_id,),
                    )
                if not cursor.fetchone():
                    raise HTTPException(
                        status_code=404, detail="健康档案不存在或无权限访问"
                    )

                cursor.execute(
                    "SELECT file_path FROM file_attachments WHERE record_id = %s",
                    (record_id,),
                )
                file_paths = cursor.fetchall()
                for file_path_row in file_paths:
                    try:
                        fp = (
                            file_path_row["file_path"]
                            if isinstance(file_path_row, dict)
                            else file_path_row[0]
                        )
                        if fp:
                            file_path = Path(fp)
                            if file_path.exists():
                                file_path.unlink()
                    except Exception:
                        pass

                try:
                    cursor.execute(
                        "SELECT metadata FROM health_records WHERE id = %s",
                        (record_id,),
                    )
                    r = cursor.fetchone()
                    mem_id = None
                    try:
                        meta = (
                            api.deserialize_metadata(r[0])
                            if r and isinstance(r[0], str)
                            else (r[0] if r else {})
                        )
                        if isinstance(meta, dict):
                            mem_id = meta.get("memory_id")
                    except Exception:
                        mem_id = None
                    if (
                        mem_id
                        and api.health_records_memory_service
                        and api.health_records_memory_service.is_available()
                    ):
                        try:
                            api.health_records_memory_service.memory_system.delete_memory(
                                mem_id
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                cursor.execute(
                    "DELETE FROM file_attachments WHERE record_id = %s",
                    (record_id,),
                )
                if uid:
                    cursor.execute(
                        "DELETE FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, uid),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM health_records WHERE id = %s",
                        (record_id,),
                    )
                conn.commit()

                return {"message": "健康档案删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"删除健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_health_statistics(api: Any):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM health_records")
                total_records = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT record_type, COUNT(*) FROM health_records GROUP BY record_type
                    """
                )
                records_by_type = {r[0]: r[1] for r in cursor.fetchall()}

                cursor.execute(
                    """
                    SELECT importance, COUNT(*) FROM health_records GROUP BY importance
                    """
                )
                records_by_importance = {r[0]: r[1] for r in cursor.fetchall()}

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM health_records WHERE created_at >= now() - interval '7 days'
                    """
                )
                recent_records_count = cursor.fetchone()[0]

                cursor.execute("SELECT MAX(updated_at) FROM health_records")
                last_updated_val = cursor.fetchone()[0]
                last_updated = last_updated_val

                return api.HealthStatistics(
                    total_records=total_records,
                    records_by_type=records_by_type,
                    records_by_importance=records_by_importance,
                    recent_records_count=recent_records_count,
                    last_updated=last_updated,
                )
    except Exception as e:
        api.logger.error(f"获取健康统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_health_insights(
    api: Any,
    *,
    analysis_type: str,
    include_recommendations: bool,
    include_trends: bool,
    include_risks: bool,
):
    try:
        insights = [
            api.HealthInsight(
                id="insight_1",
                type="trend",
                title="血压趋势分析",
                summary="您的血压在过去一个月呈现稳定趋势",
                details="根据您最近的血压记录，收缩压平均值为120mmHg，舒张压平均值为80mmHg，均在正常范围内。",
                severity="low",
                confidence=0.85,
                tags=["血压", "心血管"],
                recommendations=["继续保持健康的生活方式", "定期监测血压"],
                metrics={"平均收缩压": 120, "平均舒张压": 80},
            ),
            api.HealthInsight(
                id="insight_2",
                type="recommendation",
                title="运动建议",
                summary="建议增加有氧运动频率",
                details="基于您的健康档案，建议每周进行3-4次中等强度的有氧运动，每次30-45分钟。",
                severity="medium",
                confidence=0.75,
                tags=["运动", "健康建议"],
                recommendations=[
                    "每周游泳2-3次",
                    "每天快走30分钟",
                    "定期进行力量训练",
                ],
            ),
        ]

        health_score = {
            "overall": 85,
            "categories": {
                "心血管健康": 88,
                "代谢健康": 82,
                "免疫系统": 90,
                "精神健康": 78,
            },
            "summary": "您的整体健康状况良好，建议继续保持健康的生活方式。",
        }

        quick_tips = [
            {
                "title": "多喝水",
                "description": "每天至少饮用8杯水，保持身体水分平衡",
            },
            {"title": "规律作息", "description": "保持每天7-8小时的优质睡眠"},
            {
                "title": "均衡饮食",
                "description": "多吃蔬菜水果，减少加工食品摄入",
            },
        ]

        return api.HealthInsightsResponse(
            insights=insights, health_score=health_score, quick_tips=quick_tips
        )
    except Exception as e:
        api.logger.error(f"获取健康洞察失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def upload_file(
    api: Any,
    *,
    file: UploadFile,
    user_id: str | None,
    skip_ocr: str | None,
    request: Request | None,
):
    limiter = api._get_upload_limiter()
    await limiter.acquire()
    try:
        api.logger.info(
            f"upload start filename={getattr(file, 'filename', None)} "
            f"ct={getattr(file, 'content_type', None)}"
        )
        allowed_types = {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/bmp",
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

        incoming_ct = (
            (getattr(file, "content_type", None) or "").strip().lower()
        )
        normalized_ct = incoming_ct
        if not normalized_ct or normalized_ct == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(file.filename or "")
            if guessed:
                normalized_ct = guessed.lower()
        if (
            not normalized_ct or normalized_ct == "application/octet-stream"
        ) and isinstance(file.filename, str):
            ext = Path(file.filename).suffix.lower()
            ext_to_ct = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
                ".pdf": "application/pdf",
                ".txt": "text/plain",
                ".doc": "application/msword",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            normalized_ct = ext_to_ct.get(ext, normalized_ct or "")

        if normalized_ct == "image/jpg":
            normalized_ct = "image/jpeg"

        if normalized_ct not in allowed_types:
            raise HTTPException(status_code=400, detail="不支持的文件类型")

        max_size = int(
            os.getenv("HEALTH_RECORDS_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
        )

        try:
            user_id = api._resolve_user_id(request, user_id)
        except Exception:
            pass

        skip_ocr_flag = str(skip_ocr or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

        file_id = api.generate_id()
        file_extension = Path(file.filename).suffix
        filename = f"{file_id}{file_extension}"
        file_path = api.UPLOAD_DIR / filename

        chunk_size = int(
            os.getenv("HEALTH_RECORDS_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        want_bytes = (not skip_ocr_flag) and normalized_ct.startswith("image/")
        content_buf = bytearray() if want_bytes else None
        try:
            with open(file_path, "wb") as out:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > max_size:
                        try:
                            out.close()
                        except Exception:
                            pass
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                        raise HTTPException(
                            status_code=400, detail="文件大小超过限制"
                        )
                    await anyio.to_thread.run_sync(out.write, chunk)
                    if content_buf is not None:
                        content_buf.extend(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        file_content = bytes(content_buf) if content_buf is not None else b""

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO file_attachments (
                        id, filename, original_filename, file_path,
                        file_size, mime_type, upload_time, record_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        filename,
                        file.filename,
                        str(file_path),
                        file_size,
                        normalized_ct,
                        datetime.now(),
                        None,
                    ),
                )

                ocr_info = None
                memory_id = None
                record_id = None

                if skip_ocr_flag:
                    now = datetime.now()
                    record_id = api.generate_id()
                    title = f"附件 - {file.filename or '上传的文件'}"
                    tags = ["auto_import"]
                    metadata = {
                        "file_id": file_id,
                        "file_path": str(file_path),
                        "mime_type": normalized_ct,
                        "uploaded_files": [file_id],
                        "skip_ocr": True,
                        "ocr_status": "pending",
                    }
                    cursor.execute(
                        """
                        INSERT INTO health_records (
                            id, user_id, title, record_type, summary, content, importance,
                            tags, metadata, record_date, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record_id,
                            user_id,
                            title,
                            api.RecordType.OTHER.value,
                            "已上传附件，内容待识别",
                            "",
                            api.ImportanceLevel.MEDIUM.value,
                            api.Json(tags),
                            api.Json(metadata),
                            None,
                            now,
                            now,
                        ),
                    )
                    cursor.execute(
                        "UPDATE file_attachments SET record_id = %s WHERE id = %s",
                        (record_id, file_id),
                    )
                    conn.commit()
                    try:
                        asyncio.create_task(
                            _process_pending_ocr(
                                api,
                                record_id=str(record_id),
                                file_id=str(file_id),
                                user_id=str(user_id),
                                file_path=str(file_path),
                                original_filename=str(file.filename or ""),
                                mime_type=str(normalized_ct or ""),
                            )
                        )
                    except Exception as e:
                        api.logger.warning(f"后台OCR任务启动失败: {e}")
                    return {
                        "file_id": file_id,
                        "filename": filename,
                        "original_filename": file.filename,
                        "file_size": file_size,
                        "mime_type": normalized_ct,
                        "message": "文件上传成功",
                        "ocr_info": None,
                        "memory_id": None,
                        "record_id": record_id,
                    }

                if normalized_ct.startswith("image/"):
                    image_base64 = base64.b64encode(file_content).decode(
                        "utf-8"
                    )
                    ocr_text = ""
                    document_type = "unknown"
                    confidence = 0.0
                    _used_paddle = False
                    used_external = False
                    try:
                        from paddleocr import PaddleOCR  # type: ignore
                        import tempfile

                        _used_paddle = True
                        tmp = tempfile.NamedTemporaryFile(
                            delete=False,
                            suffix=Path(file.filename or "").suffix or ".png",
                        )
                        tmp.write(file_content)
                        tmp_path = tmp.name
                        tmp.close()
                        try:
                            ocr_engine = PaddleOCR(
                                use_angle_cls=True, lang="ch"
                            )
                            result = ocr_engine.ocr(tmp_path, cls=True)
                            lines = [
                                line[1]
                                for line in (result[0] if result else [])
                            ]
                            ocr_text = "\n".join([t[0] for t in lines])
                            confs = [
                                float(t[1])
                                for t in lines
                                if isinstance(t[1], (int, float))
                            ]
                            confidence = (
                                (sum(confs) / len(confs)) if confs else 0.5
                            )
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                    except Exception:
                        _used_paddle = False
                    if not ocr_text:
                        if not api.extract_text_from_image:
                            conn.rollback()
                            raise HTTPException(
                                status_code=503,
                                detail="OCR模块未加载，无法对图片进行识别与入库",
                            )
                        ocr_text = (
                            api.extract_text_from_image.fn(image_base64)
                            if hasattr(api.extract_text_from_image, "fn")
                            else api.extract_text_from_image(image_base64)
                        )
                        used_external = True
                    ocr_text = api._normalize_ocr_text(ocr_text)
                    if (
                        api._is_ocr_placeholder_text(ocr_text)
                        and api.extract_text_from_image
                        and _used_paddle
                        and not used_external
                    ):
                        ocr_text = (
                            api.extract_text_from_image.fn(image_base64)
                            if hasattr(api.extract_text_from_image, "fn")
                            else api.extract_text_from_image(image_base64)
                        )
                        used_external = True
                        ocr_text = api._normalize_ocr_text(ocr_text)
                    if api._is_ocr_placeholder_text(ocr_text):
                        conn.rollback()
                        raise HTTPException(
                            status_code=422, detail="OCR识别结果无效"
                        )

                    if api.validate_medical_document:
                        try:
                            validation_json = (
                                api.validate_medical_document.fn(ocr_text)
                                if hasattr(api.validate_medical_document, "fn")
                                else api.validate_medical_document(ocr_text)
                            )
                            val = (
                                json.loads(validation_json)
                                if isinstance(validation_json, str)
                                else (validation_json or {})
                            )
                            document_type = (
                                val.get("document_type") or "unknown"
                            )
                            vconf = val.get("confidence")
                            if isinstance(vconf, (int, float)):
                                confidence = max(
                                    float(confidence), float(vconf)
                                )
                        except Exception as e:
                            api.logger.warning(
                                f"文档验证失败，使用默认类型: {e}"
                            )
                        validation = validation_json
                    else:
                        validation = {}

                    extracted_info = None
                    try:
                        from HealthRecordsManager.mcpserver.data_extraction_tool import (
                            extract_medical_info as _extract_medical_info,  # type: ignore
                        )
                    except Exception:
                        _extract_medical_info = None  # type: ignore

                    if _extract_medical_info:
                        try:
                            info_json = (
                                _extract_medical_info.fn(ocr_text)
                                if hasattr(_extract_medical_info, "fn")
                                else _extract_medical_info(ocr_text)
                            )
                            extracted_info = (
                                json.loads(info_json)
                                if isinstance(info_json, str)
                                else info_json
                            )
                        except Exception as e:
                            api.logger.warning(f"结构化提取失败: {e}")

                    try:
                        validation_data = (
                            json.loads(validation)
                            if isinstance(validation, str)
                            else validation
                        )
                    except Exception:
                        validation_data = {"raw": validation}
                    document_type = api._normalize_document_type(
                        validation_data.get("document_type")
                    )
                    try:
                        confidence = float(
                            validation_data.get("confidence", 0.5)
                        )
                    except Exception:
                        confidence = 0.5

                    extracted_info = {}
                    if api.extract_medical_info:
                        try:
                            info_json = (
                                api.extract_medical_info.fn(ocr_text)
                                if hasattr(api.extract_medical_info, "fn")
                                else api.extract_medical_info(ocr_text)
                            )
                            extracted_info = (
                                json.loads(info_json)
                                if isinstance(info_json, str)
                                else (info_json or {})
                            )
                        except Exception as e:
                            api.logger.warning(f"信息抽取失败，已忽略: {e}")
                            extracted_info = {}
                    if isinstance(extracted_info, dict):
                        tests_val = extracted_info.get(
                            "test_results"
                        ) or extracted_info.get("tests")
                        filtered = api._filter_test_results(tests_val)
                        if filtered is not None:
                            if filtered:
                                extracted_info["test_results"] = filtered
                            else:
                                extracted_info.pop("test_results", None)
                            extracted_info.pop("tests", None)

                    if api.health_records_memory_service is not None:
                        try:
                            if (
                                not api.health_records_memory_service.is_available()
                            ):
                                await api.health_records_memory_service.initialize()
                            try:
                                memory_id = await asyncio.wait_for(
                                    api.health_records_memory_service.store_ocr_result(
                                        user_id=user_id,
                                        document_type=document_type,
                                        ocr_text=(
                                            ocr_text
                                            if isinstance(ocr_text, str)
                                            else str(ocr_text)
                                        ),
                                        extracted_info=(
                                            extracted_info
                                            if isinstance(extracted_info, dict)
                                            else {}
                                        ),
                                        confidence=confidence,
                                        file_path=str(file_path),
                                    ),
                                    timeout=2.0,
                                )
                            except asyncio.TimeoutError:
                                api.logger.warning(
                                    "存储OCR结果到记忆超时，已跳过"
                                )
                                memory_id = None
                        except Exception as e:
                            api.logger.warning(f"存储OCR结果到记忆失败: {e}")

                    ocr_text_str = api._normalize_ocr_text(
                        ocr_text
                        if isinstance(ocr_text, str)
                        else str(ocr_text)
                    )
                    if not ocr_text_str or not ocr_text_str.strip():
                        conn.rollback()
                        raise HTTPException(
                            status_code=422, detail="OCR识别结果为空，未入库"
                        )

                    doc_type_lower = (document_type or "").lower()
                    ext_doc_type = (
                        (extracted_info or {}).get("document_type")
                        if isinstance(extracted_info, dict)
                        else None
                    )
                    if isinstance(ext_doc_type, str) and ext_doc_type.strip():
                        doc_type_lower = ext_doc_type.strip().lower()

                    lab_keywords = [
                        "血常规",
                        "化验",
                        "检验",
                        "实验室",
                        "检验报告",
                        "化验单",
                        "B超",
                        "CT",
                        "MRI",
                        "X光",
                        "影像",
                    ]
                    prescription_keywords = [
                        "处方",
                        "医嘱",
                        "用药",
                        "药品",
                        "药方",
                    ]
                    surgery_keywords = ["手术", "术后", "术前", "麻醉"]
                    allergy_keywords = ["过敏", "皮试", "过敏史"]
                    vaccination_keywords = ["疫苗", "接种", "免疫"]
                    vital_keywords = [
                        "血压",
                        "心率",
                        "体温",
                        "呼吸",
                        "身高",
                        "体重",
                    ]

                    def has_any(text: str, kws: list[str]) -> bool:
                        return any(k in text for k in kws)

                    if doc_type_lower in {
                        "test_report",
                        "lab_result",
                        "inspection_report",
                        "检验报告",
                        "化验单",
                    } or has_any(ocr_text_str, lab_keywords):
                        record_type = api.RecordType.LAB_RESULT.value
                    elif doc_type_lower in {
                        "prescription",
                        "medication",
                        "处方",
                    } or has_any(ocr_text_str, prescription_keywords):
                        record_type = api.RecordType.PRESCRIPTION.value
                    elif has_any(ocr_text_str, surgery_keywords):
                        record_type = api.RecordType.SURGERY.value
                    elif doc_type_lower in {
                        "medical_record",
                        "病历",
                        "门诊记录",
                        "出院记录",
                        "入院记录",
                    }:
                        record_type = api.RecordType.MEDICAL_REPORT.value
                    elif has_any(ocr_text_str, allergy_keywords):
                        record_type = api.RecordType.ALLERGY.value
                    elif has_any(ocr_text_str, vaccination_keywords):
                        record_type = api.RecordType.VACCINATION.value
                    elif has_any(ocr_text_str, vital_keywords):
                        record_type = api.RecordType.VITAL_SIGNS.value
                    else:
                        record_type = api.RecordType.MEDICAL_REPORT.value

                    now = datetime.now()
                    record_id = api.generate_id()
                    title = f"{document_type or 'OCR文档'} - {file.filename}"
                    tags = ["ocr", "auto_import", document_type or "unknown"]
                    try:
                        file_hash = hashlib.sha256(file_content).hexdigest()
                    except Exception:
                        file_hash = None
                    metadata = {
                        "file_id": file_id,
                        "file_path": str(file_path),
                        "mime_type": normalized_ct,
                        "ocr_info": {
                            "document_type": document_type,
                            "confidence": confidence,
                            "text_length": len(ocr_text_str),
                        },
                        "memory_id": memory_id,
                        "extracted_info": (
                            extracted_info
                            if isinstance(extracted_info, dict)
                            else {}
                        ),
                        "uploaded_files": [file_id],
                        **({"file_hash": file_hash} if file_hash else {}),
                    }

                    try:
                        cursor.execute(
                            """
                            SELECT id FROM health_records
                            WHERE user_id = %s AND (content = %s OR metadata ->> 'file_hash' = %s)
                            ORDER BY created_at DESC LIMIT 1
                            """,
                            (user_id, ocr_text_str, file_hash),
                        )
                        dup = cursor.fetchone()
                        if dup and (
                            dup.get("id") if isinstance(dup, dict) else dup[0]
                        ):
                            dup_id = (
                                dup.get("id")
                                if isinstance(dup, dict)
                                else dup[0]
                            )
                            cursor.execute(
                                "UPDATE file_attachments SET record_id = %s WHERE id = %s",
                                (dup_id, file_id),
                            )
                            conn.commit()
                            api.logger.info(
                                f"upload dedup merged file_id={file_id} "
                                f"record_id={dup_id} user_id={user_id} "
                                f"hash={file_hash}"
                            )
                            return {
                                "file_id": file_id,
                                "record_id": dup_id,
                                "ocr_info": {
                                    "document_type": document_type,
                                    "confidence": confidence,
                                    "text_length": len(ocr_text_str),
                                },
                                "message": "duplicate_merged",
                            }
                    except Exception:
                        pass

                    structured_summary = api._build_structured_summary(
                        metadata.get("extracted_info")
                        if isinstance(metadata, dict)
                        else None
                    )
                    if structured_summary and isinstance(metadata, dict):
                        metadata["structured_summary"] = structured_summary

                    llm_summary = None
                    try:
                        llm_summary = await api._maybe_llm_summary(
                            ocr_text_str,
                            (
                                metadata.get("extracted_info")
                                if isinstance(metadata, dict)
                                else None
                            ),
                        )
                    except Exception as e:
                        api.logger.warning(f"调用 LLM 摘要失败: {e}")
                        llm_summary = None
                    if llm_summary is not None:
                        api.logger.info("使用 LLM 摘要")
                    elif structured_summary:
                        api.logger.info("使用结构化摘要")
                    else:
                        api.logger.info("使用规则摘要")
                    final_summary = (
                        llm_summary
                        or structured_summary
                        or api._generate_ai_summary(
                            ocr_text_str,
                            (
                                metadata.get("extracted_info")
                                if isinstance(metadata, dict)
                                else None
                            ),
                        )
                    )

                    cursor.execute(
                        """
                        INSERT INTO health_records (
                            id, user_id, title, record_type, summary, content, importance,
                            tags, metadata, record_date, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record_id,
                            user_id,
                            title,
                            record_type,
                            final_summary,
                            ocr_text_str,
                            api.ImportanceLevel.MEDIUM.value,
                            api.Json(tags),
                            api.Json(metadata),
                            None,
                            now,
                            now,
                        ),
                    )
                    cursor.execute(
                        "UPDATE file_attachments SET record_id = %s WHERE id = %s",
                        (record_id, file_id),
                    )

                    ocr_info = {
                        "document_type": document_type,
                        "confidence": confidence,
                        "text_length": len(ocr_text_str),
                    }

                    conn.commit()
                    api.logger.info(
                        f"upload insert record_id={record_id} user_id={user_id} "
                        f"file_id={file_id} type={record_type} "
                        f"summary_len={len(final_summary or '')} "
                        f"content_len={len(ocr_text_str or '')}"
                    )

                    try:
                        api._save_to_hrm(
                            user_id=user_id,
                            record_type=record_type,
                            title=title,
                            content=ocr_text_str,
                            extracted_data=metadata.get("extracted_info")
                            or {},
                        )
                    except Exception as e:
                        api.logger.warning(f"OCR入库后HRM双写失败：{e}")
            if not normalized_ct.startswith("image/"):
                conn.commit()

        return {
            "file_id": file_id,
            "filename": filename,
            "original_filename": file.filename,
            "file_size": file_size,
            "mime_type": normalized_ct,
            "message": "文件上传成功",
            "ocr_info": ocr_info,
            "memory_id": memory_id,
            "record_id": record_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            limiter.release()
        except Exception:
            pass


async def _process_pending_ocr(
    api: Any,
    *,
    record_id: str,
    file_id: str,
    user_id: str,
    file_path: str,
    original_filename: str = "",
    mime_type: str = "",
):
    started_at = datetime.now()
    try:
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT id, title, summary, content, record_type, tags, metadata
                    FROM health_records
                    WHERE id = %s AND user_id = %s
                    """,
                    (record_id, user_id),
                )
                row = cursor.fetchone()
                if not row:
                    return
                meta = (
                    api.deserialize_metadata(row["metadata"])
                    if isinstance(row.get("metadata"), str)
                    else (row.get("metadata") or {})
                )
                if not isinstance(meta, dict):
                    meta = {}
                if meta.get("ocr_status") == "done":
                    return
                meta["ocr_status"] = "processing"
                meta["ocr_started_at"] = started_at.isoformat()
                cursor.execute(
                    """
                    UPDATE health_records
                    SET metadata = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (api.Json(meta), started_at, record_id, user_id),
                )
                conn.commit()

        p = Path(file_path)
        file_bytes = await anyio.to_thread.run_sync(p.read_bytes)
        if not file_bytes:
            raise ValueError("empty file")

        ocr_text: str | None = None
        confidence = 0.5
        document_type = "unknown"

        if (mime_type or "").startswith("image/"):
            try:
                from paddleocr import PaddleOCR  # type: ignore

                ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch")
                result = await anyio.to_thread.run_sync(
                    lambda: ocr_engine.ocr(str(p), cls=True)
                )
                texts: list[str] = []
                confs: list[float] = []
                if isinstance(result, list) and result:
                    page0 = result[0] if result else []
                    if isinstance(page0, list):
                        for it in page0:
                            try:
                                texts.append(str(it[1][0] or "").strip())
                                confs.append(float(it[1][1]))
                            except Exception:
                                pass
                ocr_text = "\n".join([t for t in texts if t])
                if confs:
                    confidence = sum(confs) / max(len(confs), 1)
            except Exception as e:
                api.logger.warning(f"后台OCR PaddleOCR失败: {e}")

        if (not ocr_text) and api.extract_text_from_image:
            image_base64 = base64.b64encode(file_bytes).decode("utf-8")
            try:
                ocr_text = await anyio.to_thread.run_sync(
                    lambda: (
                        api.extract_text_from_image.fn(image_base64)
                        if hasattr(api.extract_text_from_image, "fn")
                        else api.extract_text_from_image(image_base64)
                    )
                )
            except Exception as e:
                api.logger.warning(f"后台OCR 外部OCR失败: {e}")

        ocr_text_str = api._normalize_ocr_text(
            ocr_text
            if isinstance(ocr_text, str)
            else (str(ocr_text) if ocr_text else "")
        )
        if not ocr_text_str or api._is_ocr_placeholder_text(ocr_text_str):
            raise ValueError("invalid ocr result")

        if api.validate_medical_document:
            try:
                validation_json = await anyio.to_thread.run_sync(
                    lambda: (
                        api.validate_medical_document.fn(ocr_text_str)
                        if hasattr(api.validate_medical_document, "fn")
                        else api.validate_medical_document(ocr_text_str)
                    )
                )
                val = (
                    json.loads(validation_json)
                    if isinstance(validation_json, str)
                    else (validation_json or {})
                )
                document_type = api._normalize_document_type(
                    val.get("document_type")
                )
                vconf = val.get("confidence")
                if isinstance(vconf, (int, float)):
                    confidence = max(float(confidence), float(vconf))
            except Exception as e:
                api.logger.warning(f"后台OCR 文档验证失败: {e}")

        extracted_info: dict = {}
        if api.extract_medical_info:
            try:
                info_json = await anyio.to_thread.run_sync(
                    lambda: (
                        api.extract_medical_info.fn(ocr_text_str)
                        if hasattr(api.extract_medical_info, "fn")
                        else api.extract_medical_info(ocr_text_str)
                    )
                )
                extracted_info = (
                    json.loads(info_json)
                    if isinstance(info_json, str)
                    else (info_json or {})
                )
                if not isinstance(extracted_info, dict):
                    extracted_info = {}
            except Exception as e:
                api.logger.warning(f"后台OCR 信息抽取失败: {e}")
                extracted_info = {}

        tests_val = extracted_info.get("test_results") or extracted_info.get(
            "tests"
        )
        filtered = api._filter_test_results(tests_val)
        if filtered is not None:
            if filtered:
                extracted_info["test_results"] = filtered
            else:
                extracted_info.pop("test_results", None)
            extracted_info.pop("tests", None)

        memory_id = None
        if api.health_records_memory_service is not None:
            try:
                if not api.health_records_memory_service.is_available():
                    await api.health_records_memory_service.initialize()
                try:
                    memory_id = await asyncio.wait_for(
                        api.health_records_memory_service.store_ocr_result(
                            user_id=user_id,
                            document_type=document_type,
                            ocr_text=ocr_text_str,
                            extracted_info=extracted_info,
                            confidence=confidence,
                            file_path=str(file_path),
                        ),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    api.logger.warning("后台OCR存储记忆超时，已跳过")
                    memory_id = None
            except Exception as e:
                api.logger.warning(f"后台OCR存储记忆失败: {e}")
                memory_id = None

        doc_type_lower = (document_type or "").lower()
        if doc_type_lower in {
            "test_report",
            "lab_result",
            "inspection_report",
            "检验报告",
            "化验单",
        }:
            record_type = api.RecordType.LAB_RESULT.value
        elif doc_type_lower in {"prescription", "medication", "处方"}:
            record_type = api.RecordType.PRESCRIPTION.value
        else:
            record_type = api.RecordType.MEDICAL_REPORT.value

        structured_summary = api._build_structured_summary(extracted_info)
        llm_summary = None
        try:
            llm_summary = await api._maybe_llm_summary(
                ocr_text_str, extracted_info
            )
        except Exception:
            llm_summary = None
        final_summary = (
            llm_summary
            or structured_summary
            or api._generate_ai_summary(ocr_text_str, extracted_info)
        )

        try:
            file_hash = hashlib.sha256(file_bytes).hexdigest()
        except Exception:
            file_hash = None

        finished_at = datetime.now()
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT title, summary, content, record_type, tags, metadata, importance
                    FROM health_records
                    WHERE id = %s AND user_id = %s
                    """,
                    (record_id, user_id),
                )
                row = cursor.fetchone()
                if not row:
                    return

                current_title = row.get("title") or ""
                current_summary = row.get("summary") or ""
                current_content = row.get("content") or ""
                current_record_type = row.get("record_type") or ""
                current_tags = row.get("tags") or []
                meta = (
                    api.deserialize_metadata(row["metadata"])
                    if isinstance(row.get("metadata"), str)
                    else (row.get("metadata") or {})
                )
                if not isinstance(meta, dict):
                    meta = {}
                if not isinstance(current_tags, list):
                    current_tags = []

                new_record_type = current_record_type
                if (not current_record_type) or (
                    current_record_type == api.RecordType.OTHER.value
                ):
                    new_record_type = record_type

                ui_doc_type = str(new_record_type or "").strip().lower()
                if not ui_doc_type:
                    ui_doc_type = (
                        str(document_type or "unknown").strip().lower()
                    )

                raw_dt = str(document_type or "").strip().lower()
                raw_to_key = {
                    "病历": "medical_record",
                    "就诊记录": "medical_record",
                    "门诊记录": "medical_record",
                    "检查报告": "lab_result",
                    "检验报告": "lab_result",
                    "化验单": "lab_result",
                    "处方": "prescription",
                    "处方单": "prescription",
                    "住院记录": "hospital_record",
                    "疫苗记录": "vaccination_record",
                    "手术记录": "surgery",
                    "影像资料": "imaging",
                    "影像报告": "radiology",
                }
                if raw_dt in raw_to_key:
                    ui_doc_type = raw_to_key[raw_dt]

                doc_type_label_map = {
                    "test_report": "检查报告",
                    "inspection_report": "检查报告",
                    "lab_result": "检查报告",
                    "medical_record": "病历",
                    "hospital_record": "住院记录",
                    "vaccination_record": "疫苗记录",
                    "vaccination": "疫苗记录",
                    "prescription": "处方单",
                    "surgery": "手术记录",
                    "imaging": "影像资料",
                    "radiology": "影像资料",
                }
                title_label = (
                    doc_type_label_map.get(ui_doc_type, "")
                    or str(document_type or "OCR文档").strip()
                )

                tags: list[str] = []
                for t in current_tags:
                    if isinstance(t, str) and t.startswith("file:"):
                        continue
                    if isinstance(t, str) and t not in tags:
                        tags.append(t)
                for t in ["ocr", "auto_import", ui_doc_type or "unknown"]:
                    if t and t not in tags:
                        tags.append(t)

                new_title = current_title
                if (not current_title) or str(current_title).startswith(
                    "附件 -"
                ):
                    suffix = (original_filename or "").strip()
                    if suffix:
                        suffix = (
                            suffix.replace("\\", "/").split("/")[-1].strip()
                        )
                    if (
                        suffix
                        and "." not in suffix
                        and re.fullmatch(r"[A-Za-z0-9]{12,}", suffix)
                    ):
                        suffix = ""
                    if suffix:
                        new_title = f"{title_label} - {suffix}".strip(" -")
                    else:
                        new_title = str(title_label).strip() or "健康档案"

                new_summary = current_summary
                if (not current_summary) or (
                    str(current_summary).strip() == "已上传附件，内容待识别"
                ):
                    new_summary = final_summary

                new_content = current_content
                if not current_content:
                    new_content = ocr_text_str

                uploaded_files = meta.get("uploaded_files")
                if not isinstance(uploaded_files, list):
                    uploaded_files = []
                if file_id and file_id not in uploaded_files:
                    uploaded_files.append(file_id)

                meta.update(
                    {
                        "file_id": meta.get("file_id") or file_id,
                        "file_path": meta.get("file_path") or str(file_path),
                        "mime_type": meta.get("mime_type")
                        or (mime_type or ""),
                        "uploaded_files": uploaded_files,
                        "ocr_info": {
                            "document_type": ui_doc_type,
                            "raw_document_type": str(
                                document_type or ""
                            ).strip(),
                            "confidence": confidence,
                            "text_length": len(ocr_text_str),
                        },
                        "extracted_info": extracted_info,
                        "memory_id": memory_id,
                        "skip_ocr": False,
                        "ocr_status": "done",
                        "ocr_finished_at": finished_at.isoformat(),
                        **({"file_hash": file_hash} if file_hash else {}),
                    }
                )
                cursor.execute(
                    """
                    UPDATE health_records
                    SET title = %s,
                        record_type = %s,
                        summary = %s,
                        content = %s,
                        tags = %s,
                        metadata = %s,
                        updated_at = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        new_title,
                        new_record_type,
                        new_summary,
                        new_content,
                        api.Json(tags),
                        api.Json(meta),
                        finished_at,
                        record_id,
                        user_id,
                    ),
                )

                try:
                    text = api._make_rag_text(
                        new_title, new_summary, new_content
                    )
                    api._upsert_rag_document(
                        cursor,
                        user_id=user_id,
                        source_type="health_records",
                        source_id=str(record_id),
                        record_type=str(new_record_type),
                        title=new_title,
                        text=text,
                    )
                except Exception as e:
                    api.logger.warning(f"后台OCR RAG入库失败：{e}")

                conn.commit()

        try:
            api._save_to_hrm(
                user_id=user_id,
                record_type=new_record_type,
                title=new_title,
                content=new_content or (new_summary or ""),
                extracted_data=meta.get("extracted_info") or {},
            )
        except Exception as e:
            api.logger.warning(f"后台OCR HRM双写失败：{e}")

        try:
            if api.health_records_memory_service is not None:
                if not api.health_records_memory_service.is_available():
                    await api.health_records_memory_service.initialize()
                imp_map = {
                    "low": 0.2,
                    "medium": 0.5,
                    "high": 0.8,
                    "critical": 1.0,
                }
                imp_key = row.get("importance") or "medium"
                imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                await api.health_records_memory_service.store_health_record(
                    user_id=user_id,
                    record_type=new_record_type,
                    record_data={
                        "id": record_id,
                        "title": new_title,
                        "content": new_content,
                        "metadata": meta or {},
                        "record_date": None,
                    },
                    summary=new_summary or "",
                    importance=imp_val,
                    tags=tags,
                )
        except Exception as e:
            api.logger.warning(f"后台OCR 写入健康档案记忆失败：{e}")
    except Exception as e:
        failed_at = datetime.now()
        try:
            with api.get_db_connection() as conn:
                with conn.cursor(row_factory=api.dict_row) as cursor:
                    cursor.execute(
                        "SELECT metadata FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, user_id),
                    )
                    row = cursor.fetchone() or {}
                    meta = (
                        api.deserialize_metadata(row.get("metadata"))
                        if isinstance(row.get("metadata"), str)
                        else (row.get("metadata") or {})
                    )
                    if not isinstance(meta, dict):
                        meta = {}
                    meta["ocr_status"] = "failed"
                    meta["ocr_failed_at"] = failed_at.isoformat()
                    meta["ocr_error"] = str(e)
                    cursor.execute(
                        """
                        UPDATE health_records
                        SET metadata = %s, updated_at = %s
                        WHERE id = %s AND user_id = %s
                        """,
                        (api.Json(meta), failed_at, record_id, user_id),
                    )
                    conn.commit()
        except Exception:
            pass
        api.logger.warning(f"后台OCR处理失败 record_id={record_id}: {e}")


async def upload_multiple_files(
    api: Any,
    *,
    files: list[UploadFile],
    user_id: str | None,
    request: Request | None,
):
    try:
        if not files:
            raise HTTPException(status_code=400, detail="未提供文件")

        results = []
        for f in files:
            try:
                res = await upload_file(
                    api,
                    file=f,
                    user_id=user_id,
                    skip_ocr=None,
                    request=request,
                )
                results.append(res)
            except HTTPException as he:
                results.append(
                    {
                        "filename": getattr(f, "filename", None),
                        "error": he.detail,
                    }
                )
            except Exception as e:
                results.append(
                    {"filename": getattr(f, "filename", None), "error": str(e)}
                )

        return {
            "files": results,
            "count": len(results),
            "message": f"已处理 {len(results)} 个文件",
        }
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"批量文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def sync_sqlite_to_hrm(api: Any, *, user_id: str):
    try:
        synced = 0
        skipped = 0
        if not api.HRM_SAVE_RECORD:
            raise HTTPException(
                status_code=503, detail="HRM存储工具不可用，无法同步"
            )

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    "SELECT id, title, record_type, summary, content, metadata "
                    "FROM health_records WHERE user_id = %s "
                    "ORDER BY created_at DESC",
                    (user_id,),
                )
                rows = cursor.fetchall()

            for row in rows:
                try:
                    title = row["title"] or "记录"
                    rtype = row["record_type"] or "other"
                    content = row["content"] or (row["summary"] or "")
                    meta = (
                        api.deserialize_metadata(row["metadata"])
                        if isinstance(row["metadata"], str)
                        else (row["metadata"] or {})
                    )
                    extracted = meta.get("extracted_info") or meta

                    if not content or not str(content).strip():
                        skipped += 1
                        continue

                    api._save_to_hrm(
                        user_id=user_id,
                        record_type=rtype,
                        title=title,
                        content=str(content),
                        extracted_data=extracted,
                    )
                    synced += 1
                except Exception as e:
                    api.logger.warning(f"同步单条记录失败（已跳过）: {e}")
                    skipped += 1

        return {
            "message": "同步完成",
            "user_id": user_id,
            "synced": synced,
            "skipped": skipped,
        }
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"健康记录同步到HRM失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def backfill_health_trends(
    api: Any,
    *,
    days: int,
    limit: int,
    dry_run: bool,
    user_id: str | None,
    request: Request | None,
) -> dict[str, Any]:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        total = 0
        updated = 0
        skipped = 0
        updated_ids: list[str] = []

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                interval = f"{days} days"
                cursor.execute(
                    """
                    SELECT id, content, metadata, record_date, created_at
                    FROM health_records
                    WHERE user_id = %s
                    AND (record_date >= now() - %s::interval OR created_at >= now() - %s::interval)
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (uid, interval, interval, limit),
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    total += 1
                    meta_val = row.get("metadata")
                    if isinstance(meta_val, str):
                        meta_val = api.deserialize_metadata(meta_val)
                    elif not isinstance(meta_val, dict):
                        meta_val = {}

                    extracted = api._ensure_dict_value(
                        meta_val.get("extracted_info") or meta_val.get("extracted_data")
                    )
                    tests = extracted.get("test_results") or extracted.get("tests")
                    if tests:
                        skipped += 1
                        continue

                    text = row.get("content") or ""
                    if not text and isinstance(extracted, dict):
                        text = extracted.get("original_content") or ""
                    if not text:
                        skipped += 1
                        continue

                    test_results = None
                    extractor = getattr(api, "extract_test_results", None)
                    if extractor:
                        try:
                            test_results = (
                                extractor.fn(text)
                                if hasattr(extractor, "fn")
                                else extractor(text)
                            )
                        except Exception:
                            test_results = None

                    if not test_results:
                        extractor2 = getattr(api, "extract_medical_info", None)
                        if extractor2:
                            try:
                                info_json = (
                                    extractor2.fn(text)
                                    if hasattr(extractor2, "fn")
                                    else extractor2(text)
                                )
                                info_obj = (
                                    json.loads(info_json)
                                    if isinstance(info_json, str)
                                    else info_json
                                )
                                if isinstance(info_obj, dict):
                                    test_results = info_obj.get("test_results")
                            except Exception:
                                test_results = None

                    if not test_results or not isinstance(test_results, dict):
                        skipped += 1
                        continue

                    filtered_results = api._filter_test_results(test_results)
                    if filtered_results is None or not filtered_results:
                        skipped += 1
                        continue

                    extracted["test_results"] = filtered_results
                    meta_val["extracted_info"] = extracted
                    updated += 1

                    if not dry_run:
                        cursor.execute(
                            """
                            UPDATE health_records
                            SET metadata = %s, updated_at = %s
                            WHERE id = %s AND user_id = %s
                            """,
                            (api.Json(meta_val), datetime.now(), row.get("id"), uid),
                        )

                    updated_ids.append(str(row.get("id")))

                if not dry_run and updated:
                    conn.commit()

        return {
            "dry_run": dry_run,
            "days": days,
            "limit": limit,
            "total_scanned": total,
            "updated": updated,
            "skipped": skipped,
            "updated_ids": updated_ids[:50],
        }
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"回填健康趋势失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_health_trend_indicators(
    api: Any,
    *,
    days: int,
    include_points: bool,
    user_id: str | None,
    request: Request | None,
) -> dict[str, Any]:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        store: dict = {}
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                interval = f"{days} days"
                cursor.execute(
                    """
                    SELECT id, record_date, created_at, metadata, content
                    FROM health_records
                    WHERE user_id = %s
                    AND (record_date >= now() - %s::interval OR created_at >= now() - %s::interval)
                    """,
                    (uid, interval, interval),
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    meta_val = row.get("metadata")
                    if isinstance(meta_val, str):
                        meta_val = api.deserialize_metadata(meta_val)
                    elif not isinstance(meta_val, dict):
                        meta_val = {}

                    meta_val = api._prepare_metadata_with_tests(
                        row.get("content"), meta_val
                    )
                    extracted = api._ensure_dict_value(
                        meta_val.get("extracted_info") or meta_val.get("extracted_data")
                    )
                    tests = extracted.get("test_results") or extracted.get("tests")
                    if tests:
                        api._collect_test_points(
                            store,
                            tests,
                            row.get("record_date") or row.get("created_at"),
                            "health_records",
                            str(row.get("id")) if row.get("id") is not None else None,
                        )

                cursor.execute(
                    """
                    SELECT id, visit_date, created_at, tests
                    FROM visit_summaries
                    WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0
                    AND (visit_date >= now() - %s::interval OR created_at >= now() - %s::interval)
                    """,
                    (uid, interval, interval),
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    tests = row.get("tests")
                    if isinstance(tests, str):
                        tests = api._ensure_list_value(tests) or api._ensure_dict_value(
                            tests
                        )
                    if tests:
                        api._collect_test_points(
                            store,
                            tests,
                            row.get("visit_date") or row.get("created_at"),
                            "visit_summaries",
                            str(row.get("id")) if row.get("id") is not None else None,
                        )

        indicators = api._finalize_indicator_items(store, include_points)
        return {"days": days, "indicators": indicators}
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"获取健康趋势指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_health_trend_indicator(
    api: Any,
    *,
    name: str,
    days: int,
    user_id: str | None,
    request: Request | None,
) -> dict[str, Any]:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        store: dict = {}
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                interval = f"{days} days"
                cursor.execute(
                    """
                    SELECT id, record_date, created_at, metadata, content
                    FROM health_records
                    WHERE user_id = %s
                    AND (record_date >= now() - %s::interval OR created_at >= now() - %s::interval)
                    """,
                    (uid, interval, interval),
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    meta_val = row.get("metadata")
                    if isinstance(meta_val, str):
                        meta_val = api.deserialize_metadata(meta_val)
                    elif not isinstance(meta_val, dict):
                        meta_val = {}

                    meta_val = api._prepare_metadata_with_tests(
                        row.get("content"), meta_val
                    )
                    extracted = api._ensure_dict_value(
                        meta_val.get("extracted_info") or meta_val.get("extracted_data")
                    )
                    tests = extracted.get("test_results") or extracted.get("tests")
                    if tests:
                        api._collect_test_points(
                            store,
                            tests,
                            row.get("record_date") or row.get("created_at"),
                            "health_records",
                            str(row.get("id")) if row.get("id") is not None else None,
                        )

                cursor.execute(
                    """
                    SELECT id, visit_date, created_at, tests
                    FROM visit_summaries
                    WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0
                    AND (visit_date >= now() - %s::interval OR created_at >= now() - %s::interval)
                    """,
                    (uid, interval, interval),
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    tests = row.get("tests")
                    if isinstance(tests, str):
                        tests = api._ensure_list_value(tests) or api._ensure_dict_value(
                            tests
                        )
                    if tests:
                        api._collect_test_points(
                            store,
                            tests,
                            row.get("visit_date") or row.get("created_at"),
                            "visit_summaries",
                            str(row.get("id")) if row.get("id") is not None else None,
                        )

        indicators = api._finalize_indicator_items(store, True)
        selected = None
        for item in indicators:
            if item.get("name") == name:
                selected = item
                break

        return {"days": days, "indicator": selected}
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"获取健康趋势详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_record_extracted_info(api: Any, *, record_id: str):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    "SELECT metadata FROM health_records WHERE id = %s",
                    (record_id,),
                )
                row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="健康档案不存在")
            metadata = api.deserialize_metadata(
                row[0] if isinstance(row, tuple) else row["metadata"]
            )
            return {
                "extracted_info": metadata.get("extracted_info") or {},
                "ocr_info": metadata.get("ocr_info") or {},
            }
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"获取结构化信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_file_attachment(api: Any, *, file_id: str):
    try:
        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT original_filename, file_path, mime_type FROM file_attachments WHERE id = %s",
                    (file_id,),
                )
                row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="附件不存在")
            original_name = (
                row[0] if isinstance(row, tuple) else row["original_filename"]
            )
            path_str = row[1] if isinstance(row, tuple) else row["file_path"]
            mime = (
                row[2] if isinstance(row, tuple) else row["mime_type"]
            ) or "application/octet-stream"
            file_path = Path(path_str)
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="文件不存在")
            headers = {
                "Content-Disposition": f'inline; filename="{original_name}"'
            }
            return api.FileResponse(
                str(file_path),
                media_type=mime,
                headers=headers,
            )
    except HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"获取附件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
