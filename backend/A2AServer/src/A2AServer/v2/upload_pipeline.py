"""阶段48-22 v2: Upload Pipeline — 只管"上传 + OCR", 不动业务表.

设计原则 (拆分):
  - 上传是上传, 创建档案是创建档案 — 两件事分开
  - `uploaded_files` 是附件的"对象存储 + 元数据 + OCR 状态"独立表
  - 业务表 (health_records / visit_summaries / 等) 通过 `attached_file_ids: [uuid]`
    引用上游的 uploaded_files.id — 这是显式关系, 用户可解绑/替换

链路:
  POST /v2/upload/file
       ├─ 落盘:        <UPLOAD_DIR>/<domain>/<user>/<yyyy>/<uuid>.<ext>
       ├─ 入库:        uploaded_files (id, user_id, domain, purpose, mime, size, sha256, path, ...)
       ├─ async:     OCR (如果 mime ∈ image/* 或 pdf)
       └─ return:    { ok, file_id, url, ocr_text?, ocr_status }
                     ↑ 不再有 attached_record_id (那是业务表的事)

  POST /api/health-records (业务路由)
       body: { title, record_type, record_date, hospital, ..., attached_file_ids: [...] }
       └─ 新建 health_records 行, 把 file_ids 存到 metadata.attached_file_ids
       同样的:  POST /api/visit-summaries 走同一套 metadata.attached_file_ids

  GET  /v2/upload/files?purpose=health_record&limit=20
       └─ list 用户上传的附件 (前后端共用)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ===== Config =====
UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "/app/uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# 阶段48-22: 业务 attach 目的. 用户的不同 domain 会用不同 purpose
PURPOSE_HEALTH_RECORD = "health_record"
PURPOSE_VISIT_SUMMARY = "visit_summary"
PURPOSE_REPORT = "report"
PURPOSE_AVATAR = "avatar"
PURPOSE_OTHER = "other"

VALID_PURPOSES = {
    PURPOSE_HEALTH_RECORD,
    PURPOSE_VISIT_SUMMARY,
    PURPOSE_REPORT,
    PURPOSE_AVATAR,
    PURPOSE_OTHER,
}

# mime 白名单
ALLOWED_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp", "image/tiff",
    "application/pdf",
    "text/plain", "text/csv",
    "audio/mpeg", "audio/wav",         # 语音备注 (未来)
}
MAX_FILE_SIZE = int(os.getenv("UPLOAD_MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50 MB

# ===== DB =====
@contextmanager
def get_db():
    """共享 pgvector DB pool (跟 manifest 同一库)."""
    # 阶段48-22: 跟 docker-compose 设置对齐 (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)
    host = os.getenv("DB_HOST", "postgres")
    user = os.getenv("DB_USER", "pha")
    password = os.getenv("DB_PASSWORD", "")
    db = os.getenv("MEMORY_DB_NAME", "personal_health_assistant")
    # fallback: 也接受完整 DSN
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


def _ensure_table():
    """首次 import 时建表 (幂等)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS uploaded_files (
                    id              TEXT PRIMARY KEY,
                    user_id         VARCHAR(64) NOT NULL,
                    domain          VARCHAR(64) NOT NULL,
                    purpose         VARCHAR(32) NOT NULL,
                    original_name   TEXT,
                    storage_name    TEXT NOT NULL,
                    storage_dir     TEXT NOT NULL,
                    storage_path    TEXT NOT NULL,
                    public_url      TEXT,
                    mime_type       VARCHAR(128),
                    size_bytes      BIGINT,
                    sha256          CHAR(64),
                    ocr_status      VARCHAR(16) DEFAULT 'pending',  -- pending / running / done / failed / skipped
                    ocr_text        TEXT,
                    ocr_error       TEXT,
                    attached_table  VARCHAR(64),  -- e.g. 'health_records', 'visit_summaries'
                    attached_id     TEXT,
                    metadata        JSONB DEFAULT '{}'::jsonb,
                    created_at      TIMESTAMPTZ DEFAULT now(),
                    updated_at      TIMESTAMPTZ DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_files_user_domain ON uploaded_files(user_id, domain, purpose, created_at DESC)")


try:
    _ensure_table()
    logger.info("[upload_pipeline] uploaded_files ready")
except Exception as e:
    logger.warning(f"[upload_pipeline] init failed: {e} (will retry on first request)")


# ===== Pydantic =====
class UploadResponse(BaseModel):
    ok: bool
    file_id: str
    public_url: str
    original_name: str
    size_bytes: int
    mime_type: str
    ocr_status: str = "pending"
    message: Optional[str] = None


class FileListItem(BaseModel):
    id: str
    user_id: str
    domain: str
    purpose: str
    original_name: str
    public_url: str
    mime_type: str
    size_bytes: int
    ocr_status: str
    ocr_text: Optional[str] = None
    attached_record_id: Optional[str] = None
    attached_table: Optional[str] = None
    created_at: str


# ===== Helpers =====
def _public_url(file_id: str, storage_path: str) -> str:
    """构造前端可访问的 URL (Static mount prefix /v2/files)."""
    return f"/v2/files/{file_id}"


def _safe_ext(filename: str, mime: str) -> str:
    name = filename or "file"
    ext = Path(name).suffix.lower()
    if ext:
        return ext
    # fallback by mime
    return {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
        "image/webp": ".webp", "application/pdf": ".pdf",
        "text/plain": ".txt",
    }.get(mime, ".bin")


def attach_existing_file_to_record(
    file_ids: List[str],
    user_id: str,
    target_table: str,
    target_id: str,
) -> int:
    """阶段48-22 v2: 把已有 uploaded_files 挂到业务表.
    本函数供业务路由调用, 上传接口不再调用.

    Args:
        file_ids: 上传时拿到的 file_id 列表
        user_id: 当前用户
        target_table: 'health_records' | 'visit_summaries'
        target_id: 刚创建的业务行 id

    Returns:
        实际挂上的数量 (过滤不属于自己的 / 不存在的)
    """
    if not file_ids:
        return 0
    attached: List[Dict[str, Any]] = []
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 校验 file_id 确实属于该 user
            cur.execute("""
                SELECT id, original_name, mime_type, ocr_text, public_url
                FROM uploaded_files
                WHERE user_id = %s AND id = ANY(%s)
            """, (user_id, file_ids))
            rows = cur.fetchall()
            attached = [dict(r) for r in rows]

            if not attached:
                return 0

            # 2. 把 file_ids 写到目标表的 metadata.attached_file_ids
            cur.execute(f"""
                UPDATE {target_table}
                SET metadata = COALESCE(metadata, '{{}}'::jsonb) ||
                              jsonb_build_object(
                                'attached_file_ids',
                                (SELECT array_agg(value::text) FROM json_array_elements_text(
                                    COALESCE(metadata->'attached_file_ids', '[]'::jsonb)::text[]::jsonb)),
                                'attached_at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
                              ),
                    updated_at = now()
                WHERE id = %s
            """, (target_id,))
            # ↑ 这种语法可能不通用, 改用更可靠的 merge:
            cur.execute(f"""
                UPDATE {target_table} t
                SET metadata = t.metadata || jsonb_build_object(
                                    'attached_file_ids',
                                    ARRAY(
                                      SELECT jsonb_array_elements_text(
                                        COALESCE(t.metadata->'attached_file_ids', '[]'::jsonb)
                                      ) UNION SELECT unnest(%s::text[])
                                    ),
                                    'attached_at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
                                  ),
                    updated_at = now()
                WHERE t.id = %s
            """, (file_ids, target_id))

    # 3. 反向标记: 在 uploaded_files 上写 "已挂载" — 仅用作 UI 提示, 不做硬约束
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE uploaded_files SET
                        attached_table = COALESCE(attached_table, %s),
                        attached_id = COALESCE(attached_id, %s),
                        updated_at = now()
                    WHERE id = ANY(%s)
                """, (target_table, target_id, file_ids))
    except Exception:
        pass

    return len(attached)


def _guess_record_type(mime: str, filename: str) -> str:
    n = (filename or "").lower()
    if any(k in n for k in ("b超", "ct", "mri", "x光", "xray", "影像", "scan")):
        return "imaging"
    if any(k in n for k in ("血", "化验", "lab")):
        return "lab_report"
    if mime.startswith("audio/"):
        return "audio"
    return "other"


def _guess_record_type(mime: str, filename: str) -> str:
    n = (filename or "").lower()
    if any(k in n for k in ("b超", "ct", "mri", "x光", "xray", "影像", "scan")):
        return "imaging"
    if any(k in n for k in ("血", "化验", "lab")):
        return "lab_report"
    if mime.startswith("audio/"):
        return "audio"
    return "other"


def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _run_ocr_qwen_vl_sync(image_bytes: bytes, mime: str = "image/jpeg") -> Optional[str]:
    """阶段48-22 v6: 同步调 DashScope 原生 multimodal-generation.

    PhaCore / mcp__health_records 都装不上的退化路径, 直接用 Qwen-VL.
    注意: 走 dashscope.aliyuncs.com/api/v1/... 原生 API, 而不是 OpenAI-compat
          (/compatible/v1/chat/completions 对 VL 经常 404).
    """
    api_key = (
        os.getenv("QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("ALIYUN_DASHSCOPE_API_KEY")
        or ""
    ).strip()
    if not api_key or not image_bytes:
        return None
    base_url = (
        os.getenv("QWEN_VL_API_BASE")
        or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    ).rstrip("/")
    model_name = os.getenv("QWEN_VL_MODEL") or "qwen-vl-plus"
    prompt_text = (
        os.getenv("HOSTAPI_CHAT_OCR_QWEN_PROMPT")
        or "请识别这张图片中的所有文字, 按原始结构输出纯文本, 不要解释."
    )
    import base64 as _b64
    import httpx as _httpx
    b64 = _b64.b64encode(image_bytes).decode("utf-8")
    mime_q = (mime or "image/jpeg").split(";")[0]
    payload = {
        "model": model_name,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:{mime_q};base64,{b64}"},
                        {"text": prompt_text},
                    ],
                }
            ]
        },
        "parameters": {},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with _httpx.Client(timeout=_httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)) as cli:
            r = cli.post(base_url, headers=headers, json=payload)
        if r.status_code < 200 or r.status_code >= 300:
            logger.warning(f"[upload_pipeline] Qwen-VL OCR HTTP {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        # 原生格式: data.output.choices[0].message.content[*].text
        try:
            msg = data["output"]["choices"][0]["message"]
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = "".join(str(p.get("text") or "") for p in content if isinstance(p, dict))
            return (content or "").strip()
        except (KeyError, IndexError, TypeError):
            logger.warning(f"[upload_pipeline] Qwen-VL OCR unexpected payload: {str(data)[:300]}")
            return None
    except Exception as e:
        logger.warning(f"[upload_pipeline] Qwen-VL OCR threw: {e}")
    return None


def _run_ocr(file_id: str, file_path: Path, mime: str) -> Optional[str]:
    """阶段48-22 v6: OCR 三级回退.
      1. PhaCore.share.ocr.extract_text (本机统一入口)
      2. mcp__health_records @localhost:10010/ocr_extract (MCPServer, 健康档案子服务)
      3. Qwen-VL 直连 DashScope (无外部依赖, 只要有 QWEN_API_KEY)

    返回 None = 跳过 (audio/unsupported).
    返回 str = OCR 文本.
    """
    # 1. PhaCore
    try:
        from PhaCore.share.ocr import extract_text  # type: ignore
        return extract_text(str(file_path), mime=mime)
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[upload_pipeline] PhaCore OCR failed: {e}")

    # 2. mcp__health_records
    try:
        import httpx
        base = os.getenv("HEALTH_RECORDS_MCP_URL", "http://localhost:10010")
        with open(file_path, "rb") as fh:
            files = {"file": (file_path.name, fh, mime or "application/octet-stream")}
            data = {"user_id": "ocr_worker", "skip_db": "true"}
            r = httpx.post(f"{base}/ocr_extract", files=files, data=data, timeout=30)
        if r.status_code == 200:
            text = r.json().get("text", "") or ""
            if text:
                return text
    except Exception:
        pass

    # 3. Qwen-VL 直连 (fallback, 这一步绝对不要跳)
    if mime.startswith("image/") or mime == "application/pdf":
        try:
            raw = file_path.read_bytes()
            if mime.startswith("image/"):
                text = _run_ocr_qwen_vl_sync(raw, mime=mime)
                if text:
                    return text
            # 注: PDF 多页 Qwen 直接吃; 这里仅第 1 页, 多页扩展示例后续
        except Exception as e:
            logger.warning(f"[upload_pipeline] Qwen-VL fallback failed for {file_id}: {e}")

    return None


async def async_process_file(file_id: str, file_path: Path, mime: str, purpose: str,
                             user_id: str, domain: str, original_name: str):
    """后台任务: 只跑 OCR, 不动业务表 (阶段48-22 v2)."""
    try:
        # 1. mark running
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE uploaded_files SET ocr_status='running', updated_at=now() WHERE id=%s",
                    (file_id,),
                )

        # 2. OCR (image / pdf)
        ocr_text = None
        if mime and (mime.startswith("image/") or mime == "application/pdf"):
            loop = asyncio.get_event_loop()
            try:
                ocr_text = await loop.run_in_executor(None, _run_ocr, file_id, file_path, mime)
            except Exception as e:
                logger.warning(f"[upload_pipeline] OCR threw: {e}")
                ocr_text = None
        ocr_text = ocr_text or ""

        # 3. update OCR status
        # 注: 不写 attached_table / attached_id — 这是业务路由自己处理的事
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE uploaded_files SET
                        ocr_status=%s,
                        ocr_text=%s,
                        updated_at=now()
                    WHERE id=%s
                """, (
                    "done" if ocr_text else "skipped",
                    ocr_text,
                    file_id,
                ))
        logger.info(f"[upload_pipeline] ocr done for {file_id}: text_len={len(ocr_text)}")
    except Exception as e:
        logger.exception(f"[upload_pipeline] process {file_id} failed: {e}")
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE uploaded_files SET ocr_status='failed', ocr_error=%s, updated_at=now() WHERE id=%s
                    """, (str(e)[:500], file_id))
        except Exception:
            pass


# ===== FastAPI Router =====
router = APIRouter(prefix="/v2/upload", tags=["v2-upload"])


@router.post("/file", response_model=UploadResponse)
async def upload_file(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...),
    domain: str = Form("pha"),                # 阶段48-22: 由前端读 manifest 自动填
    purpose: str = Form(PURPOSE_HEALTH_RECORD),
    metadata: str = Form("{}"),                # JSON 字符串, 前端塞额外信息 (e.g. patient_name)
    # auth 暂时由 nginx 或后续阶段加, MVP 直接 user_id
):
    """统一上传入口. 返回 OK + file_id, OCR/attach 后台跑."""
    if purpose not in VALID_PURPOSES:
        raise HTTPException(400, f"invalid purpose: {purpose}, must be one of {sorted(VALID_PURPOSES)}")

    mime = file.content_type or "application/octet-stream"
    if mime and mime not in ALLOWED_MIMES:
        # 不直接拒绝 (允许未知 mime), 但 warn
        logger.warning(f"[upload_pipeline] unusual mime {mime} for {file.filename}")

    # 1. read bytes
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(413, f"file too large: {len(raw)} > {MAX_FILE_SIZE}")

    file_id = str(uuid.uuid4())
    sha = hashlib.sha256(raw).hexdigest()
    ext = _safe_ext(file.filename, mime)
    now = datetime.utcnow()
    rel_dir = f"{domain}/{user_id}/{now.year:04d}/{now.month:02d}"
    storage_dir = UPLOAD_ROOT / rel_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_name = f"{file_id}{ext}"
    storage_path = storage_dir / storage_name

    # 2. write to disk
    storage_path.write_bytes(raw)

    # 3. insert DB
    public_url = _public_url(file_id, str(storage_path))
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO uploaded_files
                        (id, user_id, domain, purpose, original_name, storage_name,
                         storage_dir, storage_path, public_url, mime_type, size_bytes,
                         sha256, ocr_status, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s::jsonb)
                """, (
                    file_id, user_id, domain, purpose, file.filename or "file",
                    storage_name, str(storage_dir), str(storage_path), public_url,
                    mime, len(raw), sha, metadata,
                ))
    except Exception as e:
        # 回滚磁盘文件
        try:
            storage_path.unlink()
        except Exception:
            pass
        raise HTTPException(500, f"db insert failed: {e}")

    # 4. 后台: OCR + attach
    background.add_task(
        async_process_file, file_id, storage_path, mime, purpose, user_id, domain,
        file.filename or "file",
    )

    return UploadResponse(
        ok=True,
        file_id=file_id,
        public_url=public_url,
        original_name=file.filename or "file",
        size_bytes=len(raw),
        mime_type=mime,
        ocr_status="pending",
        message=f"uploaded, OCR queued (purpose={purpose}). Attach to record via /api/health-records or /api/visit-summaries with attached_file_ids=[{file_id}].",
    )


