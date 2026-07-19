"""阶段48-22 v2: 业务 record attach 路由 — 业务表与 uploaded_files 的显式关联.

设计原则:
  - 上传 (upload_pipeline.py) 只管文件 + OCR.
  - 创建业务 record (这个模块) 接收 attached_file_ids 列表, 显式关联.
  - 分离关注点 — 不再有"上传 = 建档案"的副作用.

Routes:
  POST /api/health-records/{record_id}/attach-files
       body: { file_ids: [...], replace: bool }
       └─ 关联 (默认 append), 写 metadata.attached_file_ids

  POST /api/health-records/{record_id}/detach-files
       body: { file_ids: [...] }
       └─ 解除关联 (只清理 metadata, 不删 uploaded_files 行)

  POST /api/visit-summaries/{record_id}/attach-files  (同上)
  POST /api/visit-summaries/{record_id}/detach-files

  GET  /api/health-records/{record_id}/files
       └─ 取已关联的 uploaded_files 详情 (前端展示用)
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, Body, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 阶段48-22 v2: 用 v2-attach 前缀, 避开 legacy /api/health-records/* 的路由嵌套冲突
router = APIRouter(prefix="/api/v2-attach", tags=["v2-record-attach"])

# ===== DB =====
@contextmanager
def get_db():
    host = __import__("os").getenv("DB_HOST", "postgres")
    user = __import__("os").getenv("DB_USER", "pha")
    password = __import__("os").getenv("DB_PASSWORD", "")
    db = __import__("os").getenv("MEMORY_DB_NAME", "personal_health_assistant")
    dsn = __import__("os").getenv("PHA_BLOB_DSN") or f"postgresql://{user}:{password}@{host}:5432/{db}"
    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SUPPORTED_TABLES = {"health_records", "visit_summaries"}


# ===== Models =====
class AttachRequest(BaseModel):
    file_ids: List[str]
    replace: bool = False   # True=覆盖现有, False=追加


class AttachResponse(BaseModel):
    record_id: str
    attached_file_ids: List[str]
    attached_count: int
    detached_count: Optional[int] = None


class AttachedFileItem(BaseModel):
    id: str
    original_name: str
    public_url: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    ocr_status: Optional[str]
    ocr_text: Optional[str]
    created_at: Optional[str]


# ===== Helpers =====
def _verify_record_ownership(target_table: str, record_id: str, user_id: str):
    if target_table not in SUPPORTED_TABLES:
        raise HTTPException(400, f"unsupported table: {target_table}")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT user_id FROM {target_table} WHERE id = %s", (record_id,))
            r = cur.fetchone()
    if not r:
        raise HTTPException(404, f"{target_table}/{record_id} not found")
    if r["user_id"] != user_id:
        raise HTTPException(403, "this record does not belong to you")


def _verify_files_ownership(file_ids: List[str], user_id: str) -> List[str]:
    if not file_ids:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM uploaded_files WHERE user_id=%s AND id = ANY(%s)",
                (user_id, file_ids),
            )
            rows = cur.fetchall()
    owned = {r["id"] for r in rows}
    not_owned = [f for f in file_ids if f not in owned]
    if not_owned:
        raise HTTPException(403, f"you do not own these files: {not_owned}")
    return [r["id"] for r in rows]


def _replace_metadata_attached_ids(target_table: str, record_id: str, file_ids: List[str]):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE {target_table} t
                SET metadata = t.metadata || jsonb_build_object(
                                    'attached_file_ids', %s::jsonb,
                                    'attached_at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
                                ),
                    updated_at = now()
                WHERE t.id = %s
            """, (json.dumps(file_ids), record_id))


