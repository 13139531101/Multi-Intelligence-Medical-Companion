from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse as _FileResponse, HTMLResponse
from pydantic import BaseModel, Field
try:
    from pydantic import ConfigDict
except Exception:
    ConfigDict = None
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import json
import os
import asyncio
import uuid
import hashlib
from pathlib import Path
import logging
from contextlib import contextmanager
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit
import requests
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool
import jwt
import re
import anyio
from services import consultations_service
from services import dashboard_service
from services import health_records_service
from services import visit_summaries_service

FileResponse = _FileResponse
try:
    from api.schemas.models import (
        Consultation,
        DashboardActivity,
        DashboardStats,
        HealthInsightsResponse,
        HealthRecord,
        HealthRecordCreate,
        HealthRecordUpdate,
        HealthStatistics,
        ImportanceLevel,
        RecordType,
        VisitSummary,
        VisitSummaryCreate,
    )
except Exception:
    import importlib.util
    import sys

    _models_path = (
        Path(__file__).resolve().parent / "api" / "schemas" / "models.py"
    )
    _spec = importlib.util.spec_from_file_location(
        "_backend_api_schemas_models", str(_models_path)
    )
    if _spec is None or _spec.loader is None:
        raise
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
    try:
        _mod.DashboardStats.model_rebuild()
    except Exception:
        pass
    Consultation = _mod.Consultation
    DashboardActivity = _mod.DashboardActivity
    DashboardStats = _mod.DashboardStats
    HealthInsightsResponse = _mod.HealthInsightsResponse
    HealthRecord = _mod.HealthRecord
    HealthRecordCreate = _mod.HealthRecordCreate
    HealthRecordUpdate = _mod.HealthRecordUpdate
    HealthStatistics = _mod.HealthStatistics
    ImportanceLevel = _mod.ImportanceLevel
    RecordType = _mod.RecordType
    VisitSummary = _mod.VisitSummary
    VisitSummaryCreate = _mod.VisitSummaryCreate

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 可选：加载OCR与记忆服务（如果不可用则降级跳过）
try:
    from HealthRecordsManager.mcpserver.ocr_tool import (
        extract_text_from_image,
        validate_medical_document,
    )

    try:
        from HealthRecordsManager.mcpserver.data_extraction_tool import (
            extract_medical_info,
        )
    except Exception:
        extract_medical_info = None  # 非必需
    try:
        from HealthRecordsManager.mcpserver.data_extraction_tool import (
            extract_test_results,
        )
    except Exception:
        extract_test_results = None  # 非必需
except Exception as _import_err:
    logger.warning(f"可选OCR/记忆模块加载失败，将跳过OCR与入库: {_import_err}")
    extract_text_from_image = None
    validate_medical_document = None
    extract_medical_info = None
    extract_test_results = None

health_records_memory_service = None

# 独立：导入HRM存储工具（不受记忆系统导入失败影响）
try:
    import importlib
    import sys

    # 解决 storage_tool 内部使用非限定导入 `database_config` 的问题
    # 预先将 HealthRecordsManager.database_config 注入到 sys.modules，使其解析为正确模块
    hrm_db_config = importlib.import_module(
        "HealthRecordsManager.database_config"
    )
    sys.modules["database_config"] = hrm_db_config

    from HealthRecordsManager.mcpserver.storage_tool import save_health_record as HRM_SAVE_RECORD  # type: ignore
except Exception as _hrm_err:
    logger.warning(f"HRM存储工具加载失败，将跳过双写: {_hrm_err}")
    HRM_SAVE_RECORD = None  # type: ignore


_health_records_memory_import_attempted = False


def _get_health_records_memory_service():
    global health_records_memory_service, _health_records_memory_import_attempted
    if health_records_memory_service is not None:
        return health_records_memory_service
    if _health_records_memory_import_attempted:
        return None
    _health_records_memory_import_attempted = True
    try:
        enable_memory_flag = os.getenv("ENABLE_AGENT_MEMORY", "true").lower()
        skip_memory_init = os.getenv("SKIP_MEMORY_INIT", "0") == "1"
        if enable_memory_flag not in ("true", "1") or skip_memory_init:
            return None
    except Exception:
        pass
    try:
        from HealthRecordsManager.memory_service import (
            health_records_memory_service as _svc,
        )

        health_records_memory_service = _svc
        return health_records_memory_service
    except Exception as e:
        logger.warning(f"记忆服务导入失败，将以无记忆模式运行: {e}")
        health_records_memory_service = None
        return None


# 创建FastAPI应用
app = FastAPI(
    title="健康档案管理API",
    description="提供健康档案的创建、查询、更新、删除等功能",
    version="1.0.0",
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 数据模型定义

MODULE_DIR = Path(__file__).resolve().parent
_upload_dir_env = os.getenv("HEALTH_RECORDS_UPLOAD_DIR", "").strip()
if _upload_dir_env:
    UPLOAD_DIR = Path(_upload_dir_env)
elif Path("/app").exists():
    UPLOAD_DIR = Path("/app/uploads")
else:
    UPLOAD_DIR = MODULE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "pha"),
    "password": os.getenv("DB_PASSWORD", "pha_pass"),
    "dbname": os.getenv(
        "DB_NAME", os.getenv("POSTGRES_DB", "personal_health_assistant")
    ),
    "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", 3)),
}

_RAG_VECTOR_DIM = 384
_RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL") or os.getenv(
    "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)
_rag_schema_ready = False
_embedding_service = None

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "your-secret-key-change-this-in-production"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

_db_pool: ConnectionPool | None = None
_db_pool_init_attempted = False


def _build_db_dsn() -> str:
    def _with_connect_timeout(raw_dsn: str) -> str:
        dsn_text = str(raw_dsn or "").strip()
        if not dsn_text:
            return dsn_text
        try:
            timeout_val = int(DB_CONFIG.get("connect_timeout") or 3)
        except Exception:
            timeout_val = 3
        try:
            parts = urlsplit(dsn_text)
            query_items = parse_qsl(parts.query, keep_blank_values=True)
            q = {k: v for k, v in query_items}
            if not str(q.get("connect_timeout") or "").strip():
                q["connect_timeout"] = str(max(timeout_val, 1))
            new_query = urlencode(q)
            return urlunsplit(
                (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
            )
        except Exception:
            sep = "&" if "?" in dsn_text else "?"
            return f"{dsn_text}{sep}connect_timeout={max(timeout_val, 1)}"

    dsn = os.getenv("DATABASE_URL")
    if isinstance(dsn, str) and dsn.strip():
        return _with_connect_timeout(dsn.strip())
    user = DB_CONFIG.get("user") or "pha"
    password = DB_CONFIG.get("password") or ""
    host = DB_CONFIG.get("host") or "localhost"
    port = DB_CONFIG.get("port") or 5432
    dbname = DB_CONFIG.get("dbname") or "personal_health_assistant"
    auth = f"{user}:{password}" if password else f"{user}"
    return _with_connect_timeout(f"postgresql://{auth}@{host}:{port}/{dbname}")


def _get_db_pool() -> ConnectionPool | None:
    global _db_pool, _db_pool_init_attempted
    if _db_pool is not None:
        return _db_pool
    if _db_pool_init_attempted:
        return None
    _db_pool_init_attempted = True
    try:
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", "20"))
        timeout = float(os.getenv("DB_POOL_TIMEOUT", "5"))
        _db_pool = ConnectionPool(
            _build_db_dsn(), max_size=max(max_size, 1), timeout=timeout
        )
        return _db_pool
    except Exception as e:
        logger.warning(f"DB连接池初始化失败，将回退为直连: {e}")
        _db_pool = None
        return None


_upload_limiter: anyio.CapacityLimiter | None = None


def _get_upload_limiter() -> anyio.CapacityLimiter:
    global _upload_limiter
    if _upload_limiter is None:
        try:
            n = int(os.getenv("HEALTH_RECORDS_UPLOAD_MAX_CONCURRENCY", "8"))
        except Exception:
            n = 8
        _upload_limiter = anyio.CapacityLimiter(max(n, 1))
    return _upload_limiter


def _get_embedding_service():
    global _embedding_service
    if _embedding_service is not None:
        return _embedding_service
    try:
        from embedding_manager import EmbeddingService  # type: ignore
    except Exception:
        _embedding_service = None
        return _embedding_service
    try:
        _embedding_service = EmbeddingService(model_name=_RAG_EMBEDDING_MODEL)
        dim = getattr(_embedding_service, "dimension", None)
        if dim is not None and int(dim) != _RAG_VECTOR_DIM:
            _embedding_service = None
        return _embedding_service
    except Exception:
        _embedding_service = None
        return _embedding_service


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def _rag_chunk_settings() -> dict[str, int]:
    try:
        chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "650"))
    except Exception:
        chunk_size = 650
    try:
        overlap = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
    except Exception:
        overlap = 120
    try:
        max_chunks = int(os.getenv("RAG_MAX_CHUNKS", "0"))
    except Exception:
        max_chunks = 0

    if chunk_size <= 0:
        chunk_size = 650
    if overlap < 0:
        overlap = 0
    if max_chunks < 0:
        max_chunks = 0
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)
    return {"chunk_size": chunk_size, "overlap": overlap, "max_chunks": max_chunks}


def _rag_chunk_mode() -> str:
    v = (os.getenv("RAG_CHUNK_MODE", "") or "").strip().lower()
    if v in ("semantic", "sentence", "meaning"):
        return "semantic"
    if v in ("paragraph", "para", "sections", "section"):
        return "paragraph"
    return "sliding"


def _rag_chunk_mode_for_source(source_type: str) -> str:
    st = (source_type or "").strip().lower()
    if st == "medical_kb":
        v = (os.getenv("RAG_CHUNK_MODE_MEDICAL_KB", "") or "").strip().lower()
        if v:
            if v in ("semantic", "sentence", "meaning"):
                return "semantic"
            if v in ("paragraph", "para", "sections", "section"):
                return "paragraph"
            return "sliding"
        return "semantic"
    return _rag_chunk_mode()


def _split_text_for_rag_sliding(
    s: str, *, chunk_size: int, overlap: int, max_chunks: int
) -> list[str]:
    if not s:
        return []
    chunks: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        j = min(n, i + chunk_size)
        chunk = s[i:j].strip()
        if chunk:
            chunks.append(chunk)
            if max_chunks and len(chunks) >= max_chunks:
                break
        if j >= n:
            break
        i = max(0, j - overlap)
    return chunks


def _split_text_for_rag_paragraph(
    s: str, *, chunk_size: int, overlap: int, max_chunks: int
) -> list[str]:
    if not s:
        return []

    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return []

    paragraphs: list[str] = []
    buf: list[str] = []
    for line in s.split("\n"):
        if line.strip():
            buf.append(line.rstrip())
            continue
        if buf:
            paragraphs.append("\n".join(buf).strip())
            buf = []
    if buf:
        paragraphs.append("\n".join(buf).strip())

    chunks: list[str] = []
    prefix = ""
    current = ""

    def flush_current() -> None:
        nonlocal prefix, current
        c = (current or "").strip()
        if not c:
            current = prefix
            return
        chunks.append(c)
        if max_chunks and len(chunks) >= max_chunks:
            current = ""
            prefix = ""
            return
        prefix = c[-overlap:] if overlap else ""
        current = prefix

    for p in paragraphs:
        if max_chunks and len(chunks) >= max_chunks:
            break
        para = (p or "").strip()
        if not para:
            continue

        if len(para) > chunk_size:
            if (current or "").strip() and (current or "").strip() != (prefix or "").strip():
                flush_current()
                if max_chunks and len(chunks) >= max_chunks:
                    break

            slices = _split_text_for_rag_sliding(
                para, chunk_size=chunk_size, overlap=overlap, max_chunks=0
            )
            for idx, sl in enumerate(slices):
                if max_chunks and len(chunks) >= max_chunks:
                    break
                if idx == 0 and prefix and len(prefix) + 2 + len(sl) <= chunk_size:
                    c = (prefix + "\n\n" + sl).strip()
                else:
                    c = (sl or "").strip()
                if c:
                    chunks.append(c)
                    prefix = c[-overlap:] if overlap else ""
                    current = prefix
            continue

        sep = "\n\n" if (current or "").strip() else ""
        candidate = (current + sep + para) if sep else (current + para)
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if (current or "").strip() and (current or "").strip() != (prefix or "").strip():
            flush_current()
            if max_chunks and len(chunks) >= max_chunks:
                break

        if prefix:
            candidate2 = (prefix + "\n\n" + para).strip()
            if len(candidate2) <= chunk_size:
                current = candidate2
            else:
                current = para
        else:
            current = para

    tail = (current or "").strip()
    if tail:
        if not overlap or not chunks or tail != (chunks[-1][-overlap:] if overlap and len(chunks[-1]) >= overlap else ""):
            chunks.append(tail)

    if max_chunks:
        return chunks[:max_chunks]
    return chunks


def _split_text_for_rag_semantic(
    s: str, *, chunk_size: int, overlap: int, max_chunks: int
) -> list[str]:
    if not s:
        return []
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return []
    chunk_size = max(50, int(chunk_size))
    overlap = max(0, int(overlap))
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)

    def is_heading(block: str) -> bool:
        b = (block or "").strip()
        if not b:
            return False
        lines = [ln.strip() for ln in b.split("\n") if ln.strip()]
        if len(lines) != 1:
            return False
        ln = lines[0]
        if ln.startswith("#"):
            return True
        if re.match(r"^第[0-9一二三四五六七八九十百千]+[章节部分篇].*$", ln):
            return True
        if re.match(r"^[0-9]{1,2}(\.[0-9]{1,3})+\s+.+$", ln):
            return True
        if re.match(r"^[0-9]{1,2}、.+$", ln):
            return True
        return False

    def split_sentences(text: str) -> list[str]:
        t = re.sub(r"[ \t]+", " ", (text or "").strip())
        if not t:
            return []
        parts = re.split(r"(……|…|[。！？!?]+)", t)
        out: list[str] = []
        i = 0
        while i < len(parts):
            seg = parts[i] or ""
            end = ""
            if i + 1 < len(parts) and parts[i + 1]:
                end = parts[i + 1]
            s2 = (seg + end).strip()
            if s2:
                out.append(s2)
            i += 2
        if not out:
            out = [t]
        return out

    def split_block_to_pieces(block: str) -> list[str]:
        b = (block or "").strip()
        if not b:
            return []
        lines = [ln.rstrip() for ln in b.split("\n")]
        is_list = True
        for ln in lines:
            x = ln.strip()
            if not x:
                continue
            if not re.match(r"^(\-|\*|\+|\d+[\.\)、])\s+.+$", x):
                is_list = False
                break
        if is_list:
            pieces = []
            for ln in lines:
                x = ln.strip()
                if x:
                    pieces.append(x)
            return pieces or [b]
        if len(b) <= chunk_size:
            return [b]
        sentences = split_sentences(b.replace("\n", " ").strip())
        return sentences if sentences else [b]

    blocks: list[str] = []
    buf: list[str] = []
    for line in s.split("\n"):
        if line.strip():
            buf.append(line.rstrip())
            continue
        if buf:
            blocks.append("\n".join(buf).strip())
            buf = []
    if buf:
        blocks.append("\n".join(buf).strip())

    chunks: list[str] = []
    cur_pieces: list[str] = []
    pending_heading = ""

    def cur_len(pieces: list[str]) -> int:
        if not pieces:
            return 0
        n = 0
        for p in pieces:
            if not p:
                continue
            if n:
                n += 2
            n += len(p)
        return n

    def join_pieces(pieces: list[str]) -> str:
        out = []
        for p in pieces:
            if not p:
                continue
            if out:
                out.append("\n\n")
            out.append(p)
        return "".join(out).strip()

    def overlap_tail(pieces: list[str]) -> list[str]:
        if not overlap or not pieces:
            return []
        tail: list[str] = []
        total = 0
        for p in reversed(pieces):
            if not p:
                continue
            add = len(p) + (2 if tail else 0)
            if tail and total + add > overlap:
                break
            tail.append(p)
            total += add
            if total >= overlap:
                break
        tail.reverse()
        return tail

    def flush() -> None:
        nonlocal cur_pieces
        txt = join_pieces(cur_pieces)
        if txt:
            chunks.append(txt)
        cur_pieces = overlap_tail(cur_pieces)

    for block in blocks:
        if max_chunks and len(chunks) >= max_chunks:
            break
        if is_heading(block):
            pending_heading = (block or "").strip()
            continue
        pieces = split_block_to_pieces(block)
        for piece in pieces:
            if max_chunks and len(chunks) >= max_chunks:
                break
            p = (piece or "").strip()
            if not p:
                continue
            if pending_heading:
                combined = pending_heading + "\n" + p
                pending_heading = ""
                p = combined
            if not cur_pieces:
                cur_pieces = [p]
                continue
            if cur_len(cur_pieces + [p]) <= chunk_size:
                cur_pieces.append(p)
                continue
            flush()
            if cur_pieces and cur_len(cur_pieces + [p]) <= chunk_size:
                cur_pieces.append(p)
            else:
                cur_pieces = [p]

    if pending_heading:
        if not cur_pieces:
            cur_pieces = [pending_heading]
        elif cur_len(cur_pieces + [pending_heading]) <= chunk_size:
            cur_pieces.append(pending_heading)
        else:
            flush()
            cur_pieces = [pending_heading]

    if cur_pieces and (not max_chunks or len(chunks) < max_chunks):
        txt = join_pieces(cur_pieces)
        if txt:
            chunks.append(txt)

    if max_chunks:
        return chunks[:max_chunks]
    return chunks