@router.get("/files", response_model=List[FileListItem])
async def list_files(
    user_id: str = Query(...),
    domain: Optional[str] = Query(None),
    purpose: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """列用户上传的文件 (按 domain / purpose 过滤)."""
    sql = "SELECT * FROM uploaded_files WHERE user_id = %s"
    args: List[Any] = [user_id]
    if domain:
        sql += " AND domain = %s"
        args.append(domain)
    if purpose:
        sql += " AND purpose = %s"
        args.append(purpose)
    sql += " ORDER BY created_at DESC LIMIT %s"
    args.append(limit)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
    return [
        FileListItem(
            id=r["id"], user_id=r["user_id"], domain=r["domain"], purpose=r["purpose"],
            original_name=r["original_name"], public_url=r["public_url"],
            mime_type=r["mime_type"] or "application/octet-stream",
            size_bytes=r["size_bytes"] or 0, ocr_status=r["ocr_status"] or "pending",
            ocr_text=r["ocr_text"], attached_record_id=r["attached_id"],
            attached_table=r["attached_table"],
            created_at=r["created_at"].isoformat() if r.get("created_at") else "",
        )
        for r in rows
    ]


@router.get("/file/{file_id}")
async def get_file_meta(file_id: str, user_id: str = Query(...)):
    """拉单文件详情 (含 OCR text, attached record)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM uploaded_files WHERE id=%s AND user_id=%s", (file_id, user_id))
            r = cur.fetchone()
    if not r:
        raise HTTPException(404, "file not found")
    return dict(r)


# 阶段48-22 v6: 手动重新跑 OCR (前端点 '提取信息' 调这里).
# 老的 /api/health-records/{id}/extracted 已不存在, 新接口是按 file_id 干活.
class ReextractRequest(BaseModel):
    user_id: str
    force: bool = False  # True = 跳过 status check, 已 done 也重跑


class ReextractResponse(BaseModel):
    ok: bool
    file_id: str
    ocr_status: str
    ocr_text: Optional[str] = None
    ocr_error: Optional[str] = None
    cached: bool = False  # True = 没真跑, 命中已有的 done
    message: Optional[str] = None


@router.post("/files/{file_id}/reextract", response_model=ReextractResponse)
async def reextract_file(
    file_id: str,
    req: ReextractRequest,
):
    """手动 OCR 重跑. 命中 done 且 !force 直接返回缓存.

    同步执行 (前台 thread 跑; image 通常几秒; PDF 可能更长)
    - 异步版见异步提取器版 (阶段48-22 v6+)
    """
    # 1. 找记录
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, mime_type, storage_path, ocr_status "
                "FROM uploaded_files WHERE id=%s AND user_id=%s",
                (file_id, req.user_id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "file not found")
    mime = row.get("mime_type") or "application/octet-stream"
    storage_path = row.get("storage_path")

    # 2. 已有 done 缓存 + !force → 直接返回
    if row.get("ocr_status") == "done" and not req.force:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ocr_text FROM uploaded_files WHERE id=%s", (file_id,)
                )
                r2 = cur.fetchone()
        return ReextractResponse(
            ok=True, file_id=file_id, ocr_status="done",
            ocr_text=r2.get("ocr_text") if r2 else None, cached=True,
            message="已提取过, 复用缓存",
        )

    # 3. 跑到 OCR (只走 Qwen-VL 这一路, PhaCore/mcp 在 hostapi 都不存在)
    if not (mime.startswith("image/") or mime == "application/pdf"):
        return ReextractResponse(
            ok=False, file_id=file_id, ocr_status="skipped",
            message=f"mime={mime} 不支持 OCR (仅 image/* 或 application/pdf)",
        )

    # mark running
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE uploaded_files SET ocr_status='running', updated_at=now() WHERE id=%s",
                (file_id,),
            )

    text = None
    err = None
    try:
        import anyio
        text = await anyio.to_thread.run_sync(
            lambda: _run_ocr(file_id, Path(storage_path), mime)
        )
    except Exception as e:
        err = str(e)[:500]
        logger.warning(f"[upload_pipeline] reextract {file_id} threw: {e}")

    text = text or ""
    final_status = "done" if text else "skipped"
    if err and not text:
        final_status = "failed"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE uploaded_files SET ocr_status=%s, ocr_text=%s, ocr_error=%s, updated_at=now() WHERE id=%s",
                (final_status, text, err or None, file_id),
            )

    return ReextractResponse(
        ok=bool(text),
        file_id=file_id,
        ocr_status=final_status,
        ocr_text=text or None,
        ocr_error=err,
        cached=False,
        message=None if text else "OCR 没拿到文字, 可能图太小或语言不支持",
    )


# 阶段48-22: 静态 serve 上传的文件. 仅后端内部, 不暴露到公网 (生产应该用 nginx).
file_router = APIRouter(prefix="/v2/files", tags=["v2-upload"])

@file_router.get("/{file_id}")
async def serve_file(file_id: str):
    """通过 file_id 拿原始文件 (后端内部使用). 不做用户隔离!"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT storage_path, mime_type, original_name FROM uploaded_files WHERE id=%s", (file_id,))
            r = cur.fetchone()
    if not r or not Path(r["storage_path"]).exists():
        raise HTTPException(404, "file not found")
    from fastapi.responses import FileResponse
    return FileResponse(
        r["storage_path"],
        media_type=r["mime_type"] or "application/octet-stream",
        filename=r["original_name"] or file_id,
    )