def _merge_metadata_attached_ids(target_table: str, record_id: str, new_ids: List[str]):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE {target_table} t
                SET metadata = t.metadata || jsonb_build_object(
                                    'attached_file_ids',
                                    ARRAY(
                                      SELECT DISTINCT v FROM (
                                        SELECT jsonb_array_elements_text(
                                          COALESCE(t.metadata->'attached_file_ids', '[]'::jsonb)
                                        ) AS v
                                        UNION
                                        SELECT unnest(%s::text[])
                                      ) AS x
                                    ),
                                    'attached_at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
                                ),
                    updated_at = now()
                WHERE t.id = %s
            """, (new_ids, record_id))


def _read_metadata_attached_ids(target_table: str, record_id: str) -> List[str]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT metadata->'attached_file_ids' AS afids FROM {target_table} WHERE id = %s",
                (record_id,),
            )
            r = cur.fetchone()
    if not r or not r["afids"]:
        return []
    # afids 是 JSONB array-of-string
    try:
        if isinstance(r["afids"], str):
            return json.loads(r["afids"])
        return list(r["afids"])
    except Exception:
        return []


def _back_mark_files(file_ids: List[str], target_table: str, record_id: str):
    """反向标记 uploaded_files (UI 友好, 不强制)."""
    if not file_ids:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE uploaded_files SET
                        attached_table = COALESCE(attached_table, %s),
                        attached_id = COALESCE(attached_id, %s),
                        updated_at = now()
                    WHERE id = ANY(%s)
                """, (target_table, record_id, file_ids))
    except Exception:
        pass


# ===== Attach endpoint (per table) =====
@router.post("/{target_table}/{record_id}/attach-files", response_model=AttachResponse)
async def attach_files(
    target_table: str,
    record_id: str,
    user_id: str = Query(..., description="user_id of caller"),
    body: AttachRequest = Body(...),
):
    """关联已有 uploaded_files → 业务 record. 默认追加, replace=True 覆盖."""
    # 用 repeated param 替代 body 选用更稳定的 POST form 风格. 这里走 JSON body.
    _verify_record_ownership(target_table, record_id, user_id)
    file_ids = _verify_files_ownership(body.file_ids, user_id)

    if body.replace:
        _replace_metadata_attached_ids(target_table, record_id, file_ids)
    else:
        _merge_metadata_attached_ids(target_table, record_id, file_ids)

    _back_mark_files(file_ids, target_table, record_id)

    final_ids = _read_metadata_attached_ids(target_table, record_id)
    return AttachResponse(
        record_id=record_id,
        attached_file_ids=final_ids,
        attached_count=len(file_ids),
    )


@router.post("/{target_table}/{record_id}/detach-files", response_model=AttachResponse)
async def detach_files(
    target_table: str,
    record_id: str,
    user_id: str = Query(...),
    body: AttachRequest = Body(...),
):
    """解除关联 (不删 uploaded_files 行, 不删物理文件)."""
    _verify_record_ownership(target_table, record_id, user_id)
    if not body.file_ids:
        raise HTTPException(400, "file_ids required")
    existing = _read_metadata_attached_ids(target_table, record_id)
    new_ids = [f for f in existing if f not in set(body.file_ids)]
    _replace_metadata_attached_ids(target_table, record_id, new_ids)

    return AttachResponse(
        record_id=record_id,
        attached_file_ids=new_ids,
        attached_count=0,
        detached_count=len(body.file_ids),
    )


@router.get("/{target_table}/{record_id}/files", response_model=List[AttachedFileItem])
async def list_attached_files(
    target_table: str,
    record_id: str,
    user_id: str = Query(...),
):
    """取业务 record 已关联的 uploaded_files 详情."""
    _verify_record_ownership(target_table, record_id, user_id)
    file_ids = _read_metadata_attached_ids(target_table, record_id)
    if not file_ids:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM uploaded_files WHERE id = ANY(%s) ORDER BY created_at DESC",
                (file_ids,),
            )
            rows = cur.fetchall()
    return [
        AttachedFileItem(
            id=r["id"],
            original_name=r["original_name"],
            public_url=r["public_url"],
            mime_type=r["mime_type"],
            size_bytes=r["size_bytes"],
            ocr_status=r["ocr_status"],
            ocr_text=r["ocr_text"],
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        )
        for r in rows
    ]