def _split_text_for_rag(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
    max_chunks: int | None = None,
    chunk_mode: str | None = None,
) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    st = _rag_chunk_settings()
    chunk_size = int(st["chunk_size"] if chunk_size is None else chunk_size)
    overlap = int(st["overlap"] if overlap is None else overlap)
    max_chunks = int(st["max_chunks"] if max_chunks is None else max_chunks)

    if chunk_size <= 0:
        chunk_size = 650
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)
    if max_chunks < 0:
        max_chunks = 0

    mode = (chunk_mode or "").strip().lower() or _rag_chunk_mode()
    if mode == "semantic":
        return _split_text_for_rag_semantic(
            s, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks
        )
    if mode == "paragraph":
        return _split_text_for_rag_paragraph(
            s, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks
        )
    return _split_text_for_rag_sliding(
        s, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks
    )


def _ensure_rag_schema(cursor) -> None:
    global _rag_schema_ready
    if _rag_schema_ready:
        return
    try:
        try:
            cursor.execute(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1"
            )
            has_vector = bool(cursor.fetchone())
        except Exception:
            has_vector = False

        if not has_vector:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_documents (
                user_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                record_type TEXT,
                title TEXT,
                full_text TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dim INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (user_id, source_type, source_id, embedding_model)
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                record_type TEXT,
                title TEXT,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dim INTEGER NOT NULL,
                embedding vector(384) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (user_id, source_type, source_id, chunk_index, embedding_model)
            );
            """
        )
        cursor.execute(
            """
            ALTER TABLE rag_chunks
            DROP CONSTRAINT IF EXISTS
                rag_chunks_source_type_source_id_chunk_index_embedding_model_key;
            """
        )
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'rag_chunks_user_source_chunk_model_key'
                ) THEN
                    ALTER TABLE rag_chunks
                    ADD CONSTRAINT rag_chunks_user_source_chunk_model_key
                    UNIQUE (
                        user_id,
                        source_type,
                        source_id,
                        chunk_index,
                        embedding_model
                    );
                END IF;
            END
            $$;
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_user ON rag_documents(user_id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_user_source ON rag_documents(user_id, source_type);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents(source_type, source_id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_updated ON rag_documents(updated_at);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user ON rag_chunks(user_id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user_source ON rag_chunks(user_id, source_type);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_source ON rag_chunks(source_type, source_id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_created ON rag_chunks(created_at);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
        )
        _rag_schema_ready = True
    except Exception:
        _rag_schema_ready = False
        try:
            conn = getattr(cursor, "connection", None)
            if conn is not None:
                conn.rollback()
        except Exception:
            pass
        raise


def _make_rag_text(
    title: str | None, summary: str | None, content: str | None
) -> str:
    parts = []
    if title and str(title).strip():
        parts.append(f"标题: {str(title).strip()}")
    if summary and str(summary).strip():
        parts.append(f"摘要: {str(summary).strip()}")
    if content and str(content).strip():
        parts.append(f"内容: {str(content).strip()}")
    return "\n".join(parts).strip()


def _upsert_rag_document(
    cursor,
    user_id: str,
    source_type: str,
    source_id: str,
    record_type: str | None,
    title: str | None,
    text: str,
) -> int:
    es = _get_embedding_service()
    if es is None:
        return 0
    if not text or not text.strip():
        return 0

    _ensure_rag_schema(cursor)

    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        cursor.execute(
            """
            SELECT text_sha256
            FROM rag_documents
            WHERE user_id = %s
              AND source_type = %s
              AND source_id = %s
              AND embedding_model = %s
            LIMIT 1
            """,
            (user_id, source_type, source_id, es.model_name),
        )
        row = cursor.fetchone()
        existing_sha = None
        if row:
            if isinstance(row, dict):
                existing_sha = row.get("text_sha256")
            elif isinstance(row, (list, tuple)):
                existing_sha = row[0]
            else:
                existing_sha = getattr(row, "text_sha256", None)
        if existing_sha and str(existing_sha) == text_sha256:
            return 0
    except Exception:
        pass

    chunks = _split_text_for_rag(
        text, chunk_mode=_rag_chunk_mode_for_source(source_type)
    )
    if not chunks:
        return 0

    embs = es.generate_batch_embeddings(chunks)
    valid: list[tuple[int, str, list[float]]] = []
    for idx, (ch, emb) in enumerate(zip(chunks, embs)):
        if not emb:
            continue
        if len(emb) != _RAG_VECTOR_DIM:
            continue
        valid.append((idx, ch, emb))
    if not valid:
        return 0

    now = datetime.now()

    cursor.execute(
        """
        INSERT INTO rag_documents (
            user_id, source_type, source_id, record_type, title,
            full_text, text_sha256,
            embedding_model, embedding_dim, chunk_count,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (user_id, source_type, source_id, embedding_model)
        DO UPDATE SET
            record_type = EXCLUDED.record_type,
            title = EXCLUDED.title,
            full_text = EXCLUDED.full_text,
            text_sha256 = EXCLUDED.text_sha256,
            embedding_dim = EXCLUDED.embedding_dim,
            chunk_count = EXCLUDED.chunk_count,
            updated_at = EXCLUDED.updated_at
        """,
        (
            user_id,
            source_type,
            source_id,
            record_type,
            title,
            text,
            text_sha256,
            es.model_name,
            _RAG_VECTOR_DIM,
            len(valid),
            now,
            now,
        ),
    )

    cursor.execute(
        """
        DELETE FROM rag_chunks
        WHERE user_id = %s AND source_type = %s AND source_id = %s AND embedding_model = %s
        """,
        (user_id, source_type, source_id, es.model_name),
    )

    inserted = 0
    for chunk_index, chunk_text, emb in valid:
        cursor.execute(
            """
            INSERT INTO rag_chunks (
                id, user_id, source_type, source_id, record_type, title,
                chunk_index, chunk_text, embedding_model, embedding_dim, embedding,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s::vector(384),
                %s, %s
            )
            ON CONFLICT (user_id, source_type, source_id, chunk_index, embedding_model)
            DO UPDATE SET
                user_id = EXCLUDED.user_id,
                record_type = EXCLUDED.record_type,
                title = EXCLUDED.title,
                chunk_text = EXCLUDED.chunk_text,
                embedding_dim = EXCLUDED.embedding_dim,
                embedding = EXCLUDED.embedding,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(uuid.uuid4()),
                user_id,
                source_type,
                source_id,
                record_type,
                title,
                chunk_index,
                chunk_text,
                es.model_name,
                len(emb),
                _vector_literal(emb),
                now,
                now,
            ),
        )
        inserted += 1
    return inserted


