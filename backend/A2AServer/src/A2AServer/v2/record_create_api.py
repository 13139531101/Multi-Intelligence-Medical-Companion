"""阶段48-22 v2 (末尾): Create-Record-and-Attach 单步接口.

动机: 前端用两步虽然灵活, 但 UX 上是负担 — 用户点了上传 + 点关联 + 点保存.

设计: 一个端到端的事务化接口 (逻辑事务, 不是 SQL 事务 — 失败回滚 best-effort):
  POST /api/v2/create-record-and-attach
       body: {
         target_table: "health_records" | "visit_summaries",
         record: { title, record_type, record_date, hospital, doctor, summary, content, importance, tags, ... },
         attached_file_ids: [...]   // optional
       }
  response: { record_id, attached_file_ids, attached_count, warnings? }

逻辑流:
  1. 创建 record 行
  2. 如果有 file_ids: 上 spread 给 attach-files 逻辑
  3. 全部成功才返回 200, 否则回滚 record (deleted on conflict)

不做 SQL 事务: 因为跨表 + 跨 system (uploaded_files), 但失败回滚足够了.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import date as date_type
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, Body, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from .record_attach_api import (
    SUPPORTED_TABLES,
    _back_mark_files,
    _merge_metadata_attached_ids,
    _verify_files_ownership,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2-record-create"])


# ===== DB =====
@contextmanager
def get_db():
    host = os.getenv("DB_HOST", "postgres")
    user = os.getenv("DB_USER", "pha")
    password = os.getenv("DB_PASSWORD", "")
    db = os.getenv("MEMORY_DB_NAME", "personal_health_assistant")
    dsn = os.getenv("PHA_BLOB_DSN") or f"postgresql://{user}:{password}@{host}:5432/{db}"
    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ===== Models =====
class HealthRecordPayload(BaseModel):
    title: str
    record_type: str = "other"
    record_date: Optional[str] = None       # ISO date string
    hospital: Optional[str] = ""
    department: Optional[str] = ""
    doctor: Optional[str] = ""
    summary: Optional[str] = ""
    content: Optional[str] = ""
    importance: Optional[str] = "medium"
    tags: List[str] = Field(default_factory=list)


class VisitSummaryPayload(BaseModel):
    title: str
    visit_date: Optional[str] = None
    doctor: Optional[str] = ""
    hospital: Optional[str] = ""
    department: Optional[str] = ""
    chief_complaint: Optional[str] = ""
    symptoms: Optional[str] = ""
    examination: Optional[str] = ""
    diagnosis: Optional[str] = ""
    treatment: Optional[str] = ""
    prescription: Optional[str] = "[]"
    follow_up: Optional[str] = ""
    notes: Optional[str] = ""


class CreateAndAttachRequest(BaseModel):
    target_table: str = "health_records"
    record: Dict[str, Any]
    attached_file_ids: List[str] = Field(default_factory=list)


class CreateAndAttachResponse(BaseModel):
    ok: bool
    record_id: str
    target_table: str
    attached_file_ids: List[str] = []
    attached_count: int = 0
    warnings: List[str] = Field(default_factory=list)


# ===== Create + Attach helpers =====
def _create_health_record(user_id: str, payload: HealthRecordPayload) -> str:
    rid = str(uuid.uuid4())
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO health_records
                        (id, user_id, title, record_type, summary, content,
                         importance, tags, metadata, record_date, file_hash)
                    VALUES (%s, %s, %s, %s, %s, %s,
                            %s, %s::jsonb, '{}'::jsonb, %s, %s)
                """, (
                    rid, user_id,
                    payload.title[:200],
                    payload.record_type,
                    (payload.summary or "")[:1000],
                    payload.content or "",
                    payload.importance or "medium",
                    json.dumps(payload.tags or []),
                    payload.record_date or date_type.today().isoformat(),
                    "",
                ))
        return rid
    except Exception:
        raise


def _create_visit_summary(user_id: str, payload: VisitSummaryPayload) -> str:
    rid = str(uuid.uuid4())
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO visit_summaries
                        (id, user_id, title, visit_date, doctor, hospital, department,
                         chief_complaint, symptoms, examination, diagnosis, treatment,
                         prescription, follow_up, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s)
                """, (
                    rid, user_id,
                    payload.title[:200],
                    payload.visit_date or date_type.today().isoformat(),
                    payload.doctor or "",
                    payload.hospital or "",
                    payload.department or "",
                    payload.chief_complaint or "",
                    payload.symptoms or "",
                    payload.examination or "",
                    payload.diagnosis or "",
                    payload.treatment or "",
                    payload.prescription or "[]",
                    payload.follow_up or "",
                    payload.notes or "",
                ))
        return rid
    except Exception:
        raise


def _delete_record(target_table: str, record_id: str):
    """失败回滚 (best-effort)."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {target_table} WHERE id=%s", (record_id,))
    except Exception as e:
        logger.warning(f"[create-record-attach] rollback failed: {e}")


# ===== Endpoint =====
@router.post("/create-record-and-attach", response_model=CreateAndAttachResponse)
async def create_record_and_attach(
    user_id: str = Query(..., description="current user"),
    body: CreateAndAttachRequest = Body(...),
):
    """一步完成: 创建 record + attach file_ids. 失败自动回滚."""
    target_table = body.target_table
    if target_table not in SUPPORTED_TABLES:
        raise HTTPException(400, f"target_table must be one of {sorted(SUPPORTED_TABLES)}, got {target_table}")

    warnings: List[str] = []

    # 1. 前置校验 file ownership (越早失败越好, 别创建了 record 又 rollback)
    file_ids = body.attached_file_ids or []
    try:
        owned_ids = _verify_files_ownership(file_ids, user_id) if file_ids else []
    except HTTPException as e:
        raise e

    if len(owned_ids) != len(file_ids):
        missing = set(file_ids) - set(owned_ids)
        warnings.append(f"these files not owned / not exist: {sorted(missing)}")
        file_ids = owned_ids  # 只 attach owned 的

    # 2. 创建 record
    try:
        if target_table == "health_records":
            payload = HealthRecordPayload(**body.record)
            rid = _create_health_record(user_id, payload)
        else:  # visit_summaries
            payload = VisitSummaryPayload(**body.record)
            rid = _create_visit_summary(user_id, payload)
    except Exception as e:
        logger.exception(f"[create-record-attach] create record failed: {e}")
        raise HTTPException(500, f"create record failed: {e}")

    # 3. attach files (单步合成接口的重点)
    if file_ids:
        try:
            _merge_metadata_attached_ids(target_table, rid, file_ids)
            _back_mark_files(file_ids, target_table, rid)
        except Exception as e:
            # 创建了 record, 但 attach 失败 — 回滚 record
            logger.exception(f"[create-record-attach] attach failed, rolling back record {rid}: {e}")
            _delete_record(target_table, rid)
            raise HTTPException(500, f"attach failed, record rolled back: {e}")

    # 4. 取回 final attached_file_ids (let 前端展示)
    final_ids: List[str] = file_ids[:]
    if file_ids:
        try:
            from .record_attach_api import _read_metadata_attached_ids
            final_ids = _read_metadata_attached_ids(target_table, rid)
        except Exception:
            final_ids = file_ids[:]

    return CreateAndAttachResponse(
        ok=True,
        record_id=rid,
        target_table=target_table,
        attached_file_ids=final_ids,
        attached_count=len(final_ids),
        warnings=warnings,
    )