@contextmanager
def get_db_connection():
    pool = _get_db_pool()
    if pool is not None:
        with pool.connection() as conn:
            try:
                conn.autocommit = False
            except Exception:
                pass
            yield conn
        return

    conn = psycopg.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_database():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception:
                conn.rollback()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS health_records (
                    id UUID PRIMARY KEY,
                    user_id TEXT,
                    title TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    summary TEXT,
                    content TEXT,
                    importance TEXT NOT NULL DEFAULT 'medium',
                    tags JSONB,
                    metadata JSONB,
                    record_date DATE,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS file_attachments (
                    id UUID PRIMARY KEY,
                    record_id UUID REFERENCES health_records(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    mime_type TEXT,
                    upload_time TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS visit_summaries (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    visit_date DATE,
                    doctor TEXT,
                    hospital TEXT,
                    department TEXT,
                    chief_complaint TEXT,
                    symptoms TEXT,
                    examination TEXT,
                    diagnosis TEXT,
                    treatment TEXT,
                    prescription TEXT,
                    follow_up TEXT,
                    summary_content TEXT,
                    notes TEXT,
                    files JSONB,
                    tests JSONB,
                    status TEXT DEFAULT 'done',
                    error_message TEXT,
                    is_deleted SMALLINT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            # Add columns if they don't exist (migration for existing table)
            alter_stmts = [
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS title TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS doctor TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS hospital TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS department TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS chief_complaint TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS symptoms TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS examination TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS treatment TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS prescription TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS follow_up TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS summary_content TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS notes TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS files JSONB",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS tests JSONB",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'done'",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS error_message TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS is_deleted SMALLINT DEFAULT 0",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()",
            ]
            for stmt in alter_stmts:
                try:
                    cursor.execute(stmt)
                except Exception as e:
                    logger.warning(f"Column migration skipped: {e}")
                    conn.rollback()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS consultations (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    consultation_id VARCHAR(64) UNIQUE,
                    session_id VARCHAR(64),
                    question TEXT,
                    answer TEXT,
                    tags JSONB,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id UUID PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    record_type TEXT,
                    title TEXT,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    embedding vector(384) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (
                        user_id,
                        source_type,
                        source_id,
                        chunk_index,
                        embedding_model
                    )
                )
                """
            )
            cursor.execute(
                """
                ALTER TABLE rag_chunks
                DROP CONSTRAINT IF EXISTS
                    rag_chunks_source_type_source_id_chunk_index_embedding_model_key
                """
            )
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'rag_chunks_user_source_chunk_model_key'
                    ) THEN
                        ALTER TABLE rag_chunks
                        ADD CONSTRAINT rag_chunks_user_source_chunk_model_key
                        UNIQUE (
                            user_id,
                            source_type,
                            source_id,
                            chunk_index,
                            embedding_model
                        );
                    END IF;
                END
                $$;
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user ON rag_chunks(user_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user_source ON rag_chunks(user_id, source_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_source ON rag_chunks(source_type, source_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_created ON rag_chunks(created_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id VARCHAR(64) PRIMARY KEY,
                    consultation_id VARCHAR(64) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            conn.commit()
            logger.info("数据库初始化完成")


# 工具函数
def generate_id() -> str:
    """生成唯一ID"""
    return str(uuid.uuid4())


def serialize_tags(tags: List[str]) -> str:
    """序列化标签列表"""
    return json.dumps(tags) if tags else "[]"


def deserialize_tags(tags_str: str) -> List[str]:
    """反序列化标签列表"""
    try:
        return json.loads(tags_str) if tags_str else []
    except json.JSONDecodeError:
        return []


def serialize_metadata(metadata: Dict[str, Any]) -> str:
    """序列化元数据"""
    return json.dumps(metadata) if metadata else "{}"


def deserialize_metadata(metadata_str: str) -> Dict[str, Any]:
    """反序列化元数据"""
    try:
        return json.loads(metadata_str) if metadata_str else {}
    except json.JSONDecodeError:
        return {}


def _coerce_float_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _split_bp_value(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", s)
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except Exception:
        return None


def _format_date_value(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value)
    return s[:10] if len(s) >= 10 else s


def _ensure_dict_value(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            v = json.loads(value)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


def _ensure_list_value(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            v = json.loads(value)
            return v if isinstance(v, list) else []
        except Exception:
            return []
    return []


def _looks_like_unit(unit: str | None) -> bool:
    s = (unit or "").strip()
    if not s:
        return False
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    low = s.lower()
    unit_tokens = {
        "mmhg",
        "mmol/l",
        "mmol\\l",
        "μmol/l",
        "umol/l",
        "umol\\l",
        "mg/dl",
        "mg\\dl",
        "g/dl",
        "g\\dl",
        "g/l",
        "g\\l",
        "%",
        "％",
        "fl",
        "pg",
        "bpm",
        "mm",
        "cm",
        "m",
        "kg",
        "g",
        "mg",
        "ng",
        "μg",
        "l",
        "dl",
        "ml",
        "μl",
        "ul",
        "u/l",
        "iu/l",
    }
    if low in unit_tokens:
        return True
    if "/" in low or "%" in low or "×" in s or "^" in s:
        return True
    return False


def _is_valid_test_name(name: str, unit: str = "") -> bool:
    text = (name or "").strip()
    if not text:
        return False
    if len(text) > 24:
        return False
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"[0-9.]+", compact):
        return False
    if re.fullmatch(r"[一二三四五六七八九十百千万两]+", compact):
        return False
    if re.fullmatch(r"[+\-*/=<>≤≥]+", compact):
        return False
    lower = compact.lower()
    unit_like_names = {
        "pg",
        "fl",
        "cv",
        "sd",
        "ipv",
        "xt40",
        "xt-40",
        "mmhg",
        "mmol/l",
        "μmol/l",
        "umol/l",
        "mg/dl",
        "g/dl",
        "g/l",
        "%",
        "％",
    }
    if lower in unit_like_names:
        return False
    if re.fullmatch(r"\d+[a-z]{2,8}\d{0,2}", lower):
        return False
    if re.fullmatch(r"xt\d{2,4}", lower):
        return False
    if ("号" in compact and len(compact) <= 8) or compact.endswith("号"):
        return False
    blacklist = [
        "test",
        "测试",
        "参考范围",
        "参考值",
        "参考",
        "范围",
        "姓名",
        "性别",
        "年龄",
        "电话",
        "地址",
        "医生",
        "医师",
        "科室",
        "医院",
        "病区",
        "床号",
        "编号",
        "条码",
        "病历号",
        "门诊号",
        "住院号",
        "病案号",
        "报告",
        "检验",
        "检查",
        "结果",
        "结论",
        "意见",
        "建议",
        "提示",
        "诊断",
        "病史",
        "处方",
        "药品",
        "用药",
        "主诉",
        "入院",
        "出院",
        "日期",
        "时间",
    ]
    for bad in blacklist:
        if bad in text:
            return False
    allowed_keywords = [
        "血压",
        "收缩压",
        "舒张压",
        "血糖",
        "空腹血糖",
        "餐后血糖",
        "糖化血红蛋白",
        "心率",
        "脉搏",
        "体温",
        "血氧",
        "呼吸",
        "体重",
        "身高",
        "尿酸",
        "肌酐",
        "尿素氮",
        "转氨酶",
        "胆固醇",
        "甘油三酯",
        "低密度",
        "高密度",
        "总胆固醇",
        "血红蛋白",
        "白细胞",
        "红细胞",
        "血小板",
        "中性粒细胞",
        "淋巴细胞",
        "单核细胞",
        "嗜酸性粒细胞",
        "嗜碱性粒细胞",
        "网织红细胞",
        "有核红细胞",
    ]
    if any(kw in text for kw in allowed_keywords):
        return True
    allowed_abbr = {
        "hba1c",
        "hdl",
        "ldl",
        "hgb",
        "hb",
        "wbc",
        "rbc",
        "plt",
        "mch",
        "mcv",
        "mchc",
        "hct",
        "rdw",
        "rdwcv",
        "rdwsd",
        "mpv",
        "pdw",
        "pct",
        "nrbc",
        "ret",
        "ret%",
        "ret#",
        "retic",
        "retic%",
        "retic#",
        "alt",
        "ast",
        "glu",
        "tg",
        "tc",
        "spo2",
        "bmi",
        "crp",
        "tsh",
        "ft3",
        "ft4",
    }
    if lower in allowed_abbr:
        return True
    if re.fullmatch(r"[a-z]{1,2}", lower) and lower in {"na", "k", "cl", "ca", "mg"}:
        return True
    if re.fullmatch(r"[a-z]{2,6}\d{0,2}", lower) and lower not in unit_like_names:
        return True
    if re.fullmatch(r"[a-z]{2,8}[-/][a-z]{1,8}\d{0,2}", lower):
        return True
    if _looks_like_unit(unit):
        return True
    return False


def _filter_test_results(tests: Any) -> dict | None:
    if not isinstance(tests, dict):
        return None
    cleaned: dict = {}
    for k, v in tests.items():
        if not k:
            continue
        raw_key = str(k)
        unit = ""
        if isinstance(v, dict):
            unit = str(v.get("unit") or "").strip()
        if not _is_valid_test_name(str(k), unit):
            continue
        key = _canonicalize_indicator_name(raw_key)
        if not key:
            continue
        vv = v
        if isinstance(v, dict):
            vv = dict(v)
            rns = vv.get("raw_names")
            if isinstance(rns, list):
                if raw_key not in rns and len(rns) < 20:
                    rns.append(raw_key)
            elif isinstance(rns, str):
                if rns != raw_key:
                    vv["raw_names"] = [rns, raw_key]
                else:
                    vv["raw_names"] = [raw_key]
            else:
                vv["raw_names"] = [raw_key]
        if key not in cleaned:
            cleaned[key] = vv
            continue
        prev = cleaned.get(key)
        if isinstance(prev, dict) and isinstance(v, dict):
            pv = prev.get("value")
            nv = v.get("value")
            pu = str(prev.get("unit") or "").strip()
            nu = str(v.get("unit") or "").strip()
            try:
                pr = prev.get("raw_names")
                vr = vv.get("raw_names") if isinstance(vv, dict) else None
                if isinstance(pr, list) and isinstance(vr, list):
                    for rn in vr:
                        if rn not in pr and len(pr) < 20:
                            pr.append(rn)
            except Exception:
                pass
            if (pv is None or str(pv).strip() == "") and (
                nv is not None and str(nv).strip() != ""
            ):
                cleaned[key] = vv
                continue
            if not pu and nu:
                merged = dict(prev)
                merged["unit"] = nu
                if (pv is None or str(pv).strip() == "") and (
                    nv is not None and str(nv).strip() != ""
                ):
                    merged["value"] = nv
                cleaned[key] = merged
                continue
        elif isinstance(v, dict) and not isinstance(prev, dict):
            cleaned[key] = vv
    return cleaned


def _normalize_unit_text(unit: str | None) -> str:
    s = (unit or "").strip()
    if not s:
        return ""
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("μ", "μ").replace("µ", "μ")
    s = re.sub(r"\s+", "", s)
    low = s.lower()
    if low == "mmhg":
        return "mmHg"
    if low in {"mmol/l", "mmol\\l"}:
        return "mmol/L"
    if low in {"μmol/l", "umol/l"}:
        return "μmol/L"
    if low in {"mg/dl", "mg\\dl"}:
        return "mg/dL"
    if low in {"g/dl", "g\\dl"}:
        return "g/dL"
    if low in {"g/l", "g\\l"}:
        return "g/L"
    if low in {"%", "％"}:
        return "%"
    return s


def _canonicalize_indicator_name(name: str | None) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    s = raw.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    s = s.replace("_", "-").replace("－", "-").replace("—", "-")
    suffix = ""
    if "-" in s:
        left, right = s.rsplit("-", 1)
        if right in {"收缩压", "舒张压"}:
            s = left
            suffix = "-" + right
    base = s
    paren = ""
    if "(" in s and s.endswith(")"):
        i = s.rfind("(")
        if i >= 0:
            base = s[:i].strip()
            paren = s[i + 1 : -1].strip()
    base = base.strip().strip("#*")
    base = re.sub(r"^[0-9.]+", "", base)
    base = re.sub(r"^[^0-9a-zA-Z\u4e00-\u9fa5]+", "", base)
    paren_code = ""
    if paren and not _looks_like_unit(paren):
        paren_code = paren
    low = (paren_code or base).lower()
    mapping = {
        "hgb": "血红蛋白",
        "hb": "血红蛋白",
        "wbc": "白细胞",
        "rbc": "红细胞",
        "plt": "血小板",
        "mch": "平均红细胞血红蛋白量",
        "mcv": "平均红细胞体积",
        "mchc": "平均红细胞血红蛋白浓度",
        "hct": "红细胞压积",
        "rdw": "红细胞分布宽度",
        "rdw-cv": "红细胞分布宽度-CV",
        "rdwcv": "红细胞分布宽度-CV",
        "rdw-sd": "红细胞分布宽度-SD",
        "rdwsd": "红细胞分布宽度-SD",
        "glu": "血糖",
        "glucose": "血糖",
        "hba1c": "糖化血红蛋白",
        "alt": "谷丙转氨酶",
        "ast": "谷草转氨酶",
        "cr": "肌酐",
        "crea": "肌酐",
        "creatinine": "肌酐",
        "ua": "尿酸",
        "bun": "尿素氮",
        "tc": "总胆固醇",
        "tg": "甘油三酯",
        "hdl": "高密度脂蛋白",
        "ldl": "低密度脂蛋白",
        "crp": "C反应蛋白",
        "tsh": "促甲状腺激素",
        "ft3": "游离三碘甲状腺原氨酸",
        "ft4": "游离甲状腺素",
        "spo2": "血氧饱和度",
        "bp": "血压",
        "neu": "中性粒细胞",
        "neu%": "中性粒细胞百分比",
        "neut": "中性粒细胞",
        "neut%": "中性粒细胞百分比",
        "lym": "淋巴细胞",
        "lym%": "淋巴细胞百分比",
        "mono": "单核细胞",
        "mono%": "单核细胞百分比",
        "mon": "单核细胞",
        "mon%": "单核细胞百分比",
        "eos": "嗜酸性粒细胞",
        "eos%": "嗜酸性粒细胞百分比",
        "eo": "嗜酸性粒细胞",
        "eo%": "嗜酸性粒细胞百分比",
        "bas": "嗜碱性粒细胞",
        "bas%": "嗜碱性粒细胞百分比",
        "baso": "嗜碱性粒细胞",
        "baso%": "嗜碱性粒细胞百分比",
        "bas0%": "嗜碱性粒细胞百分比",
        "gran": "中性粒细胞",
        "gran%": "中性粒细胞百分比",
        "nrbc": "有核红细胞",
        "nrbc%": "有核红细胞百分比",
        "ret": "网织红细胞",
        "ret#": "网织红细胞",
        "ret%": "网织红细胞百分比",
        "retic": "网织红细胞",
        "retic#": "网织红细胞",
        "retic%": "网织红细胞百分比",
        "irf": "未成熟网织红细胞比率",
        "p-lcr": "大血小板比率",
        "plcr": "大血小板比率",
        "lcr": "大血小板比率",
        "mpv": "平均血小板体积",
        "pdw": "血小板分布宽度",
        "pct": "血小板压积",
    }
    if low in mapping:
        return mapping[low] + suffix
    if base and any(ch.isalpha() for ch in base) and base.lower() in mapping:
        return mapping[base.lower()] + suffix
    if paren_code and paren_code.lower() in mapping:
        return mapping[paren_code.lower()] + suffix
    if base:
        normalized = base
        if normalized == "血红蛋白浓度":
            normalized = "血红蛋白"
        normalized = normalized.replace("糖化血红蛋白(hba1c)", "糖化血红蛋白")
        normalized = normalized.replace("红细胞计数", "红细胞")
        normalized = normalized.replace("红细胞数", "红细胞")
        normalized = normalized.replace("白细胞计数", "白细胞")
        normalized = normalized.replace("白细胞数", "白细胞")
        normalized = normalized.replace("血小板计数", "血小板")
        normalized = normalized.replace("血小板数", "血小板")
        normalized = normalized.replace("中性粒细胞计数", "中性粒细胞")
        normalized = normalized.replace("淋巴细胞计数", "淋巴细胞")
        normalized = normalized.replace("单核细胞计数", "单核细胞")
        normalized = normalized.replace("嗜酸性粒细胞计数", "嗜酸性粒细胞")
        normalized = normalized.replace("嗜碱性粒细胞计数", "嗜碱性粒细胞")
        normalized = normalized.replace("中性粒细胞比值", "中性粒细胞百分比")
        normalized = normalized.replace("淋巴细胞比值", "淋巴细胞百分比")
        normalized = normalized.replace("单核细胞比值", "单核细胞百分比")
        normalized = normalized.replace("嗜酸性粒细胞比值", "嗜酸性粒细胞百分比")
        normalized = normalized.replace("嗜碱性粒细胞比值", "嗜碱性粒细胞百分比")
        return normalized + suffix
    return s + suffix


def _convert_value_for_indicator(
    name: str,
    value: float | None,
    unit: str,
) -> tuple[float | None, str]:
    if value is None:
        return None, unit
    u = _normalize_unit_text(unit)
    n = (name or "").strip()
    if n in {"血红蛋白", "HGB"} and u == "g/dL":
        return round(value * 10.0, 2), "g/L"
    if n in {"血糖", "空腹血糖", "餐后血糖"} and u == "mg/dL":
        return round(value / 18.0, 2), "mmol/L"
    if n in {"肌酐"} and u == "mg/dL":
        return round(value * 88.4, 1), "μmol/L"
    if n in {"尿酸"} and u == "mg/dL":
        return round(value * 59.48, 1), "μmol/L"
    return value, u


def _quick_extract_test_results(text: str) -> dict:
    results: dict = {}
    s = (text or "").strip()
    if not s:
        return results
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    patterns = [
        (
            r"([\u4e00-\u9fa5]{2,30}(?:\([^)]{1,12}\))?)\s+"
            r"([-+]?\d+(?:\.\d+)?%?)\s+"
            r"(?:\d+(?:\.\d+)?\s*(?:~|-|—)\s*\d+(?:\.\d+)?\s+)?"
            r"([A-Za-z0-9μµ/%×x*^.\-~]+(?:/[A-Za-z0-9μµ%×x*^.\-~]+)?)?"
        ),
        (
            r"([A-Za-z]{2,6}\d{0,2}%?)\)?\s+"
            r"([-+]?\d+(?:\.\d+)?%?)\s+"
            r"(?:\d+(?:\.\d+)?\s*(?:~|-|—)\s*\d+(?:\.\d+)?\s+)?"
            r"([A-Za-z0-9μµ/%×x*^.\-~]+(?:/[A-Za-z0-9μµ%×x*^.\-~]+)?)?"
        ),
    ]
    for pat in patterns:
        for match in re.findall(pat, s):
            try:
                name = str(match[0] or "").strip()
                value = str(match[1] or "").strip()
                unit = str(match[2] or "").strip() if len(match) > 2 else ""
            except Exception:
                continue
            if not _is_valid_test_name(name, unit):
                continue
            if (not unit) and value.endswith("%"):
                unit = "%"
                value = value[:-1].strip()
            results[name] = {"value": value, "unit": unit}
    return results


def _prepare_metadata_with_tests(
    content: str | None, metadata: Dict[str, Any] | None
) -> Dict[str, Any]:
    meta = metadata if isinstance(metadata, dict) else {}
    extracted = _ensure_dict_value(
        meta.get("extracted_info") or meta.get("extracted_data")
    )
    tests = extracted.get("test_results") or extracted.get("tests")
    text = (content or "").strip()
    existing_count = 0
    if isinstance(tests, dict):
        existing_count = len(tests)
    elif isinstance(tests, list):
        existing_count = len(tests)
    if text and isinstance(tests, dict) and existing_count > 0 and existing_count < 3:
        quick = _quick_extract_test_results(text)
        if quick:
            merged = dict(quick)
            merged.update(tests)
            tests = merged
    if text and isinstance(tests, dict) and existing_count > 0 and existing_count < 25 and extract_test_results:
        try:
            more = (
                extract_test_results.fn(text)
                if hasattr(extract_test_results, "fn")
                else extract_test_results(text)
            )
            if isinstance(more, dict) and more:
                merged = dict(more)
                merged.update(tests)
                tests = merged
        except Exception:
            tests = tests
    if (not tests) and text and extract_test_results:
        try:
            tests = (
                extract_test_results.fn(text)
                if hasattr(extract_test_results, "fn")
                else extract_test_results(text)
            )
        except Exception:
            tests = None
    if text and ((not tests) or (isinstance(tests, dict) and len(tests) < 3)):
        quick = _quick_extract_test_results(text)
        if quick:
            if isinstance(tests, dict) and tests:
                merged = dict(quick)
                merged.update(tests)
                tests = merged
            else:
                tests = quick
    if (not tests) and text and extract_medical_info:
        try:
            info_json = (
                extract_medical_info.fn(text)
                if hasattr(extract_medical_info, "fn")
                else extract_medical_info(text)
            )
            info_obj = (
                json.loads(info_json)
                if isinstance(info_json, str)
                else info_json
            )
            if isinstance(info_obj, dict):
                tests = info_obj.get("test_results") or tests
        except Exception:
            tests = tests
    filtered = _filter_test_results(tests)
    if filtered is not None:
        if filtered:
            extracted["test_results"] = filtered
        else:
            extracted.pop("test_results", None)
        extracted.pop("tests", None)
    if extracted:
        meta["extracted_info"] = extracted
        meta.pop("extracted_data", None)
    return meta


def _append_indicator_point(
    store: dict,
    name: str,
    unit: str | None,
    date_val: Any,
    value_raw: Any,
    source: str,
    record_id: str | None,
):
    normalized_name = _canonicalize_indicator_name(name)
    if not normalized_name:
        return
    item = store.get(normalized_name)
    if not item:
        item = {"name": normalized_name, "unit": "", "points": [], "raw_names": []}
        store[normalized_name] = item
    try:
        raw = str(name or "").strip()
        if raw:
            raw_names = item.get("raw_names")
            if isinstance(raw_names, list):
                if raw not in raw_names and len(raw_names) < 30:
                    raw_names.append(raw)
            else:
                item["raw_names"] = [raw]
    except Exception:
        pass
    normalized_unit = _normalize_unit_text(unit)
    date_str = _format_date_value(date_val)
    value_text = "" if value_raw is None else str(value_raw).strip()
    value_num = (
        _coerce_float_value(value_raw)
        if value_raw is not None and "/" not in value_text
        else None
    )
    value_num, normalized_unit = _convert_value_for_indicator(
        normalized_name, value_num, normalized_unit
    )
    if normalized_unit and not item.get("unit"):
        item["unit"] = normalized_unit
    item["points"].append(
        {
            "date": date_str,
            "value": value_num,
            "value_text": value_text,
            "unit": normalized_unit,
            "source": source,
            "record_id": record_id,
        }
    )


def _collect_test_points(
    store: dict,
    tests: Any,
    date_val: Any,
    source: str,
    record_id: str | None,
):
    if isinstance(tests, dict):
        for k, v in tests.items():
            if not k:
                continue
            key_text = str(k).strip().lower()
            if key_text in {"test", "test_report"}:
                continue
            if isinstance(v, dict):
                val = v.get("value")
                unit = v.get("unit") or ""
                name_val = str(k).strip()
                try:
                    rns = v.get("raw_names")
                    if isinstance(rns, list) and rns:
                        ascii_rns = [
                            rn
                            for rn in rns
                            if any(ord(ch) < 128 for ch in str(rn))
                        ]
                        name_val = str(
                            ascii_rns[0] if ascii_rns else rns[0]
                        ).strip()
                except Exception:
                    name_val = str(k).strip()
                bp = _split_bp_value(val)
                if bp:
                    _append_indicator_point(
                        store,
                        f"{name_val}-收缩压",
                        unit or "mmHg",
                        date_val,
                        bp[0],
                        source,
                        record_id,
                    )
                    _append_indicator_point(
                        store,
                        f"{name_val}-舒张压",
                        unit or "mmHg",
                        date_val,
                        bp[1],
                        source,
                        record_id,
                    )
                else:
                    _append_indicator_point(
                        store,
                        name_val,
                        unit,
                        date_val,
                        val,
                        source,
                        record_id,
                    )
            else:
                bp = _split_bp_value(v)
                if bp:
                    _append_indicator_point(
                        store,
                        f"{k}-收缩压",
                        "mmHg",
                        date_val,
                        bp[0],
                        source,
                        record_id,
                    )
                    _append_indicator_point(
                        store,
                        f"{k}-舒张压",
                        "mmHg",
                        date_val,
                        bp[1],
                        source,
                        record_id,
                    )
                else:
                    _append_indicator_point(
                        store,
                        str(k).strip(),
                        "",
                        date_val,
                        v,
                        source,
                        record_id,
                    )
        return
    items = _ensure_list_value(tests)
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("test_name") or "").strip()
        if name and name.lower() in {"test", "test_report"}:
            continue
        val = item.get("value")
        unit = str(item.get("unit") or "").strip()
        if name and not _is_valid_test_name(name, unit):
            continue
        dt = item.get("date") or date_val
        bp = _split_bp_value(val)
        if bp and name:
            _append_indicator_point(
                store,
                f"{name}-收缩压",
                unit or "mmHg",
                dt,
                bp[0],
                source,
                record_id,
            )
            _append_indicator_point(
                store,
                f"{name}-舒张压",
                unit or "mmHg",
                dt,
                bp[1],
                source,
                record_id,
            )
        else:
            _append_indicator_point(
                store, name, unit, dt, val, source, record_id
            )


def _finalize_indicator_items(store: dict, include_points: bool) -> list:
    indicators = []
    for item in store.values():
        points = item.get("points") or []
        points = [p for p in points if p.get("date")]
        points.sort(key=lambda x: x.get("date") or "")
        item["count"] = len(points)
        item["points"] = points[-200:]
        nums = [
            p.get("value")
            for p in points
            if isinstance(p.get("value"), (int, float))
        ]
        if nums:
            nums_sorted = sorted(float(x) for x in nums)
            mid = len(nums_sorted) // 2
            median = (
                nums_sorted[mid]
                if len(nums_sorted) % 2 == 1
                else (nums_sorted[mid - 1] + nums_sorted[mid]) / 2
            )
            item["stats"] = {
                "min": round(min(nums_sorted), 2),
                "max": round(max(nums_sorted), 2),
                "avg": round(sum(nums) / len(nums), 2),
                "median": round(median, 2),
            }
        else:
            item["stats"] = None
        item["latest"] = points[-1] if points else None
        if not include_points:
            item.pop("points", None)
        indicators.append(item)
    indicators.sort(
        key=lambda x: (x.get("latest") or {}).get("date") or "", reverse=True
    )
    return indicators


async def _maybe_llm_audit_trend_indicators(indicators: list[dict]) -> None:
    try:
        def _parse_json_object(text: str) -> dict | None:
            try:
                s = (text or "").strip()
                if not s:
                    return None
                if "```" in s:
                    start = s.find("```")
                    end = s.rfind("```")
                    if start != -1 and end != -1 and end > start:
                        inner = s[start + 3 : end]
                        nl = inner.find("\n")
                        if nl != -1:
                            inner = inner[nl + 1 :]
                        s = inner.strip()
                if s.startswith("{") and s.endswith("}"):
                    try:
                        obj = json.loads(s)
                        return obj if isinstance(obj, dict) else None
                    except Exception:
                        pass
                i = s.find("{")
                j = s.rfind("}")
                if i != -1 and j != -1 and j > i:
                    cand = s[i : j + 1].strip()
                    cand = re.sub(r",\s*([}\]])", r"\1", cand)
                    obj = json.loads(cand)
                    return obj if isinstance(obj, dict) else None
            except Exception:
                return None
            return None

        raw_flag = os.getenv("USE_LLM_INDICATOR_AUDIT")
        if raw_flag is None:
            use_llm = False
        else:
            use_llm = str(raw_flag).lower() in ("1", "true", "yes")
        if not use_llm:
            return
        try:
            from openai import AsyncOpenAI
        except Exception:
            return
        cache = globals().get("_INDICATOR_AUDIT_CACHE")
        if not isinstance(cache, dict):
            cache = {}
            globals()["_INDICATOR_AUDIT_CACHE"] = cache
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            return
        base_url = (
            os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.deepseek.com"
        )
        try:
            bu = str(base_url or "").strip().rstrip("/")
            if bu and (not bu.endswith("/v1")):
                base_url = bu + "/v1"
        except Exception:
            pass
        model = (
            os.getenv("LLM_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "deepseek-chat"
        )
        to_audit: list[dict] = []
        id_to_name: dict[str, str] = {}
        name_to_id: dict[str, str] = {}
        for item in indicators:
            if not isinstance(item, dict):
                continue
            raw_names = item.get("raw_names")
            if not isinstance(raw_names, list) or not raw_names:
                continue
            nm = str(item.get("name") or "").strip()
            if not nm:
                continue
            audit_id = f"i{len(to_audit)}"
            id_to_name[audit_id] = nm
            name_to_id[nm] = audit_id
            to_audit.append(
                {
                    "id": audit_id,
                    "name": nm,
                    "unit": str(item.get("unit") or ""),
                    "raw_names": [str(x) for x in raw_names[:10]],
                }
            )
            if len(to_audit) >= 40:
                break
        if not to_audit:
            return
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        sys_prompt = (
            "你是医学检验指标名称审校助手，只输出JSON。"
            "任务：审查系统给出的中文指标名是否与原始缩写/原名一致。"
            "要求：仅依据raw_names和常见检验缩写含义判断；不确定时is_correct=false且confidence<=0.5；禁止编造；reason不超过30字；不要markdown。"
            "输出格式：{\"items\":[{\"id\":\"与输入一致\",\"is_correct\":true/false,\"suggested_name\":\"建议中文名或空\",\"confidence\":0到1,\"reason\":\"简短原因\"}]}"
        )
        audit_map: dict[str, dict] = {}
        chunk_size = 10
        for start in range(0, len(to_audit), chunk_size):
            chunk = to_audit[start : start + chunk_size]
            if not chunk:
                continue
            payload = {"items": chunk}
            user_prompt = json.dumps(payload, ensure_ascii=False)
            try:
                import hashlib

                cache_key = hashlib.sha1(
                    user_prompt.encode("utf-8", errors="ignore")
                ).hexdigest()
            except Exception:
                cache_key = None
            parsed = cache.get(cache_key) if cache_key else None
            try:
                if parsed is None:
                    req_kwargs = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 2000,
                    }
                    try:
                        resp = await client.chat.completions.create(
                            **req_kwargs, response_format={"type": "json_object"}
                        )
                    except Exception:
                        resp = await client.chat.completions.create(**req_kwargs)
                    text = (resp.choices[0].message.content or "").strip()
                    parsed = _parse_json_object(text)
                    if cache_key and isinstance(parsed, dict):
                        cache[cache_key] = parsed
            except Exception:
                continue
            items = parsed.get("items") if isinstance(parsed, dict) else None
            if not isinstance(items, list) or not items:
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                _id = str(it.get("id") or "").strip()
                if not _id:
                    continue
                audit_map[_id] = it
        if not audit_map:
            return
        for item in indicators:
            if not isinstance(item, dict):
                continue
            nm = str(item.get("name") or "").strip()
            if not nm:
                continue
            audit_id = name_to_id.get(nm)
            audit = audit_map.get(audit_id) if audit_id else None
            if not audit:
                continue
            item["audit"] = audit
            is_correct = bool(audit.get("is_correct"))
            conf = audit.get("confidence")
            suggested = str(audit.get("suggested_name") or "").strip()
            if not is_correct and isinstance(conf, (int, float)) and conf >= 0.75:
                if suggested:
                    item["name"] = _canonicalize_indicator_name(suggested)
                else:
                    item["name"] = nm + "（待核对）"
    except Exception:
        return


def _normalize_ocr_text(raw: str | None) -> str:
    """规范化 OCR 原始输出为纯文本。
    - 解析可能的 JSON，优先抽取 content/Content；
    - 兼容 data/Data 下的 lines/prism_wordsInfo 数组；
    - 兜底返回去除空白的原文。
    """
    try:
        s = raw or ""
        if not isinstance(s, str):
            s = str(s)
        s_strip = s.strip()
        if s_strip.startswith("{") or s_strip.startswith("["):
            try:
                obj = json.loads(s_strip)
            except Exception:
                return s_strip
            if isinstance(obj, dict):
                # 顶层 content/Content
                top_content = None
                for key in ("content", "Content"):
                    v = obj.get(key)
                    if isinstance(v, str):
                        top_content = v
                        if v.strip():
                            return v.strip()
                # data/Data 里取内容或行
                data = obj.get("data") or obj.get("Data")
                if isinstance(data, dict):
                    v = data.get("content") or data.get("Content")
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                    lines = data.get("lines") or data.get("prism_wordsInfo")
                    if isinstance(lines, list) and lines:
                        parts = []
                        for it in lines:
                            if isinstance(it, dict):
                                parts.append(
                                    str(
                                        it.get("text") or it.get("word") or ""
                                    ).strip()
                                )
                            elif isinstance(it, str):
                                parts.append(it.strip())
                        text = "\n".join([p for p in parts if p])
                        if text.strip():
                            return text.strip()
                    if isinstance(v, str) and (not v.strip()) and (not lines):
                        return ""
                elif isinstance(data, str) and data.strip():
                    return data.strip()
                if isinstance(top_content, str) and (not top_content.strip()):
                    if any(
                        k in obj
                        for k in (
                            "Height",
                            "Width",
                            "SubImages",
                            "SubImageCount",
                            "Angle",
                        )
                    ):
                        return ""
                # 兜底：拼接所有字符串值
                try:
                    vals = []
                    for _, v in obj.items():
                        if isinstance(v, str):
                            vals.append(v.strip())
                    if vals:
                        text = "\n".join([v for v in vals if v])
                        if text.strip():
                            return text.strip()
                except Exception:
                    pass
            if isinstance(obj, list) and obj:
                parts = []
                for it in obj:
                    if isinstance(it, dict):
                        parts.append(
                            str(it.get("text") or it.get("word") or "").strip()
                        )
                    elif isinstance(it, str):
                        parts.append(it.strip())
                text = "\n".join([p for p in parts if p])
                if text.strip():
                    return text.strip()
        return s_strip.replace("\r", " ").strip()
    except Exception:
        return (raw or "").strip()


def _is_ocr_placeholder_text(text: str | None) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    low = s.lower()
    if low == "test":
        return True
    if s in ("OCR识别结果", "识别结果"):
        return True
    ocr_err_prefixes = (
        "阿里云OCR(2021)调用失败",
        "阿里云OCR(2021)配置缺失",
        "阿里云OCR(2021) SDK未安装",
        "阿里云OCR调用失败",
        "阿里云OCR配置缺失",
        "阿里云OCR SDK未安装",
        "图片Base64数据不合法",
        "本地OCR兜底不可用",
        "本地OCR兜底失败",
        "本地OCR兜底异常",
        "OCR识别失败",
        "不支持的OCR服务提供商",
    )
    return s.startswith(ocr_err_prefixes)


def _parse_date_str(s: str | None) -> date | None:
    if not isinstance(s, str):
        return None
    raw = s.strip()
    if not raw:
        return None
    try:
        try:
            from dateutil import parser as _dt_parser  # type: ignore

            dt = _dt_parser.parse(raw, fuzzy=True)
            return dt.date()
        except Exception:
            pass

        m = re.search(r"(\d{4})[./\-年](\d{1,2})[./\-月](\d{1,2})", raw)
        if m:
            y = int(m.group(1))
            mo = int(m.group(2))
            d = int(m.group(3))
            return date(y, mo, d)

        m = re.search(r"(\d{4})[./\-](\d{1,2})", raw)
        if m:
            y = int(m.group(1))
            mo = int(m.group(2))
            return date(y, mo, 1)
    except Exception:
        return None
    return None


def _extract_visit_summary_fields(ocr_text: str) -> dict[str, Any]:
    text = (ocr_text or "").strip()
    if not text:
        return {}

    def _pick(patterns: list[str], max_len: int) -> str | None:
        for pat in patterns:
            try:
                m = re.search(pat, text, flags=re.IGNORECASE)
            except Exception:
                continue
            if not m:
                continue
            v = (m.group(1) or "").strip()
            if not v:
                continue
            v = re.sub(r"\s+", " ", v).strip()
            if not v:
                continue
            if len(v) > max_len:
                v = v[:max_len].rstrip()
            return v
        return None

    extracted: dict[str, Any] = {}

    dt = _parse_date_str(text)
    if dt:
        extracted["visit_date"] = dt

    extracted["hospital"] = _pick(
        [
            r"(?:医院|医疗机构名称|医疗机构|机构名称)\s*[:：]?\s*([^\n；;。]{2,80})",
        ],
        80,
    )
    extracted["department"] = _pick(
        [
            r"(?:科室|就诊科室|门诊科室|就诊门诊)\s*[:：]?\s*([^\n；;。]{2,40})",
        ],
        40,
    )
    extracted["doctor"] = _pick(
        [
            r"(?:医生|医师|接诊医生|主治医师|责任医师)\s*[:：]?\s*([^\n；;。]{2,30})",
        ],
        30,
    )
    extracted["chief_complaint"] = _pick(
        [
            r"(?:主诉)\s*[:：]?\s*([^\n]{2,120})",
        ],
        120,
    )
    extracted["symptoms"] = _pick(
        [
            r"(?:现病史|症状|病史|不适)\s*[:：]?\s*([^\n]{2,200})",
        ],
        200,
    )
    extracted["examination"] = _pick(
        [
            r"(?:体格检查|辅助检查|检查)\s*[:：]?\s*([^\n]{2,240})",
        ],
        240,
    )
    extracted["diagnosis"] = _pick(
        [
            r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,120})",
        ],
        120,
    )
    extracted["treatment"] = _pick(
        [
            r"(?:治疗|处置|处理|治疗方案)\s*[:：]?\s*([^\n]{2,240})",
        ],
        240,
    )
    extracted["prescription"] = _pick(
        [
            r"(?:处方|用药|药物)\s*[:：]?\s*([^\n]{2,400})",
        ],
        400,
    )
    extracted["follow_up"] = _pick(
        [
            r"(?:复查|随访|复诊|回访|医嘱)\s*[:：]?\s*([^\n]{2,240})",
        ],
        240,
    )
    extracted["notes"] = None

    for k in list(extracted.keys()):
        if extracted.get(k) is None:
            extracted.pop(k, None)
    return extracted


def _generate_ai_summary(ocr_text: str, extracted: dict | None) -> str:
    try:
        text_clean = (ocr_text or "").strip().replace("\n", " ")
        parts = []
        if isinstance(extracted, dict):
            doc_type = extracted.get("document_type") or ""
            date = extracted.get("date") or extracted.get("record_date") or ""
            diagnosis = extracted.get("diagnosis") or ""
            result = (
                extracted.get("result") or extracted.get("conclusion") or ""
            )
            prescription = (
                extracted.get("prescription")
                or extracted.get("medications")
                or ""
            )
            tests = extracted.get("tests") or ""
            key = (
                extracted.get("key_findings") or extracted.get("summary") or ""
            )
            if doc_type:
                parts.append(f"类型：{doc_type}")
            if date:
                parts.append(f"日期：{date}")
            if key:
                parts.append(f"要点：{str(key)}")
            if diagnosis:
                parts.append(f"诊断：{str(diagnosis)}")
            if result:
                parts.append(f"结果：{str(result)}")
            if prescription:
                parts.append(f"用药：{str(prescription)}")
            if tests:
                parts.append(f"检查：{str(tests)}")

        # 优先使用OCR正文；若OCR文本足够（>=50字），使用全文作为摘要
        if len(text_clean) >= 50:
            summary = text_clean
        else:
            # 若仅有少量元信息，尝试组合元信息 + OCR片段
            info = "；".join([p for p in parts if p])
            if info and text_clean:
                summary = info + "；" + text_clean
            else:
                summary = info or text_clean
            summary = summary

        return summary
    except Exception:
        t = ocr_text or ""
        t = t.strip().replace("\n", " ")
        return t


def _build_structured_summary(extracted: dict | None) -> str | None:
    if not isinstance(extracted, dict):
        return None
    parts: list[str] = []
    doc_type = str(extracted.get("document_type") or "").strip()
    if doc_type:
        parts.append(f"类型：{doc_type}")
    date_val = extracted.get("date") or extracted.get("record_date")
    date_str = str(date_val or "").strip()
    if date_str:
        parts.append(f"日期：{date_str}")
    diagnosis = extracted.get("diagnosis")
    if isinstance(diagnosis, list):
        diag_list = [str(x).strip() for x in diagnosis if str(x).strip()]
        if diag_list:
            parts.append(f"诊断：{'；'.join(diag_list[:5])}")
    elif isinstance(diagnosis, str) and diagnosis.strip():
        parts.append(f"诊断：{diagnosis.strip()}")

    medications = extracted.get("medications")
    if isinstance(medications, list) and medications:
        med_items: list[str] = []
        for m in medications[:5]:
            if isinstance(m, str) and m.strip():
                med_items.append(m.strip())
            elif isinstance(m, dict):
                name = str(m.get("name") or "").strip()
                dosage = str(m.get("dosage") or "").strip()
                frequency = str(m.get("frequency") or "").strip()
                duration = str(m.get("duration") or "").strip()
                usage = str(m.get("usage_instruction") or "").strip()
                segs = [name, dosage, frequency, duration, usage]
                text = " ".join([s for s in segs if s])
                if text:
                    med_items.append(text)
        if med_items:
            parts.append(f"用药：{'、'.join(med_items)}")

    test_results = extracted.get("test_results")
    if isinstance(test_results, dict) and test_results:
        test_items: list[str] = []
        for k, v in list(test_results.items())[:5]:
            if not k:
                continue
            if isinstance(v, dict):
                val = str(v.get("value") or "").strip()
                unit = str(v.get("unit") or "").strip()
                segs = [str(k).strip(), val, unit]
                text = " ".join([s for s in segs if s])
                if text:
                    test_items.append(text)
            else:
                text = f"{str(k).strip()} {str(v).strip()}".strip()
                if text:
                    test_items.append(text)
        if test_items:
            parts.append(f"检查：{'、'.join(test_items)}")

    doctor_info = extracted.get("doctor_info")
    if isinstance(doctor_info, dict):
        hospital = str(doctor_info.get("hospital") or "").strip()
        doctor = str(doctor_info.get("doctor") or "").strip()
        dept = str(doctor_info.get("department") or "").strip()
        doc_parts = [p for p in [hospital, dept, doctor] if p]
        if doc_parts:
            parts.append(f"就诊：{'、'.join(doc_parts)}")

    advice = extracted.get("medical_advice")
    if isinstance(advice, list):
        adv_list = [str(x).strip() for x in advice if str(x).strip()]
        if adv_list:
            parts.append(f"医嘱：{'；'.join(adv_list[:5])}")
    elif isinstance(advice, str) and advice.strip():
        parts.append(f"医嘱：{advice.strip()}")

    if not parts:
        return None
    return "；".join(parts)


def _try_generate_visit_summary_with_agent(
    ocr_text: str,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        text = (ocr_text or "").strip()
        if not text:
            return None, None, None
        try:
            from VisitSummaryGenerator.mcpserver.document_tool import (
                generate_visit_summary,
            )
        except Exception:
            return None, None, None

        lines = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]

        diag_cert_lines: list[str] = []
        visit_lines: list[str] = []
        rx_lines: list[str] = []
        lab_lines: list[str] = []
        imaging_lines: list[str] = []

        for ln in lines:
            low = ln.lower()
            if any(
                k in ln
                for k in (
                    "诊断证明",
                    "疾病证明",
                    "诊断书",
                    "疾病诊断证明",
                    "姓名",
                    "性别",
                    "年龄",
                    "身份证",
                )
            ):
                diag_cert_lines.append(ln)
            if (
                ln.startswith(("诊断", "临床诊断", "疾病诊断"))
                and "诊断证明" not in ln
                and "诊断书" not in ln
            ):
                diag_cert_lines.append(ln)

            if any(
                k in ln
                for k in (
                    "主诉",
                    "现病史",
                    "既往史",
                    "体格检查",
                    "病史",
                    "处理",
                    "门诊",
                    "入院",
                    "出院",
                )
            ):
                visit_lines.append(ln)

            is_dose = bool(
                re.search(
                    r"\d+(?:\.\d+)?\s*(?:mg|g|ml|iu|μg|ug|单位)",
                    ln,
                    flags=re.IGNORECASE,
                )
            )
            is_count_dose = bool(
                re.search(r"\d+\s*(?:片|粒|丸|袋|支|贴|滴|喷)", ln)
            )
            is_lab_unit = any(
                u in low
                for u in (
                    "mmol",
                    "μmol",
                    "umol",
                    "×10",
                    "10^",
                    "/l",
                    "mg/l",
                    "g/l",
                )
            )
            is_lab_kw = any(
                k in ln
                for k in ("检验", "化验", "血常规", "生化", "参考范围", "结果")
            )
            is_rx_kw = any(
                k in ln
                for k in (
                    "Rx:",
                    "处方",
                    "用药",
                    "医嘱",
                    "用法",
                    "用量",
                    "用法用量",
                    "口服",
                    "静滴",
                    "肌注",
                    "皮下",
                    "iv",
                    "im",
                    "po",
                    "每次",
                    "每日",
                    "qd",
                    "bid",
                    "tid",
                    "q12h",
                )
            )
            is_med_form = any(
                k in ln
                for k in (
                    "胶囊",
                    "颗粒",
                    "滴丸",
                    "口服液",
                    "注射液",
                    "软膏",
                    "乳膏",
                    "喷雾",
                    "滴眼液",
                    "贴",
                )
            )

            if is_lab_kw or is_lab_unit:
                if is_dose and not is_lab_unit:
                    pass
                else:
                    lab_lines.append(ln)
            if (
                is_rx_kw
                or is_med_form
                or is_count_dose
                or (is_dose and not is_lab_unit)
            ):
                if is_lab_unit or is_lab_kw:
                    pass
                else:
                    rx_lines.append(ln)

            if any(
                k in ln for k in ("影像", "CT", "MRI", "超声", "X线", "心电图")
            ):
                imaging_lines.append(ln)

        documents: list[dict[str, Any]] = []
        seen_contents: set[str] = set()

        def add_doc(doc_type: str, doc_lines: list[str]):
            content = "\n".join([x for x in doc_lines if x]).strip()
            if len(content) < 8:
                return
            if content in seen_contents:
                return
            seen_contents.add(content)
            documents.append({"type": doc_type, "content": content})

        add_doc("诊断证明", diag_cert_lines)
        add_doc("门诊记录", visit_lines)
        add_doc("处方单", rx_lines)
        add_doc("检验报告", lab_lines)
        add_doc("影像报告", imaging_lines)

        if not documents:
            documents = [{"type": "auto", "content": text}]

        res = generate_visit_summary(documents, summary_type="comprehensive")
        if not isinstance(res, dict) or not res.get("success"):
            return None, None, None
        data = res.get("data") or {}
        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, dict):
            return None, None, None

        diagnosis_list: list[str] = []
        diag = (
            content.get("diagnosis_treatment", {}).get("diagnosis")
            if isinstance(content.get("diagnosis_treatment"), dict)
            else None
        )
        if isinstance(diag, list):
            diagnosis_list = [str(x).strip() for x in diag if str(x).strip()]
        elif isinstance(diag, str) and diag.strip():
            diagnosis_list = [diag.strip()]

        meds = (
            content.get("medications")
            if isinstance(content.get("medications"), list)
            else []
        )
        med_lines: list[str] = []
        med_names: list[str] = []
        for m in meds:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or "").strip()
            dosage = str(m.get("dosage") or "").strip()
            usage = str(m.get("usage") or "").strip()
            duration = str(m.get("duration") or "").strip()
            if name:
                med_names.append(name)
                s = name
                if dosage:
                    s = f"{s} {dosage}"
                if duration:
                    s = f"{s} {duration}"
                if usage and usage != s:
                    s = f"{s}；{usage}"
                med_lines.append(s)

        test_results = (
            content.get("test_results")
            if isinstance(content.get("test_results"), list)
            else []
        )
        test_lines: list[str] = []
        for t in test_results:
            if not isinstance(t, dict):
                continue
            tn = str(t.get("test_name") or "").strip()
            val = str(t.get("value") or "").strip()
            unit = str(t.get("unit") or "").strip()
            status = str(t.get("status") or "").strip()
            if tn and val:
                seg = f"{tn} {val}{unit}"
                if status:
                    seg = f"{seg}（{status}）"
                test_lines.append(seg)

        lines: list[str] = []
        if diagnosis_list:
            lines.append("诊断：" + "；".join(diagnosis_list))
        if med_lines:
            lines.append("用药：\n" + "\n".join(med_lines[:20]))
        if test_lines:
            lines.append("检查：\n" + "\n".join(test_lines[:30]))
        summary_text = (
            "\n\n".join([ln for ln in lines if ln.strip()]).strip() or None
        )

        fields: dict[str, Any] = {
            "diagnosis": "；".join(diagnosis_list) if diagnosis_list else None,
            "medications": meds,
            "medication_names": list(
                dict.fromkeys([n for n in med_names if n])
            ),
        }
        return summary_text, fields, data
    except Exception:
        return None, None, None


def _try_generate_visit_summary_with_agent_multi(
    ocr_texts: list[str],
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        texts = [(t or "").strip() for t in (ocr_texts or [])]
        texts = [t for t in texts if t]
        if not texts:
            return None, None, None
        try:
            from VisitSummaryGenerator.mcpserver.document_tool import (
                generate_visit_summary,
            )
        except Exception:
            return None, None, None

        documents: list[dict[str, Any]] = []
        seen_contents: set[str] = set()
        for t in texts:
            if len(t) < 8:
                continue
            if t in seen_contents:
                continue
            seen_contents.add(t)
            documents.append({"type": "auto", "content": t})
        if not documents:
            return None, None, None

        res = generate_visit_summary(documents, summary_type="comprehensive")
        if not isinstance(res, dict) or not res.get("success"):
            return None, None, None
        data = res.get("data") or {}
        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, dict):
            return None, None, None

        diagnosis_list: list[str] = []
        diag = (
            content.get("diagnosis_treatment", {}).get("diagnosis")
            if isinstance(content.get("diagnosis_treatment"), dict)
            else None
        )
        if isinstance(diag, list):
            diagnosis_list = [str(x).strip() for x in diag if str(x).strip()]
        elif isinstance(diag, str) and diag.strip():
            diagnosis_list = [diag.strip()]

        meds = (
            content.get("medications")
            if isinstance(content.get("medications"), list)
            else []
        )
        med_lines: list[str] = []
        med_names: list[str] = []
        for m in meds:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or "").strip()
            dosage = str(m.get("dosage") or "").strip()
            usage = str(m.get("usage") or "").strip()
            duration = str(m.get("duration") or "").strip()
            if name:
                med_names.append(name)
                s = name
                if dosage:
                    s = f"{s} {dosage}"
                if duration:
                    s = f"{s} {duration}"
                if usage and usage != s:
                    s = f"{s}；{usage}"
                med_lines.append(s)

        test_results = (
            content.get("test_results")
            if isinstance(content.get("test_results"), list)
            else []
        )
        test_lines: list[str] = []
        for t in test_results:
            if not isinstance(t, dict):
                continue
            tn = str(t.get("test_name") or "").strip()
            val = str(t.get("value") or "").strip()
            unit = str(t.get("unit") or "").strip()
            status = str(t.get("status") or "").strip()
            if tn and val:
                seg = f"{tn} {val}{unit}"
                if status:
                    seg = f"{seg}（{status}）"
                test_lines.append(seg)

        lines: list[str] = []
        if diagnosis_list:
            lines.append("诊断：" + "；".join(diagnosis_list))
        if med_lines:
            lines.append("用药：\n" + "\n".join(med_lines[:20]))
        if test_lines:
            lines.append("检查：\n" + "\n".join(test_lines[:30]))
        summary_text = (
            "\n\n".join([ln for ln in lines if ln.strip()]).strip() or None
        )

        fields: dict[str, Any] = {
            "diagnosis": "；".join(diagnosis_list) if diagnosis_list else None,
            "medications": meds,
            "medication_names": list(
                dict.fromkeys([n for n in med_names if n])
            ),
        }
        return summary_text, fields, data
    except Exception:
        return None, None, None


def _sanitize_json_value(v: Any) -> Any:
    if isinstance(v, str) and "\x00" in v:
        return v.replace("\x00", "")
    return v


def _sanitize_text_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        return v.replace("\x00", "")
    return v


def _ensure_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except Exception:
        try:
            return {"raw": str(obj)}
        except Exception:
            return None


async def _maybe_llm_summary(
    ocr_text: str, extracted: dict | None
) -> str | None:
    try:
        raw_flag = os.getenv("USE_LLM_SUMMARY")
        if raw_flag is None:
            use_llm = True
        else:
            use_llm = str(raw_flag).lower() in ("1", "true", "yes")
        logger.info(f"LLM_SUMMARY_FLAG={use_llm}")
        if not use_llm:
            logger.info("LLM 摘要未开启，跳过")
            return None
        try:
            from openai import AsyncOpenAI

            logger.info("OpenAI 客户端导入成功")
        except Exception as e:
            logger.warning(f"OpenAI 客户端导入失败: {e}")
            return None

        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            logger.warning("LLM 密钥缺失，跳过")
            return None
        base_url = (
            os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.deepseek.com"
        )
        model = (
            os.getenv("LLM_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "deepseek-chat"
        )
        logger.info(f"LLM 配置 base_url={base_url}, model={model}")

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        text_clean = (ocr_text or "").strip()
        extracted_str = ""
        if isinstance(extracted, dict) and extracted:
            try:
                import json

                extracted_str = json.dumps(extracted, ensure_ascii=False)
            except Exception:
                extracted_str = str(extracted)

        sys_prompt = (
            "你是医疗文档摘要助手。仅依据输入文本生成中文摘要，禁止编造、推断或引用外部知识。"
            "必须完全从提供的内容中摘取信息，不得修改数值、单位或术语。缺失的字段不要补充；不存在的部分不要输出。"
            "尽量完整列出关键检查项目，避免截断。面向医生。"
        )
        has_rx = False
        try:
            if isinstance(extracted, dict):
                for k in (
                    "prescription",
                    "medication",
                    "medications",
                    "用药",
                    "处方",
                ):
                    v = extracted.get(k)
                    if v:
                        has_rx = True
                        break
            if not has_rx and text_clean:
                rx_keywords = ["处方", "用药", "医嘱", "药品", "药方"]
                has_rx = any(kw in text_clean for kw in rx_keywords)
        except Exception:
            has_rx = False
        sections = ["类型", "日期", "要点", "诊断", "检查"]
        if has_rx:
            sections.append("用药")
        sections_str = "、".join(sections)
        user_prompt = (
            f"【结构化信息】\n{extracted_str}\n\n"
            f"【OCR全文】\n{text_clean}\n\n"
            f"任务：概述真实信息，按‘{sections_str}’组织。"
            "要求：只使用上述文本中的内容；禁止添加任何未出现的信息；禁止建议、风险推断或延伸结论；"
            "不要输出‘无用药’或类似占位内容。"
        )

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1200,
            )
            text = resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM 摘要请求失败: {e}")
            return None

        text = (text or "").strip().replace("\n", " ")
        if not text:
            return None
        # 不做硬截断，保留完整摘要，由前端决定展示长度
        logger.info(f"LLM 摘要生成成功，长度={len(text)}")
        return text
    except Exception as e:
        logger.error(f"LLM 摘要流程异常: {e}")
        return None


def _extract_json_payload(text: str) -> dict | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s).strip()
        s = re.sub(r"\s*```$", "", s).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    raw = s[start : end + 1].strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _build_display_fields_fallback(extracted: dict | None) -> dict[str, Any]:
    if not isinstance(extracted, dict):
        extracted = {}

    diagnosis_val = extracted.get("diagnosis") or extracted.get("diagnoses")
    diagnosis: list[str] = []
    if isinstance(diagnosis_val, str):
        dx = diagnosis_val.strip()
        if dx:
            diagnosis = [x.strip() for x in re.split(r"[；;，,\n]+", dx) if x.strip()]
    elif isinstance(diagnosis_val, list):
        diagnosis = [str(x).strip() for x in diagnosis_val if str(x).strip()]

    medications: list[str] = []
    meds_val = extracted.get("medications") or extracted.get("medication_names")
    if isinstance(meds_val, list):
        for m in meds_val:
            if isinstance(m, str):
                name = m.strip()
                if name:
                    medications.append(name)
            elif isinstance(m, dict):
                name = str(m.get("name") or m.get("drug") or "").strip()
                if name:
                    medications.append(name)
    elif isinstance(meds_val, str):
        medications = [
            x.strip() for x in re.split(r"[；;，,\n]+", meds_val) if x.strip()
        ]

    key_tests: list[dict[str, Any]] = []
    tests_val = extracted.get("test_results") or extracted.get("tests")
    if isinstance(tests_val, list):
        for t in tests_val[:30]:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name") or t.get("test_name") or "").strip()
            value = str(t.get("value") or t.get("result") or "").strip()
            unit = str(t.get("unit") or "").strip()
            if name and (value or unit):
                key_tests.append({"name": name, "value": value, "unit": unit})
    elif isinstance(tests_val, dict):
        for k, v in list(tests_val.items())[:30]:
            name = str(k or "").strip()
            if not name:
                continue
            if isinstance(v, dict):
                value = str(v.get("value") or "").strip()
                unit = str(v.get("unit") or "").strip()
            else:
                value = str(v or "").strip()
                unit = ""
            if value or unit:
                key_tests.append({"name": name, "value": value, "unit": unit})

    date_val = extracted.get("date") or extracted.get("visit_date")
    date_text = str(date_val or "").strip()
    if hasattr(date_val, "isoformat"):
        try:
            date_text = date_val.isoformat()
        except Exception:
            date_text = str(date_val or "").strip()

    return {
        "doc_type": str(extracted.get("document_type") or "").strip(),
        "date": date_text,
        "hospital": str(extracted.get("hospital") or "").strip(),
        "department": str(extracted.get("department") or "").strip(),
        "doctor": str(extracted.get("doctor") or "").strip(),
        "diagnosis": diagnosis[:4],
        "medications": list(dict.fromkeys([x for x in medications if x]))[:8],
        "key_tests": key_tests[:12],
        "key_points": [],
        "advice": [],
        "follow_up": [],
    }


def _normalize_display_fields(obj: dict | None) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None

    def norm_str(v: Any) -> str:
        return str(v or "").strip()

    def norm_str_list(v: Any, max_items: int) -> list[str]:
        if isinstance(v, str):
            items = [x.strip() for x in re.split(r"[；;，,\n]+", v) if x.strip()]
        elif isinstance(v, list):
            items = [str(x).strip() for x in v if str(x).strip()]
        else:
            items = []
        uniq: list[str] = []
        seen = set()
        for it in items:
            if it in seen:
                continue
            seen.add(it)
            uniq.append(it)
            if len(uniq) >= max_items:
                break
        return uniq

    def norm_tests(v: Any, max_items: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if isinstance(v, list):
            for t in v:
                if not isinstance(t, dict):
                    continue
                name = norm_str(t.get("name") or t.get("test_name"))
                value = norm_str(t.get("value") or t.get("result"))
                unit = norm_str(t.get("unit"))
                if not name:
                    continue
                if not (value or unit):
                    continue
                out.append({"name": name, "value": value, "unit": unit})
                if len(out) >= max_items:
                    break
        return out

    normalized: dict[str, Any] = {
        "doc_type": norm_str(obj.get("doc_type")),
        "date": norm_str(obj.get("date")),
        "hospital": norm_str(obj.get("hospital")),
        "department": norm_str(obj.get("department")),
        "doctor": norm_str(obj.get("doctor")),
        "diagnosis": norm_str_list(obj.get("diagnosis"), 4),
        "medications": norm_str_list(obj.get("medications"), 8),
        "key_tests": norm_tests(obj.get("key_tests") or obj.get("tests"), 12),
        "key_points": norm_str_list(obj.get("key_points"), 6),
        "advice": norm_str_list(obj.get("advice"), 6),
        "follow_up": norm_str_list(obj.get("follow_up"), 4),
    }
    if any(
        [
            normalized["date"],
            normalized["hospital"],
            normalized["department"],
            normalized["doctor"],
            normalized["diagnosis"],
            normalized["medications"],
            normalized["key_tests"],
            normalized["key_points"],
            normalized["advice"],
            normalized["follow_up"],
        ]
    ):
        return normalized
    return None


async def _maybe_llm_display_fields(
    ocr_text: str, extracted: dict | None, *, doc_kind: str = ""
) -> dict[str, Any] | None:
    raw_flag = os.getenv("USE_LLM_DISPLAY_FIELDS")
    if raw_flag is None:
        use_llm = True
    else:
        use_llm = str(raw_flag).lower() in ("1", "true", "yes")
    if not use_llm:
        return _normalize_display_fields(_build_display_fields_fallback(extracted))

    try:
        from openai import AsyncOpenAI
    except Exception as e:
        logger.warning(f"OpenAI 客户端导入失败: {e}")
        return _normalize_display_fields(_build_display_fields_fallback(extracted))

    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        return _normalize_display_fields(_build_display_fields_fallback(extracted))

    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.deepseek.com"
    )
    model = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    text_clean = (ocr_text or "").strip()
    extracted_str = ""
    if isinstance(extracted, dict) and extracted:
        try:
            extracted_str = json.dumps(extracted, ensure_ascii=False)
        except Exception:
            extracted_str = str(extracted)

    kind = str(doc_kind or "").strip()
    sys_prompt = (
        "你是医疗文档关键信息抽取助手。你只能依据输入文本抽取信息，禁止编造、推断或引用外部知识。"
        "你必须只输出JSON对象，不要输出解释、前后缀、Markdown或代码块。"
        "若字段缺失请输出空字符串或空数组。"
    )
    schema_hint = (
        "{"
        '"doc_type":"",'
        '"date":"",'
        '"hospital":"",'
        '"department":"",'
        '"doctor":"",'
        '"diagnosis":[""],'
        '"medications":[""],'
        '"key_tests":[{"name":"","value":"","unit":""}],'
        '"key_points":[""],'
        '"advice":[""],'
        '"follow_up":[""]'
        "}"
    )
    user_prompt = (
        f"doc_kind={kind}\n\n"
        f"【已抽取结构化信息(JSON)】\n{extracted_str}\n\n"
        f"【OCR全文】\n{text_clean}\n\n"
        "任务：抽取“一眼看懂”的关键信息，输出严格JSON对象。"
        "要求：只使用上述文本中的内容；不要改写数值与单位；不要输出'无'或'未提供'等占位；"
        "诊断/用药/要点等只列最重要的若干条；key_tests仅列明确出现的检查项目与数值。"
        f"\n输出JSON结构示例：{schema_hint}"
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=900,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"LLM 结构化字段请求失败: {e}")
        return _normalize_display_fields(_build_display_fields_fallback(extracted))

    parsed = _extract_json_payload(raw)
    normalized = _normalize_display_fields(parsed)
    if normalized:
        return normalized
    return _normalize_display_fields(_build_display_fields_fallback(extracted))


def _normalize_document_type(value: str | None) -> str:
    s = str(value or "").strip()
    if not s:
        return "unknown"
    lower = s.lower()
    if lower in {
        "test_report",
        "lab_report",
        "lab_result",
        "inspection_report",
    }:
        return "inspection_report"
    if s in {"检查报告", "化验单", "检验报告"}:
        return "inspection_report"
    return s


def row_to_health_record(row) -> HealthRecord:
    rid = str(row["id"]) if "id" in row else str(row[0])
    created = row.get("created_at")
    updated = row.get("updated_at")
    rec_date = row.get("record_date")
    tags_val = row.get("tags")
    meta_val = row.get("metadata")
    files_val = (
        row.get("file_attachments") if "file_attachments" in row else []
    )
    if isinstance(tags_val, str):
        tags_parsed = deserialize_tags(tags_val)
    elif isinstance(tags_val, list):
        # 阶段48-22 v3+ D 兼容性: 历史数据里 tags 元素可能是 dict,
        # Pydantic List[str] 会拒. 这里把非 str 项转成 str 避免整个列表 500.
        tags_parsed = [str(t) if isinstance(t, str) else json.dumps(t, ensure_ascii=False) for t in tags_val]
    else:
        tags_parsed = []
    if isinstance(meta_val, str):
        meta_parsed = deserialize_metadata(meta_val)
    elif isinstance(meta_val, dict):
        meta_parsed = meta_val
    else:
        meta_parsed = {}
    if isinstance(files_val, str):
        files_parsed = deserialize_tags(files_val)
    elif isinstance(files_val, list):
        files_parsed = files_val
    else:
        files_parsed = []
    if isinstance(created, str):
        created_dt = datetime.fromisoformat(created)
    else:
        created_dt = created
    if isinstance(updated, str):
        updated_dt = datetime.fromisoformat(updated)
    else:
        updated_dt = updated
    if isinstance(rec_date, str):
        try:
            rec_dt = datetime.strptime(rec_date, "%Y-%m-%d").date()
        except Exception:
            rec_dt = None
    else:
        rec_dt = rec_date

    def _to_record_type_enum(val) -> RecordType:
        if isinstance(val, RecordType):
            return val
        s = str(val or "").strip().lower()
        if not s:
            return RecordType.OTHER
        try:
            return RecordType(s)
        except Exception:
            alias = {
                "medical_record": RecordType.MEDICAL_REPORT,
                "inspection_report": RecordType.LAB_RESULT,
                "test_report": RecordType.LAB_RESULT,
            }.get(s)
            return alias or RecordType.OTHER

    def _to_importance_enum(val) -> ImportanceLevel:
        if isinstance(val, ImportanceLevel):
            return val
        s = str(val or "").strip().lower()
        try:
            return ImportanceLevel(s)
        except Exception:
            mapping = {
                "低": "low",
                "中": "medium",
                "高": "high",
                "紧急": "critical",
                "1": "low",
                "2": "medium",
                "3": "high",
                "4": "critical",
            }
            m = mapping.get(s, "medium")
            return ImportanceLevel(m)

    # 阶段48-22 v6: 把 v2 upload_pipeline 留的 metadata.attached_file_ids + 老 file_attachments 表 merge 进来
    # 注: HealthRecord.file_attachments 仍是 List[str] (id only).
    #     富信息 (file_name/original_name/mime/size/ocr_status) 塞 metadata._attached_files_meta
    try:
        merged = _merge_attachments_for_record(rid, files_parsed, meta_parsed) or []
        if merged:
            files_parsed = [m["file_id"] for m in merged]
            meta_parsed = dict(meta_parsed or {})
            meta_parsed["_attached_files_meta"] = merged
    except Exception as _e:
        logger.debug(f"[row_to_health_record] _merge_attachments_for_record failed: {_e}")

    return HealthRecord(
        id=rid,
        title=row.get("title"),
        record_type=_to_record_type_enum(row.get("record_type")),
        summary=row.get("summary"),
        content=row.get("content"),
        importance=_to_importance_enum(row.get("importance")),
        tags=tags_parsed,
        metadata=meta_parsed,
        record_date=rec_dt,
        created_at=created_dt,
        updated_at=updated_dt,
        file_attachments=files_parsed,
    )


def _merge_attachments_for_record(record_id: str, current: list, meta: dict) -> list:
    """阶段48-22 v6: merge 双轨附件.

    来源 A — 老接口 row.files (从 row 直接取出, 已经是 str/file_id list)
    来源 B — file_attachments WHERE record_id = <id> (老的 handle_upload_att 流程)
    来源 C — uploaded_files WHERE id IN (metadata.attached_file_ids[])
        (v2 upload_pipeline 写这里, row_to_health_record 之前漏读)

    返回统一结构 [{file_id|attached_id, file_name|original_name, file_type|mime_type,
                   file_size, ocr_status, public_url}, ...], 去重按 file_id.
    """
    import psycopg
    from psycopg.rows import dict_row as _dr

    # 拼接一段 dsn (跟 hostapi 同源)
    pg_host = os.getenv("DB_HOST", "postgres")
    pg_user = os.getenv("DB_USER", "pha")
    pg_pwd = os.getenv("DB_PASSWORD", "")
    pg_db = os.getenv("MEMORY_DB_NAME", "personal_health_assistant")
    dsn = os.getenv("PHA_BLOB_DSN") or f"postgresql://{pg_user}:{pg_pwd}@{pg_host}:5432/{pg_db}"

    out = []
    seen = set()

    def _push(fid, **kw):
        if not fid:
            return
        k = str(fid)
        if k in seen:
            return
        seen.add(k)
        out.append({"file_id": fid, **kw})

    # A: current files list (string id or dict)
    for item in (current or []):
        if isinstance(item, str):
            _push(item)
        elif isinstance(item, dict):
            fid = item.get("file_id") or item.get("id") or item.get("attached_id")
            _push(fid,
                  file_name=item.get("file_name") or item.get("original_filename") or item.get("name") or item.get("original_name"),
                  file_type=item.get("file_type") or item.get("mime_type"),
                  file_size=item.get("file_size"),
                  ocr_status=item.get("ocr_status"),
                  public_url=item.get("public_url") or item.get("url"))

    # B: file_attachments WHERE record_id
    try:
        with psycopg.connect(dsn, autocommit=False, row_factory=_dr) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, original_filename, mime_type, file_size FROM file_attachments WHERE record_id = %s",
                    (record_id,),
                )
                for r in cur.fetchall():
                    _push(str(r["id"]),
                          file_name=r.get("original_filename"),
                          file_type=r.get("mime_type"),
                          file_size=r.get("file_size"))
    except Exception as _e:
        logger.debug(f"[merge_attachments] file_attachments lookup failed: {_e}")

    # C: uploaded_files WHERE id IN metadata.attached_file_ids
    attached_ids = []
    if isinstance(meta, dict):
        for key in ("attached_file_ids", "files", "attached_file_id"):
            v = meta.get(key)
            if isinstance(v, list):
                attached_ids = v
                break
            if isinstance(v, str):
                attached_ids = [v]
                break
    if attached_ids:
        try:
            with psycopg.connect(dsn, autocommit=False, row_factory=_dr) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, original_name, mime_type, size_bytes, ocr_status, public_url "
                        "FROM uploaded_files WHERE id = ANY(%s)",
                        (attached_ids,),
                    )
                    for r in cur.fetchall():
                        _push(str(r["id"]),
                              file_name=r.get("original_name"),
                              file_type=r.get("mime_type"),
                              file_size=r.get("size_bytes"),
                              ocr_status=r.get("ocr_status"),
                              public_url=r.get("public_url"))
        except Exception as _e:
            logger.debug(f"[merge_attachments] uploaded_files lookup failed: {_e}")

    return out


# 新增：将本系统的记录类型映射为HRM存储工具的类型
def _map_record_type_for_hrm(rt: str) -> str:
    try:
        r = (rt or "").lower()
        if r in {"lab_result", "inspection_report"}:
            return "lab_result"
        if r == "prescription":
            return "prescription"
        if r in {"medical_report", "medical_record"}:
            return "medical_record"
        if r == "surgery":
            return "surgery"
        if r == "vaccination":
            return "vaccination"
        # 其他类型统一归到病历或其他
        if r in {"allergy", "vital_signs"}:
            return "medical_record"
        return "other"
    except Exception:
        return "other"


# 新增：调用HRM存储工具保存记录（失败不影响本地事务）
def _save_to_hrm(
    user_id: str | None,
    record_type: str,
    title: str,
    content: str,
    extracted_data: dict | None = None,
):
    if not HRM_SAVE_RECORD:
        return
    try:
        enabled = str(os.getenv("HRM_DOUBLEWRITE_ENABLED", "0")).lower() in (
            "1",
            "true",
            "yes",
        )
        if not enabled:
            return
        # 空内容不进行HRM入库，避免生成空记录
        if content is None or (
            isinstance(content, str) and content.strip() == ""
        ):
            return
        uid = (
            user_id
            or os.environ.get("A2A_CURRENT_USER_ID")
            or os.environ.get("USER_ID")
        )
        if not uid or str(uid).strip().lower() == "default_user":
            return
        rt_val = getattr(record_type, "value", record_type)
        hrm_type = _map_record_type_for_hrm(str(rt_val))
        payload = json.dumps(extracted_data or {}, ensure_ascii=False)
        # 兼容 mcp.tool 装饰器：优先使用 .fn，否则直接调用
        if hasattr(HRM_SAVE_RECORD, "fn"):
            HRM_SAVE_RECORD.fn(uid, hrm_type, title, content, payload)
        else:
            HRM_SAVE_RECORD(uid, hrm_type, title, content, payload)  # type: ignore
    except Exception as e:
        logger.warning(f"HRM双写失败（忽略不阻塞）：{e}")


# API路由
async def _warmup_optional_tools() -> None:
    try:
        _get_health_records_memory_service()
        if health_records_memory_service:
            try:
                await health_records_memory_service.initialize()
                ms = getattr(
                    health_records_memory_service, "memory_system", None
                )
                if ms and getattr(ms, "embedding_service", None):
                    try:
                        ms.embedding_service.generate_embedding(
                            "warmup for embeddings"
                        )
                        logger.info("记忆嵌入模型预热完成")
                    except Exception as e:
                        logger.warning(f"记忆嵌入模型预热异常: {e}")
            except Exception as e:
                logger.warning(f"记忆系统初始化/预热失败，将跳过: {e}")

        tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        if "extract_text_from_image" in globals() and extract_text_from_image:
            try:
                _ = (
                    extract_text_from_image.fn(tiny_png_b64)
                    if hasattr(extract_text_from_image, "fn")
                    else extract_text_from_image(tiny_png_b64)
                )
                logger.info("OCR工具预热完成")
            except Exception as e:
                logger.warning(f"OCR工具预热异常: {e}")
        if (
            "validate_medical_document" in globals()
            and validate_medical_document
        ):
            try:
                _ = (
                    validate_medical_document.fn("warmup text")
                    if hasattr(validate_medical_document, "fn")
                    else validate_medical_document("warmup text")
                )
                logger.info("医疗文档验证器预热完成")
            except Exception as e:
                logger.warning(f"医疗文档验证器预热异常: {e}")
    except Exception as e:
        logger.warning(f"工具预热过程出现异常（忽略）: {e}")


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库并预热可选工具（OCR与记忆系统）"""
    try:
        init_database()
    except Exception as e:
        logger.error(f"数据库初始化失败（将继续启动，部分功能不可用）: {e}")

    try:
        asyncio.create_task(_warmup_optional_tools())
    except Exception as e:
        logger.warning(f"启动预热任务失败（忽略）: {e}")


def _resolve_user_id(request: Request | None, user_id: str | None) -> str:
    try:
        if user_id and str(user_id).strip():
            return str(user_id).strip()
    except Exception:
        pass
    try:
        if (
            request
            and hasattr(request, "state")
            and hasattr(request.state, "user")
        ):
            u = request.state.user
            if isinstance(u, dict):
                uid = u.get("id") or u.get("user_id") or u.get("uid") or ""
                if isinstance(uid, str) and uid.strip():
                    return uid.strip()
    except Exception:
        pass
    try:
        if request is not None:
            xuid = request.headers.get("X-User-Id") or request.headers.get(
                "x-user-id"
            )
            if isinstance(xuid, str) and xuid.strip():
                return xuid.strip()
    except Exception:
        pass
    try:
        if request is not None:
            auth = request.headers.get("authorization") or request.headers.get(
                "Authorization"
            )
            if isinstance(auth, str) and auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
                payload = jwt.decode(
                    token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
                )
                uid = payload.get("user_id") or payload.get("sub")
                if isinstance(uid, str) and uid.strip():
                    return uid.strip()
    except Exception:
        pass
    try:
        env_uid = os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get(
            "USER_ID"
        )
        if (
            isinstance(env_uid, str)
            and env_uid.strip()
            and env_uid.strip().lower() != "default_user"
        ):
            return env_uid.strip()
    except Exception:
        pass
    return ""


class RAGBackfillRequest(BaseModel):
    user_id: Optional[str] = None
    source_types: List[str] = Field(
        default_factory=lambda: ["health_records", "visit_summaries"]
    )
    limit: int = Field(default=200, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)
    dry_run: bool = False
    include_deleted: bool = False


@app.post("/api/rag/backfill")
async def backfill_rag(payload: RAGBackfillRequest, request: Request = None):
    uid = _resolve_user_id(request, payload.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(
            status_code=500, detail="EmbeddingService不可用，无法回填RAG"
        )

    source_types = [
        str(x).strip() for x in (payload.source_types or []) if str(x).strip()
    ]
    if not source_types:
        raise HTTPException(status_code=400, detail="source_types不能为空")

    limit = int(payload.limit or 200)
    offset = int(payload.offset or 0)

    summary_filter = (
        "" if payload.include_deleted else " AND COALESCE(is_deleted, 0) = 0"
    )

    result: Dict[str, Any] = {
        "success": True,
        "user_id": uid,
        "source_types": source_types,
        "limit": limit,
        "offset": offset,
        "dry_run": bool(payload.dry_run),
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
        "processed_docs": 0,
        "inserted_chunks": 0,
        "per_source": {},
        "errors": [],
    }

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            for st in source_types:
                st_key = st
                per = {
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
                                text = _make_rag_text(
                                    title, r.get("summary"), r.get("content")
                                )
                                per["processed_docs"] += 1
                                result["processed_docs"] += 1
                                if payload.dry_run:
                                    continue
                                inserted = _upsert_rag_document(
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
                                if payload.dry_run:
                                    continue
                                inserted = _upsert_rag_document(
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
                        result["errors"].append(
                            f"unknown source_type: {st_key}"
                        )
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


_GLOBAL_KB_USER_ID = "__global__"
_ADMIN_TOKEN = (os.getenv("ADMIN_TOKEN") or "").strip()


def _require_admin(request: Request | None) -> None:
    if request is None:
        raise HTTPException(status_code=403, detail="缺少请求上下文")
    if not _ADMIN_TOKEN:
        try:
            host = getattr(getattr(request, "client", None), "host", None)
            if host in ("127.0.0.1", "::1", "localhost"):
                return
        except Exception:
            pass
        raise HTTPException(status_code=403, detail="ADMIN_TOKEN未配置")
    token = request.headers.get("X-Admin-Token") or request.headers.get(
        "x-admin-token"
    )
    if not isinstance(token, str) or token.strip() != _ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="无权限")


def _normalize_http_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    p = urlparse(u)
    if not p.scheme:
        return "http://" + u
    return u


class MonitorTarget(BaseModel):
    name: str
    url: str
    path: str = "/"


class MonitorCheckRequest(BaseModel):
    targets: List[MonitorTarget] = Field(default_factory=list)
    timeout: float = Field(default=1.5, ge=0.1, le=10)


def _probe_target(target: MonitorTarget, timeout: float) -> Dict[str, Any]:
    name = (target.name or "").strip() or "service"
    base = _normalize_http_url(target.url)
    path = (target.path or "/").strip() or "/"
    if not base:
        return {"name": name, "ok": False, "error": "empty_url"}
    url = base.rstrip("/") + (path if path.startswith("/") else "/" + path)

    t0 = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "name": name,
            "url": url,
            "ok": resp.status_code < 400,
            "status_code": int(resp.status_code),
            "latency_ms": round(dt_ms, 2),
        }
    except Exception as e:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "name": name,
            "url": url,
            "ok": False,
            "latency_ms": round(dt_ms, 2),
            "error": str(e),
        }


@app.get("/api/admin/monitor/summary")
async def admin_monitor_summary(request: Request = None):
    _require_admin(request)

    db_ok = False
    db_error = ""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = True
    except Exception as e:
        db_ok = False
        db_error = str(e)

    es = _get_embedding_service()
    embedding = {
        "available": es is not None,
        "model": getattr(es, "model_name", None) if es is not None else None,
        "dimension": (
            getattr(es, "dimension", None) if es is not None else None
        ),
    }

    system: Dict[str, Any] = {"available": psutil is not None}
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            du = psutil.disk_usage(os.getcwd())
            system.update(
                {
                    "cpu_percent": float(psutil.cpu_percent(interval=0.05)),
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

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "db": {"ok": db_ok, "error": db_error},
        "embedding": embedding,
        "system": system,
    }


@app.post("/api/admin/monitor/check")
async def admin_monitor_check(
    payload: MonitorCheckRequest, request: Request = None
):
    _require_admin(request)

    targets = payload.targets or []
    timeout = float(payload.timeout or 1.5)
    results: List[Dict[str, Any]] = []
    for t in targets:
        results.append(
            await anyio.to_thread.run_sync(_probe_target, t, timeout)
        )
    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "success": True,
        "count": len(results),
        "ok": ok_count,
        "items": results,
    }


class AdminRAGDocsListRequest(BaseModel):
    user_id: Optional[str] = None
    source_type: Optional[str] = None
    q: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


@app.post("/api/admin/rag/docs")
async def admin_list_rag_docs(
    payload: AdminRAGDocsListRequest, request: Request = None
):
    _require_admin(request)

    uid = (payload.user_id or "").strip()
    st = (payload.source_type or "").strip()
    q = (payload.q or "").strip()
    limit = int(payload.limit or 50)
    offset = int(payload.offset or 0)

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

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
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

    return {
        "success": True,
        "count": len(rows),
        "items": rows,
        "limit": limit,
        "offset": offset,
    }


class AdminRAGChunksListRequest(BaseModel):
    user_id: str
    source_type: str
    source_id: str
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


@app.post("/api/admin/rag/chunks")
async def admin_list_rag_chunks(
    payload: AdminRAGChunksListRequest, request: Request = None
):
    _require_admin(request)

    uid = (payload.user_id or "").strip()
    st = (payload.source_type or "").strip()
    sid = (payload.source_id or "").strip()
    if not uid or not st or not sid:
        raise HTTPException(
            status_code=400, detail="user_id/source_type/source_id不能为空"
        )

    limit = int(payload.limit or 200)
    offset = int(payload.offset or 0)

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
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

    return {
        "success": True,
        "count": len(rows),
        "items": rows,
        "limit": limit,
        "offset": offset,
    }


class AdminRAGSearchRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    source_types: List[str] = Field(default_factory=lambda: ["medical_kb"])
    include_global: bool = True
    limit: int = Field(default=10, ge=1, le=50)


@app.post("/api/admin/rag/search")
async def admin_rag_search(
    payload: AdminRAGSearchRequest, request: Request = None
):
    _require_admin(request)

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query不能为空")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用")

    q_emb = es.generate_embedding(q)
    if not q_emb or len(q_emb) != _RAG_VECTOR_DIM:
        raise HTTPException(status_code=500, detail="Embedding维度不匹配")

    uid = (payload.user_id or "").strip()
    include_global = bool(payload.include_global)
    uids: list[str] = []
    if uid:
        uids.append(uid)
    if include_global and _GLOBAL_KB_USER_ID not in uids:
        uids.append(_GLOBAL_KB_USER_ID)
    if not uids:
        raise HTTPException(
            status_code=400, detail="user_id为空且include_global为false"
        )

    st = [
        str(x).strip() for x in (payload.source_types or []) if str(x).strip()
    ]
    if not st:
        st = ["medical_kb"]

    placeholders_st = ",".join(["%s"] * len(st))
    where_uid = "(" + " OR ".join(["user_id = %s"] * len(uids)) + ")"
    qv = _vector_literal(q_emb)

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
            cursor.execute(
                f"""
                SELECT *
                FROM (
                    SELECT
                        user_id,
                        source_type,
                        source_id,
                        record_type,
                        title,
                        chunk_text,
                        created_at,
                        updated_at,
                        (embedding <=> %s::vector(384)) AS distance,
                        row_number() OVER (
                            PARTITION BY user_id, source_type, source_id
                            ORDER BY (embedding <=> %s::vector(384)) ASC
                        ) AS rn
                    FROM rag_chunks
                    WHERE {where_uid} AND source_type IN ({placeholders_st})
                ) t
                WHERE rn = 1
                ORDER BY distance ASC
                LIMIT %s
                """,
                tuple([qv, qv] + uids + st + [int(payload.limit or 10)]),
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


class AdminRAGReindexRequest(BaseModel):
    user_id: str
    source_type: str
    source_id: str


@app.post("/api/admin/rag/reindex")
async def admin_rag_reindex(
    payload: AdminRAGReindexRequest, request: Request = None
):
    _require_admin(request)

    uid = (payload.user_id or "").strip()
    st = (payload.source_type or "").strip()
    sid = (payload.source_id or "").strip()
    if not uid or not st or not sid:
        raise HTTPException(
            status_code=400, detail="user_id/source_type/source_id不能为空"
        )

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用")

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
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
                raise HTTPException(status_code=404, detail="未找到RAG文档")

            inserted = _upsert_rag_document(
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


class AdminRAGReindexBulkRequest(BaseModel):
    user_id: str
    source_type: str
    source_ids: List[str] = Field(default_factory=list)
    limit: int = Field(default=2000, ge=1, le=20000)


@app.post("/api/admin/rag/reindex/bulk")
async def admin_rag_reindex_bulk(
    payload: AdminRAGReindexBulkRequest, request: Request = None
):
    _require_admin(request)

    uid = (payload.user_id or "").strip()
    st = (payload.source_type or "").strip()
    if not uid or not st:
        raise HTTPException(
            status_code=400, detail="user_id/source_type不能为空"
        )

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用")

    source_ids = [
        str(x).strip() for x in (payload.source_ids or []) if str(x).strip()
    ]
    limit = int(payload.limit or 2000)

    results: List[Dict[str, Any]] = []
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
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
                source_ids = [
                    str(r.get("source_id") or "")
                    for r in rows
                    if r.get("source_id")
                ]

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
                        results.append(
                            {
                                "source_id": sid,
                                "success": False,
                                "error": "未找到RAG文档",
                            }
                        )
                        continue
                    inserted = _upsert_rag_document(
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
                        {
                            "source_id": sid,
                            "success": True,
                            "inserted_chunks": int(inserted or 0),
                        }
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append(
                        {"source_id": sid, "success": False, "error": str(e)}
                    )

    return {
        "success": True,
        "user_id": uid,
        "source_type": st,
        "count": len(results),
        "items": results,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


class MedicalKBDocUpsertRequest(BaseModel):
    user_id: Optional[str] = None
    global_kb: bool = True
    doc_id: Optional[str] = None
    doc_type: Optional[str] = "medical_kb"
    title: str
    content: str


class MedicalKBDocBulkUpsertRequest(BaseModel):
    user_id: Optional[str] = None
    global_kb: bool = True
    docs: List[MedicalKBDocUpsertRequest] = Field(default_factory=list)


@app.post("/api/medical-kb/docs")
async def upsert_medical_kb_doc(
    payload: MedicalKBDocUpsertRequest, request: Request = None
):
    uid = _resolve_user_id(request, payload.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    title = (payload.title or "").strip()
    content = (payload.content or "").strip()
    if not title or not content:
        raise HTTPException(
            status_code=400, detail="title 与 content 不能为空"
        )

    kb_uid = _GLOBAL_KB_USER_ID if payload.global_kb else uid
    doc_id = (payload.doc_id or "").strip() or str(uuid.uuid4())
    doc_type = (payload.doc_type or "").strip() or "medical_kb"

    text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                inserted = _upsert_rag_document(
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
                raise HTTPException(
                    status_code=500, detail=f"知识库入库失败: {e}"
                )

    return {
        "success": True,
        "doc_id": doc_id,
        "user_id": kb_uid,
        "global_kb": bool(payload.global_kb),
        "inserted_chunks": int(inserted or 0),
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


@app.post("/api/medical-kb/docs/bulk")
async def bulk_upsert_medical_kb_docs(
    payload: MedicalKBDocBulkUpsertRequest, request: Request = None
):
    uid = _resolve_user_id(request, payload.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    kb_uid = _GLOBAL_KB_USER_ID if payload.global_kb else uid
    docs = payload.docs or []
    if not docs:
        raise HTTPException(status_code=400, detail="docs不能为空")

    results: List[Dict[str, Any]] = []
    total_chunks = 0
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (d.title or "").strip()
                content = (d.content or "").strip()
                if not title or not content:
                    results.append(
                        {
                            "success": False,
                            "doc_id": d.doc_id,
                            "error": "title 与 content 不能为空",
                        }
                    )
                    continue
                doc_id = (d.doc_id or "").strip() or str(uuid.uuid4())
                doc_type = (d.doc_type or "").strip() or "medical_kb"
                text = "\n".join(
                    [f"标题: {title}", f"内容: {content}"]
                ).strip()
                try:
                    inserted = _upsert_rag_document(
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
                        {
                            "success": False,
                            "doc_id": doc_id,
                            "error": str(e),
                        }
                    )

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(payload.global_kb),
        "docs": results,
        "inserted_chunks": total_chunks,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


class AdminMedicalKBImportDoc(BaseModel):
    doc_id: Optional[str] = None
    doc_type: Optional[str] = "medical_kb"
    title: str
    content: str


class AdminMedicalKBImportRequest(BaseModel):
    global_kb: bool = True
    user_id: Optional[str] = None
    docs: List[AdminMedicalKBImportDoc] = Field(default_factory=list)


class AdminMedicalKBImportFromAPIRequest(BaseModel):
    global_kb: bool = True
    user_id: Optional[str] = None
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Any]] = None
    body_json: Optional[Any] = Field(default=None, alias="json")
    timeout: float = Field(default=20.0, ge=1.0, le=120.0)

    items_path: Optional[str] = None
    doc_id_field: Optional[str] = None
    title_field: Optional[str] = None
    content_field: Optional[str] = None
    content_fields: List[str] = Field(default_factory=list)

    doc_type: Optional[str] = "medical_kb"
    max_items: int = Field(default=50, ge=1, le=500)

    if ConfigDict is not None:
        model_config = ConfigDict(populate_by_name=True)
    else:
        class Config:
            allow_population_by_field_name = True


@app.post("/api/admin/medical-kb/import")
async def admin_import_medical_kb(
    payload: AdminMedicalKBImportRequest, request: Request = None
):
    _require_admin(request)

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    docs = payload.docs or []
    if not docs:
        raise HTTPException(status_code=400, detail="docs不能为空")

    if payload.global_kb:
        kb_uid = _GLOBAL_KB_USER_ID
    else:
        kb_uid = (payload.user_id or "").strip()
        if not kb_uid:
            raise HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    results: List[Dict[str, Any]] = []
    total_chunks = 0
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (d.title or "").strip()
                content = (d.content or "").strip()
                if not title or not content:
                    results.append(
                        {
                            "success": False,
                            "doc_id": d.doc_id,
                            "error": "title 与 content 不能为空",
                        }
                    )
                    continue
                doc_id = (d.doc_id or "").strip() or str(uuid.uuid4())
                doc_type = (d.doc_type or "").strip() or "medical_kb"
                text = "\n".join(
                    [f"标题: {title}", f"内容: {content}"]
                ).strip()
                try:
                    inserted = _upsert_rag_document(
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
        "global_kb": bool(payload.global_kb),
        "docs": results,
        "inserted_chunks": total_chunks,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


@app.delete("/api/admin/medical-kb/docs/{doc_id}")
async def admin_delete_medical_kb_doc(
    doc_id: str,
    global_kb: bool = Query(True),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    _require_admin(request)

    did = (doc_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="doc_id不能为空")

    if global_kb:
        kb_uid = _GLOBAL_KB_USER_ID
    else:
        kb_uid = (user_id or "").strip()
        if not kb_uid:
            raise HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    deleted = 0
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                _ensure_rag_schema(cursor)
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
                raise HTTPException(
                    status_code=500, detail=f"删除知识库文档失败: {e}"
                )

    return {
        "success": True,
        "doc_id": did,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "deleted_chunks": deleted,
    }


@app.get("/api/medical-kb/docs")
async def list_medical_kb_docs(
    user_id: Optional[str] = Query(None),
    global_kb: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    request: Request = None,
):
    uid = _resolve_user_id(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    kb_uid = _GLOBAL_KB_USER_ID if global_kb else uid

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
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


@app.get("/api/medical-kb/stats")
async def get_medical_kb_stats(
    user_id: Optional[str] = Query(None),
    global_kb: bool = Query(True),
    request: Request = None,
):
    uid = _resolve_user_id(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    kb_uid = _GLOBAL_KB_USER_ID if global_kb else uid

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            _ensure_rag_schema(cursor)
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


@app.delete("/api/medical-kb/docs/{doc_id}")
async def delete_medical_kb_doc(
    doc_id: str,
    user_id: Optional[str] = Query(None),
    global_kb: bool = Query(True),
    request: Request = None,
):
    uid = _resolve_user_id(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    kb_uid = _GLOBAL_KB_USER_ID if global_kb else uid
    did = (doc_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="doc_id不能为空")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                _ensure_rag_schema(cursor)
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
                raise HTTPException(
                    status_code=500, detail=f"删除知识库文档失败: {e}"
                )

    return {
        "success": True,
        "doc_id": did,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "deleted_chunks": deleted,
    }


@app.get("/api/health-records/status")
async def get_api_status():
    """检查API状态"""
    return await dashboard_service.get_api_status(sys.modules[__name__])


@app.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await dashboard_service.get_dashboard_stats(
        sys.modules[__name__],
        user_id=user_id,
        request=request,
    )


@app.get("/api/visit-summaries/count")
async def get_visit_summary_count(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.get_visit_summary_count(
        sys.modules[__name__],
        user_id=user_id,
        request=request,
    )


@app.get("/api/dashboard/recent-activities")
async def get_dashboard_recent_activities(
    limit: int = Query(10, ge=1, le=50),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await dashboard_service.get_dashboard_recent_activities(
        sys.modules[__name__],
        limit=limit,
        user_id=user_id,
        request=request,
    )


@app.get("/api/visit-summaries/history", response_model=List[VisitSummary])
async def get_visit_summaries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.get_visit_summaries(
        sys.modules[__name__],
        skip=skip,
        limit=limit,
        user_id=user_id,
        request=request,
    )


@app.get("/api/visit-summaries/{summary_id}", response_model=VisitSummary)
async def get_visit_summary_detail(
    summary_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.get_visit_summary_detail(
        sys.modules[__name__],
        summary_id=summary_id,
        user_id=user_id,
        request=request,
    )


@app.post("/api/visit-summaries/create", response_model=VisitSummary)
async def create_visit_summary(
    summary: VisitSummaryCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.create_visit_summary(
        sys.modules[__name__],
        summary=summary,
        user_id=user_id,
        request=request,
    )


class VisitSummaryBatchCompleteRequest(BaseModel):
    batch_id: str = Field(..., min_length=4)
    visit_date: Optional[str] = None


@app.post("/api/visit-summaries/analyze-image", response_model=VisitSummary)
async def analyze_visit_summary_image(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    visit_date: str = Form(None),
    request: Request = None,
):
    return await visit_summaries_service.analyze_visit_summary_image(
        sys.modules[__name__],
        file=file,
        user_id=user_id,
        visit_date=visit_date,
        request=request,
    )


@app.post("/api/visit-summaries/batch/collect-image")
async def collect_visit_summary_image(
    file: UploadFile = File(...),
    batch_id: str = Form(...),
    user_id: str = Form(None),
    request: Request = None,
):
    return await visit_summaries_service.collect_visit_summary_image(
        sys.modules[__name__],
        file=file,
        batch_id=batch_id,
        user_id=user_id,
        request=request,
    )


@app.post("/api/visit-summaries/batch/complete", response_model=VisitSummary)
async def complete_visit_summary_batch(
    payload: VisitSummaryBatchCompleteRequest,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.complete_visit_summary_batch(
        sys.modules[__name__],
        payload=payload,
        user_id=user_id,
        request=request,
    )


@app.get("/api/consultations/history", response_model=List[Consultation])
async def get_consultation_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    include_summary: bool = Query(False),
    include_health_records: bool = Query(False),
    request: Request = None,
):
    return await consultations_service.get_consultation_history(
        sys.modules[__name__],
        skip=skip,
        limit=limit,
        user_id=user_id,
        include_summary=include_summary,
        include_health_records=include_health_records,
        request=request,
    )


@app.put(
    "/api/visit-summaries/update/{summary_id}", response_model=VisitSummary
)
async def update_visit_summary(
    summary_id: str,
    summary: VisitSummaryCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.update_visit_summary(
        sys.modules[__name__],
        summary_id=summary_id,
        summary=summary,
        user_id=user_id,
        request=request,
    )


@app.delete("/api/visit-summaries/delete/{summary_id}")
async def delete_visit_summary(
    summary_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await visit_summaries_service.delete_visit_summary(
        sys.modules[__name__],
        summary_id=summary_id,
        user_id=user_id,
        request=request,
    )


class ConsultationCreate(BaseModel):
    question: str
    answer: Optional[str] = None
    consultation_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Optional[List[str]] = []


@app.post("/api/consultations/create", response_model=Consultation)
async def create_consultation(
    consultation: ConsultationCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.create_consultation(
        sys.modules[__name__],
        consultation=consultation,
        user_id=user_id,
        request=request,
    )


@app.delete("/api/consultations/delete/{consultation_id}")
async def delete_consultation(
    consultation_id: int,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.delete_consultation(
        sys.modules[__name__],
        consultation_id=consultation_id,
        user_id=user_id,
        request=request,
    )


class ChatMessageCreate(BaseModel):
    consultation_id: str
    role: str
    content: str


@app.post("/api/consultations/message")
async def save_consultation_message(
    message: ChatMessageCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.save_consultation_message(
        sys.modules[__name__],
        message=message,
        user_id=user_id,
        request=request,
    )


@app.get("/api/consultations/{consultation_id}/messages")
async def get_consultation_messages(
    consultation_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await consultations_service.get_consultation_messages(
        sys.modules[__name__],
        consultation_id=consultation_id,
        user_id=user_id,
        request=request,
    )


@app.get("/api/health-records", response_model=List[HealthRecord])
async def get_health_records(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    record_type: Optional[RecordType] = Query(
        None, description="记录类型筛选"
    ),
    importance: Optional[ImportanceLevel] = Query(
        None, description="重要性筛选"
    ),
    search: Optional[str] = Query(None, description="搜索关键词"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    request: Request = None,
):
    """获取健康档案列表（按用户隔离）"""
    return await health_records_service.get_health_records(
        sys.modules[__name__],
        skip=skip,
        limit=limit,
        record_type=record_type,
        importance=importance,
        search=search,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        request=request,
    )


@app.get("/api/health-records/{record_id}", response_model=HealthRecord)
async def get_health_record(
    record_id: str,
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    request: Request = None,
):
    """获取单个健康档案详情（按用户隔离）"""
    return await health_records_service.get_health_record(
        sys.modules[__name__],
        record_id=record_id,
        user_id=user_id,
        request=request,
    )


@app.post("/api/health-records", response_model=HealthRecord)
async def create_health_record(
    record: HealthRecordCreate,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    """创建健康档案（按用户隔离）"""
    return await health_records_service.create_health_record(
        sys.modules[__name__],
        record=record,
        user_id=user_id,
        request=request,
    )


@app.put("/api/health-records/{record_id}", response_model=HealthRecord)
async def update_health_record(
    record_id: str,
    record_update: HealthRecordUpdate,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    """更新健康档案（按用户隔离）"""
    return await health_records_service.update_health_record(
        sys.modules[__name__],
        record_id=record_id,
        record_update=record_update,
        user_id=user_id,
        request=request,
    )


@app.delete("/api/health-records/{record_id}")
async def delete_health_record(
    record_id: str,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    """删除健康档案（按用户隔离）"""
    return await health_records_service.delete_health_record(
        sys.modules[__name__],
        record_id=record_id,
        user_id=user_id,
        request=request,
    )


@app.get("/api/health-records/statistics", response_model=HealthStatistics)
async def get_health_statistics():
    """获取健康数据统计"""
    return await health_records_service.get_health_statistics(
        sys.modules[__name__]
    )


@app.post("/api/health-trends/backfill")
async def backfill_health_trends(
    days: int = Query(365),
    limit: int = Query(200),
    dry_run: bool = Query(True),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")
        total = 0
        updated = 0
        skipped = 0
        updated_ids: list[str] = []
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
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
                        meta_val = deserialize_metadata(meta_val)
                    elif not isinstance(meta_val, dict):
                        meta_val = {}
                    extracted = _ensure_dict_value(
                        meta_val.get("extracted_info")
                        or meta_val.get("extracted_data")
                    )
                    tests = extracted.get("test_results") or extracted.get(
                        "tests"
                    )
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
                    if extract_test_results:
                        try:
                            test_results = (
                                extract_test_results.fn(text)
                                if hasattr(extract_test_results, "fn")
                                else extract_test_results(text)
                            )
                        except Exception:
                            test_results = None
                    if not test_results and extract_medical_info:
                        try:
                            info_json = (
                                extract_medical_info.fn(text)
                                if hasattr(extract_medical_info, "fn")
                                else extract_medical_info(text)
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
                    if not test_results:
                        skipped += 1
                        continue
                    if not isinstance(test_results, dict):
                        skipped += 1
                        continue
                    filtered_results = _filter_test_results(test_results)
                    if filtered_results is None or not filtered_results:
                        skipped += 1
                        continue
                    test_results = filtered_results
                    extracted["test_results"] = test_results
                    meta_val["extracted_info"] = extracted
                    updated += 1
                    if not dry_run:
                        cursor.execute(
                            """
                            UPDATE health_records
                            SET metadata = %s, updated_at = %s
                            WHERE id = %s AND user_id = %s
                            """,
                            (
                                Json(meta_val),
                                datetime.now(),
                                row.get("id"),
                                uid,
                            ),
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
        logger.error(f"回填健康趋势失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health-trends/indicators")
async def get_health_trend_indicators(
    days: int = Query(180),
    include_points: bool = Query(True),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await health_records_service.get_health_trend_indicators(
        sys.modules[__name__],
        days=days,
        include_points=include_points,
        user_id=user_id,
        request=request,
    )


@app.get("/api/health-trends/indicator")
async def get_health_trend_indicator(
    name: str = Query(...),
    days: int = Query(180),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    return await health_records_service.get_health_trend_indicator(
        sys.modules[__name__],
        name=name,
        days=days,
        user_id=user_id,
        request=request,
    )


@app.get("/api/health-records/insights", response_model=HealthInsightsResponse)
async def get_health_insights(
    analysis_type: str = Query("comprehensive", description="分析类型"),
    include_recommendations: bool = Query(True, description="包含建议"),
    include_trends: bool = Query(True, description="包含趋势"),
    include_risks: bool = Query(True, description="包含风险"),
):
    """获取健康洞察"""
    return await health_records_service.get_health_insights(
        sys.modules[__name__],
        analysis_type=analysis_type,
        include_recommendations=include_recommendations,
        include_trends=include_trends,
        include_risks=include_risks,
    )


@app.post("/api/health-records/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    skip_ocr: str | None = Form(None),
    request: Request = None,
):
    """上传文件"""
    return await health_records_service.upload_file(
        sys.modules[__name__],
        file=file,
        user_id=user_id,
        skip_ocr=skip_ocr,
        request=request,
    )


async def _process_pending_ocr(
    record_id: str,
    file_id: str,
    user_id: str,
    file_path: str,
    original_filename: str = "",
    mime_type: str = "",
):
    return await health_records_service._process_pending_ocr(
        sys.modules[__name__],
        record_id=record_id,
        file_id=file_id,
        user_id=user_id,
        file_path=file_path,
        original_filename=original_filename,
        mime_type=mime_type,
    )


# 新增：批量上传多个文件（逐个调用单文件上传逻辑，保证返回结构一致）
@app.post("/api/health-records/upload/multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    user_id: str = Form(None),
    request: Request = None,
):
    return await health_records_service.upload_multiple_files(
        sys.modules[__name__],
        files=files,
        user_id=user_id,
        request=request,
    )


# 新增：将指定用户的本地SQLite健康记录同步到HRM（PostgreSQL）
@app.post("/api/health-records/sync-to-hrm")
async def sync_sqlite_to_hrm(
    user_id: str = Query(..., description="需要同步的用户ID")
):
    return await health_records_service.sync_sqlite_to_hrm(
        sys.modules[__name__],
        user_id=user_id,
    )


# 新增：获取指定记录的结构化与OCR信息（上移到启动语句之前）
@app.get("/api/health-records/{record_id}/extracted")
async def get_record_extracted_info(record_id: str):
    return await health_records_service.get_record_extracted_info(
        sys.modules[__name__],
        record_id=record_id,
    )


# 新增：按 file_id 读取并以内联方式返回附件文件
@app.get("/api/health-records/files/{file_id}")
async def get_file_attachment(file_id: str):
    return await health_records_service.get_file_attachment(
        sys.modules[__name__],
        file_id=file_id,
    )


_ADMIN_PAGE_HTML = """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>后台管理</title>
    <style>
      :root { color-scheme: light dark; }
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"; margin: 16px; }
      h1 { margin: 0 0 12px 0; font-size: 18px; }
      h2 { margin: 18px 0 8px 0; font-size: 16px; }
      .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
      input[type="text"], input[type="password"], textarea { padding: 8px; border: 1px solid #6666; border-radius: 6px; min-width: 240px; }
      textarea { width: min(980px, 100%); height: 140px; }
      button { padding: 8px 10px; border: 1px solid #6666; border-radius: 8px; cursor: pointer; }
      table { border-collapse: collapse; width: 100%; max-width: 1200px; }
      td, th { border: 1px solid #6663; padding: 8px; vertical-align: top; }
      th { text-align: left; }
      .muted { opacity: 0.75; }
      .ok { color: #0a7; }
      .bad { color: #d33; }
      .box { border: 1px solid #6663; border-radius: 10px; padding: 12px; max-width: 1200px; }
      .grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
      @media (min-width: 1024px) { .grid { grid-template-columns: 1fr 1fr; } }
      pre { white-space: pre-wrap; word-break: break-word; }
    </style>
  </head>
  <body>
    <h1>后台管理</h1>

    <div class="box">
      <div class="row">
        <label>ADMIN_TOKEN</label>
        <input id="adminToken" type="password" placeholder="填入 ADMIN_TOKEN" />
        <button id="saveTokenBtn">保存</button>
        <span class="muted">请求会带 X-Admin-Token</span>
      </div>
    </div>

    <h2>监控</h2>
    <div class="box grid">
      <div>
        <div class="row">
          <button id="refreshSummaryBtn">刷新概览</button>
          <button id="runChecksBtn">检查服务</button>
          <span id="summaryStatus" class="muted"></span>
        </div>
        <pre id="summaryJson" class="muted"></pre>
      </div>
      <div>
        <div class="row">
          <span class="muted">Targets（本地保存）</span>
          <button id="addTargetBtn">新增</button>
          <button id="resetTargetsBtn">重置默认</button>
        </div>
        <table>
          <thead>
            <tr><th>名称</th><th>URL</th><th>Path</th><th></th></tr>
          </thead>
          <tbody id="targetsTbody"></tbody>
        </table>
        <pre id="checksJson" class="muted"></pre>
      </div>
    </div>

    <h2>医疗 RAG</h2>
    <div class="box">
      <div class="row">
        <button id="listDocsBtn">列出文档</button>
        <input id="docFilter" type="text" placeholder="过滤（source_id/title）" />
        <button id="searchBtn">检索</button>
        <input id="searchQuery" type="text" placeholder="查询（如 头痛/发热/阿司匹林）" />
      </div>
      <div class="row muted">
        <span>默认：global_kb(__global__) + source_type=medical_kb</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>doc_id</th><th>title</th><th>type</th><th>chunks</th><th>updated</th><th></th>
          </tr>
        </thead>
        <tbody id="docsTbody"></tbody>
      </table>
      <pre id="searchJson" class="muted"></pre>
    </div>

    <h2>入库</h2>
    <div class="box">
      <div class="row">
        <input id="ingestDocId" type="text" placeholder="doc_id（可空，自动生成）" />
        <input id="ingestTitle" type="text" placeholder="title" />
        <input id="ingestType" type="text" placeholder="doc_type（guideline/drug_label/...）" />
        <button id="ingestBtn">入库</button>
      </div>
      <textarea id="ingestContent" placeholder="粘贴指南/说明书正文（建议包含章节标题）"></textarea>
      <pre id="ingestJson" class="muted"></pre>
    </div>

    <script>
      const LS_TOKEN = "adminToken";
      const LS_TARGETS = "monitorTargets";

      function getToken() {
        return (localStorage.getItem(LS_TOKEN) || "").trim();
      }
      function setToken(v) {
        localStorage.setItem(LS_TOKEN, (v || "").trim());
      }
      function headers() {
        const t = getToken();
        return t ? { "Content-Type": "application/json", "X-Admin-Token": t } : { "Content-Type": "application/json" };
      }
      function defaultTargets() {
        const origin = location.origin;
        return [
          { name: "health-api", url: origin, path: "/api/health-records/status" },
          { name: "a2a-health-records", url: "http://localhost:10010", path: "/.well-known/agent.json" },
          { name: "a2a-health-advisor", url: "http://localhost:10011", path: "/.well-known/agent.json" },
          { name: "a2a-medication", url: "http://localhost:10012", path: "/.well-known/agent.json" },
          { name: "a2a-visit-summary", url: "http://localhost:10013", path: "/.well-known/agent.json" },
          { name: "a2a-rag", url: "http://localhost:10005", path: "/.well-known/agent.json" }
        ];
      }
      function loadTargets() {
        try {
          const raw = localStorage.getItem(LS_TARGETS);
          if (!raw) return defaultTargets();
          const t = JSON.parse(raw);
          if (!Array.isArray(t) || t.length === 0) return defaultTargets();
          return t;
        } catch {
          return defaultTargets();
        }
      }
      function saveTargets(t) {
        localStorage.setItem(LS_TARGETS, JSON.stringify(t || []));
      }
      function renderTargets() {
        const tbody = document.getElementById("targetsTbody");
        tbody.innerHTML = "";
        const t = loadTargets();
        t.forEach((it, idx) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><input data-k="name" data-i="${idx}" type="text" value="${(it.name||"").replaceAll('"','&quot;')}" /></td>
            <td><input data-k="url" data-i="${idx}" type="text" value="${(it.url||"").replaceAll('"','&quot;')}" /></td>
            <td><input data-k="path" data-i="${idx}" type="text" value="${(it.path||"").replaceAll('"','&quot;')}" /></td>
            <td><button data-del="${idx}">删除</button></td>
          `;
          tbody.appendChild(tr);
        });

        tbody.querySelectorAll("input").forEach((inp) => {
          inp.addEventListener("change", (e) => {
            const el = e.target;
            const i = parseInt(el.getAttribute("data-i"), 10);
            const k = el.getAttribute("data-k");
            const cur = loadTargets();
            cur[i] = { ...cur[i], [k]: el.value };
            saveTargets(cur);
          });
        });
        tbody.querySelectorAll("button[data-del]").forEach((btn) => {
          btn.addEventListener("click", () => {
            const i = parseInt(btn.getAttribute("data-del"), 10);
            const cur = loadTargets();
            cur.splice(i, 1);
            saveTargets(cur);
            renderTargets();
          });
        });
      }

      async function fetchJson(url, opts) {
        const resp = await fetch(url, opts);
        const text = await resp.text();
        let data = null;
        try { data = JSON.parse(text); } catch { data = { raw: text }; }
        if (!resp.ok) {
          throw new Error((data && (data.detail || data.error)) ? (data.detail || data.error) : ("HTTP " + resp.status));
        }
        return data;
      }

      async function refreshSummary() {
        const el = document.getElementById("summaryStatus");
        const out = document.getElementById("summaryJson");
        el.textContent = "加载中...";
        try {
          const data = await fetchJson("/api/admin/monitor/summary", { method: "GET", headers: headers() });
          out.textContent = JSON.stringify(data, null, 2);
          el.textContent = "OK";
          el.className = "ok";
        } catch (e) {
          out.textContent = String(e);
          el.textContent = "ERROR";
          el.className = "bad";
        }
      }

      async function runChecks() {
        const out = document.getElementById("checksJson");
        out.textContent = "检查中...";
        try {
          const data = await fetchJson("/api/admin/monitor/check", {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ targets: loadTargets(), timeout: 2.0 })
          });
          out.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
          out.textContent = String(e);
        }
      }

      async function listDocs() {
        const out = document.getElementById("searchJson");
        const tbody = document.getElementById("docsTbody");
        const q = (document.getElementById("docFilter").value || "").trim();
        out.textContent = "";
        tbody.innerHTML = "";
        try {
          const data = await fetchJson("/api/admin/rag/docs", {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ source_type: "medical_kb", q, limit: 50, offset: 0 })
          });
          (data.items || []).forEach((it) => {
            const tr = document.createElement("tr");
            const docId = it.source_id || "";
            const title = it.title || "";
            const rt = it.record_type || "";
            const chunks = it.chunk_count || 0;
            const updated = (it.updated_at || "").toString().slice(0, 19).replace("T"," ");
            tr.innerHTML = `
              <td>${docId}</td>
              <td>${title}</td>
              <td>${rt}</td>
              <td>${chunks}</td>
              <td>${updated}</td>
              <td>
                <button data-del="${docId}">删除</button>
              </td>
            `;
            tbody.appendChild(tr);
          });
          tbody.querySelectorAll("button[data-del]").forEach((btn) => {
            btn.addEventListener("click", async () => {
              const docId = btn.getAttribute("data-del");
              if (!docId) return;
              if (!confirm("确认删除 doc_id=" + docId + " ?")) return;
              try {
                const data = await fetchJson("/api/admin/medical-kb/docs/" + encodeURIComponent(docId) + "?global_kb=true", {
                  method: "DELETE",
                  headers: headers()
                });
                out.textContent = JSON.stringify(data, null, 2);
                await listDocs();
              } catch (e) {
                out.textContent = String(e);
              }
            });
          });
        } catch (e) {
          out.textContent = String(e);
        }
      }

      async function ragSearch() {
        const out = document.getElementById("searchJson");
        const q = (document.getElementById("searchQuery").value || "").trim();
        if (!q) { out.textContent = "请输入查询"; return; }
        out.textContent = "查询中...";
        try {
          const data = await fetchJson("/api/admin/rag/search", {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ query: q, source_types: ["medical_kb"], include_global: true, limit: 10 })
          });
          out.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
          out.textContent = String(e);
        }
      }

      async function ingest() {
        const out = document.getElementById("ingestJson");
        const doc_id = (document.getElementById("ingestDocId").value || "").trim();
        const title = (document.getElementById("ingestTitle").value || "").trim();
        const doc_type = (document.getElementById("ingestType").value || "guideline").trim();
        const content = (document.getElementById("ingestContent").value || "").trim();
        if (!title || !content) { out.textContent = "title/content 不能为空"; return; }
        out.textContent = "入库中...";
        try {
          const payload = { global_kb: true, docs: [{ doc_id: doc_id || null, doc_type, title, content }] };
          const data = await fetchJson("/api/admin/medical-kb/import", {
            method: "POST",
            headers: headers(),
            body: JSON.stringify(payload)
          });
          out.textContent = JSON.stringify(data, null, 2);
          await listDocs();
        } catch (e) {
          out.textContent = String(e);
        }
      }

      document.getElementById("saveTokenBtn").addEventListener("click", () => {
        setToken(document.getElementById("adminToken").value);
        document.getElementById("adminToken").value = getToken();
      });
      document.getElementById("refreshSummaryBtn").addEventListener("click", refreshSummary);
      document.getElementById("runChecksBtn").addEventListener("click", runChecks);
      document.getElementById("listDocsBtn").addEventListener("click", listDocs);
      document.getElementById("searchBtn").addEventListener("click", ragSearch);
      document.getElementById("ingestBtn").addEventListener("click", ingest);
      document.getElementById("addTargetBtn").addEventListener("click", () => {
        const cur = loadTargets();
        cur.push({ name: "service", url: "http://localhost:8000", path: "/" });
        saveTargets(cur);
        renderTargets();
      });
      document.getElementById("resetTargetsBtn").addEventListener("click", () => {
        saveTargets(defaultTargets());
        renderTargets();
      });

      document.getElementById("adminToken").value = getToken();
      renderTargets();
      refreshSummary();
    </script>
  </body>
</html>
""".strip()


@app.get("/admin")
async def admin_page():
    return HTMLResponse(_ADMIN_PAGE_HTML)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
