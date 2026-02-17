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
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from enum import Enum
import json
import os
import asyncio
import uuid
import hashlib
from pathlib import Path
import logging
from contextlib import contextmanager
import base64
import mimetypes
import time
from urllib.parse import urlparse
import requests
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool
import jwt
import re
import anyio

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
    import importlib, sys

    # 解决 storage_tool 内部使用非限定导入 `database_config` 的问题
    # 预先将 HealthRecordsManager.database_config 注入到 sys.modules，使其解析为正确模块
    hrm_db_config = importlib.import_module("HealthRecordsManager.database_config")
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
class RecordType(str, Enum):
    MEDICAL_REPORT = "medical_report"
    LAB_RESULT = "lab_result"
    PRESCRIPTION = "prescription"
    VACCINATION = "vaccination"
    ALLERGY = "allergy"
    SURGERY = "surgery"
    SYMPTOM = "symptom"
    VITAL_SIGNS = "vital_signs"
    OTHER = "other"


class ImportanceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HealthRecordBase(BaseModel):
    title: str = Field(..., description="记录标题")
    record_type: RecordType = Field(..., description="记录类型")
    summary: Optional[str] = Field(None, description="记录摘要")
    content: Optional[str] = Field(None, description="详细内容")
    importance: ImportanceLevel = Field(
        ImportanceLevel.MEDIUM, description="重要性级别"
    )
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="元数据"
    )
    record_date: Optional[date] = Field(None, description="记录日期")


class HealthRecordCreate(HealthRecordBase):
    pass


class HealthRecordUpdate(BaseModel):
    title: Optional[str] = None
    record_type: Optional[RecordType] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    importance: Optional[ImportanceLevel] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    record_date: Optional[date] = None


class HealthRecord(HealthRecordBase):
    id: str = Field(..., description="记录ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    file_attachments: Optional[List[str]] = Field(
        default_factory=list, description="附件文件列表"
    )


class HealthStatistics(BaseModel):
    total_records: int
    records_by_type: Dict[str, int]
    records_by_importance: Dict[str, int]
    recent_records_count: int
    last_updated: Optional[datetime]


class HealthInsight(BaseModel):
    id: str
    type: str
    title: str
    summary: str
    details: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[float] = None
    tags: Optional[List[str]] = None
    recommendations: Optional[List[str]] = None
    related_records: Optional[List[str]] = None
    metrics: Optional[Dict[str, Any]] = None


class HealthInsightsResponse(BaseModel):
    insights: List[HealthInsight]
    health_score: Optional[Dict[str, Any]] = None
    quick_tips: Optional[List[Dict[str, str]]] = None


class VisitSummary(BaseModel):
    id: str
    user_id: str
    summary_id: Optional[str] = None
    title: Optional[str] = None
    visit_date: Optional[date] = None
    doctor: Optional[str] = None
    hospital: Optional[str] = None
    department: Optional[str] = None
    chief_complaint: Optional[str] = None
    symptoms: Optional[str] = None
    examination: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    follow_up: Optional[str] = None
    notes: Optional[str] = None
    files: Optional[List[str]] = []
    tests: Optional[List[Dict[str, Any]]] = []
    summary_content: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    generated_by: Optional[str] = None
    is_deleted: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VisitSummaryCreate(BaseModel):
    summary_id: Optional[str] = None
    title: Optional[str] = None
    visit_date: Optional[date] = None
    doctor: Optional[str] = None
    hospital: Optional[str] = None
    department: Optional[str] = None
    chief_complaint: Optional[str] = None
    symptoms: Optional[str] = None
    examination: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    follow_up: Optional[str] = None
    notes: Optional[str] = None
    files: Optional[List[str]] = []
    tests: Optional[List[Dict[str, Any]]] = []
    summary_content: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    generated_by: Optional[str] = None


class Consultation(BaseModel):
    id: Optional[int] = None
    user_id: str
    consultation_id: Optional[str]
    session_id: Optional[str]
    question: Optional[str]
    answer: Optional[str]
    tags: Optional[List[str]]
    created_at: datetime


class DashboardActivity(BaseModel):
    id: str
    title: str
    time: str
    icon: str


class DashboardStats(BaseModel):
    health_records_count: int = 0
    medication_count: int = 0
    summary_count: int = 0
    recent_activities: List[DashboardActivity] = Field(default_factory=list)


MODULE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = MODULE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "pha"),
    "password": os.getenv("DB_PASSWORD", "pha_pass"),
    "dbname": os.getenv(
        "DB_NAME", os.getenv("POSTGRES_DB", "personal_health_assistant")
    ),
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
    dsn = os.getenv("DATABASE_URL")
    if isinstance(dsn, str) and dsn.strip():
        return dsn.strip()
    user = DB_CONFIG.get("user") or "pha"
    password = DB_CONFIG.get("password") or ""
    host = DB_CONFIG.get("host") or "localhost"
    port = DB_CONFIG.get("port") or 5432
    dbname = DB_CONFIG.get("dbname") or "personal_health_assistant"
    auth = f"{user}:{password}" if password else f"{user}"
    return f"postgresql://{auth}@{host}:{port}/{dbname}"

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
        _db_pool = ConnectionPool(_build_db_dsn(), max_size=max(max_size, 1), timeout=timeout)
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

def _split_text_for_rag(text: str, chunk_size: int = 650, overlap: int = 120) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    if chunk_size <= 0:
        chunk_size = 650
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)

    chunks: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        j = min(n, i + chunk_size)
        chunk = s[i:j].strip()
        if chunk:
            chunks.append(chunk)
        if j >= n:
            break
        i = max(0, j - overlap)
    return chunks

def _ensure_rag_schema(cursor) -> None:
    global _rag_schema_ready
    if _rag_schema_ready:
        return
    try:
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            pass
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
        try:
            cursor.execute(
                """
                ALTER TABLE rag_chunks
                DROP CONSTRAINT IF EXISTS rag_chunks_source_type_source_id_chunk_index_embedding_model_key
                """
            )
        except Exception:
            pass
        try:
            cursor.execute(
                """
                ALTER TABLE rag_chunks
                ADD CONSTRAINT rag_chunks_user_source_chunk_model_key
                UNIQUE (user_id, source_type, source_id, chunk_index, embedding_model)
                """
            )
        except Exception:
            pass
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

def _make_rag_text(title: str | None, summary: str | None, content: str | None) -> str:
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

    chunks = _split_text_for_rag(text)
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
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

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
                    UNIQUE (source_type, source_id, chunk_index, embedding_model)
                )
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


def _is_valid_test_name(name: str, unit: str = "") -> bool:
    text = (name or "").strip()
    if not text:
        return False
    if len(text) > 24:
        return False
    blacklist = [
        "test",
        "测试",
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
    lower = text.lower()
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
    ]
    if any(kw in text for kw in allowed_keywords):
        return True
    allowed_abbr = {
        "hba1c",
        "hdl",
        "ldl",
        "hgb",
        "wbc",
        "rbc",
        "plt",
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
    if re.fullmatch(r"[a-z]{2,6}\d{0,2}", lower):
        return True
    unit_text = (unit or "").strip()
    if unit_text and len(unit_text) <= 12:
        return True
    return False


def _filter_test_results(tests: Any) -> dict | None:
    if not isinstance(tests, dict):
        return None
    cleaned: dict = {}
    for k, v in tests.items():
        if not k:
            continue
        unit = ""
        if isinstance(v, dict):
            unit = str(v.get("unit") or "").strip()
        if not _is_valid_test_name(str(k), unit):
            continue
        cleaned[str(k).strip()] = v
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
    low = (paren or base).lower()
    mapping = {
        "hgb": "血红蛋白",
        "hb": "血红蛋白",
        "wbc": "白细胞",
        "rbc": "红细胞",
        "plt": "血小板",
        "mch": "平均红细胞血红蛋白量",
        "mcv": "平均红细胞体积",
        "hct": "红细胞压积",
        "rdw": "红细胞分布宽度",
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
    }
    if low in mapping:
        return mapping[low] + suffix
    if base and any(ch.isalpha() for ch in base) and base.lower() in mapping:
        return mapping[base.lower()] + suffix
    if paren and paren.lower() in mapping:
        return mapping[paren.lower()] + suffix
    if base:
        normalized = base
        normalized = normalized.replace("血红蛋白浓度", "血红蛋白")
        normalized = normalized.replace("糖化血红蛋白(hba1c)", "糖化血红蛋白")
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


def _prepare_metadata_with_tests(content: str | None, metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    meta = metadata if isinstance(metadata, dict) else {}
    extracted = _ensure_dict_value(meta.get("extracted_info") or meta.get("extracted_data"))
    tests = extracted.get("test_results") or extracted.get("tests")
    text = (content or "").strip()
    if (not tests) and text and extract_test_results:
        try:
            tests = (
                extract_test_results.fn(text)
                if hasattr(extract_test_results, "fn")
                else extract_test_results(text)
            )
        except Exception:
            tests = None
    if (not tests) and text and extract_medical_info:
        try:
            info_json = (
                extract_medical_info.fn(text)
                if hasattr(extract_medical_info, "fn")
                else extract_medical_info(text)
            )
            info_obj = json.loads(info_json) if isinstance(info_json, str) else info_json
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
        item = {"name": normalized_name, "unit": "", "points": []}
        store[normalized_name] = item
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
                bp = _split_bp_value(val)
                if bp:
                    _append_indicator_point(
                        store,
                        f"{k}-收缩压",
                        unit or "mmHg",
                        date_val,
                        bp[0],
                        source,
                        record_id,
                    )
                    _append_indicator_point(
                        store,
                        f"{k}-舒张压",
                        unit or "mmHg",
                        date_val,
                        bp[1],
                        source,
                        record_id,
                    )
                else:
                    _append_indicator_point(
                        store, str(k).strip(), unit, date_val, val, source, record_id
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
                        store, str(k).strip(), "", date_val, v, source, record_id
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
        dt = item.get("date") or date_val
        bp = _split_bp_value(val)
        if bp and name:
            _append_indicator_point(
                store, f"{name}-收缩压", unit or "mmHg", dt, bp[0], source, record_id
            )
            _append_indicator_point(
                store, f"{name}-舒张压", unit or "mmHg", dt, bp[1], source, record_id
            )
        else:
            _append_indicator_point(store, name, unit, dt, val, source, record_id)


def _finalize_indicator_items(store: dict, include_points: bool) -> list:
    indicators = []
    for item in store.values():
        points = item.get("points") or []
        points = [p for p in points if p.get("date")]
        points.sort(key=lambda x: x.get("date") or "")
        item["count"] = len(points)
        item["points"] = points[-200:]
        nums = [p.get("value") for p in points if isinstance(p.get("value"), (int, float))]
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
    indicators.sort(key=lambda x: (x.get("latest") or {}).get("date") or "", reverse=True)
    return indicators


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
                                    str(it.get("text") or it.get("word") or "").strip()
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


def _generate_ai_summary(ocr_text: str, extracted: dict | None) -> str:
    try:
        text_clean = (ocr_text or "").strip().replace("\n", " ")
        parts = []
        if isinstance(extracted, dict):
            doc_type = extracted.get("document_type") or ""
            date = extracted.get("date") or extracted.get("record_date") or ""
            diagnosis = extracted.get("diagnosis") or ""
            result = extracted.get("result") or extracted.get("conclusion") or ""
            prescription = (
                extracted.get("prescription") or extracted.get("medications") or ""
            )
            tests = extracted.get("tests") or ""
            key = extracted.get("key_findings") or extracted.get("summary") or ""
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
                for u in ("mmol", "μmol", "umol", "×10", "10^", "/l", "mg/l", "g/l")
            )
            is_lab_kw = any(
                k in ln for k in ("检验", "化验", "血常规", "生化", "参考范围", "结果")
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
            if is_rx_kw or is_med_form or is_count_dose or (is_dose and not is_lab_unit):
                if is_lab_unit or is_lab_kw:
                    pass
                else:
                    rx_lines.append(ln)

            if any(k in ln for k in ("影像", "CT", "MRI", "超声", "X线", "心电图")):
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
        summary_text = "\n\n".join([ln for ln in lines if ln.strip()]).strip() or None

        fields: dict[str, Any] = {
            "diagnosis": "；".join(diagnosis_list) if diagnosis_list else None,
            "medications": meds,
            "medication_names": list(dict.fromkeys([n for n in med_names if n])),
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
        summary_text = "\n\n".join([ln for ln in lines if ln.strip()]).strip() or None

        fields: dict[str, Any] = {
            "diagnosis": "；".join(diagnosis_list) if diagnosis_list else None,
            "medications": meds,
            "medication_names": list(dict.fromkeys([n for n in med_names if n])),
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


async def _maybe_llm_summary(ocr_text: str, extracted: dict | None) -> str | None:
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
        model = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
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
                for k in ("prescription", "medication", "medications", "用药", "处方"):
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


def _normalize_document_type(value: str | None) -> str:
    s = str(value or "").strip()
    if not s:
        return "unknown"
    lower = s.lower()
    if lower in {"test_report", "lab_report", "lab_result", "inspection_report"}:
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
    files_val = row.get("file_attachments") if "file_attachments" in row else []
    if isinstance(tags_val, str):
        tags_parsed = deserialize_tags(tags_val)
    elif isinstance(tags_val, list):
        tags_parsed = tags_val
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
        if content is None or (isinstance(content, str) and content.strip() == ""):
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
                ms = getattr(health_records_memory_service, "memory_system", None)
                if ms and getattr(ms, "embedding_service", None):
                    try:
                        ms.embedding_service.generate_embedding("warmup for embeddings")
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
        if "validate_medical_document" in globals() and validate_medical_document:
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
        if request and hasattr(request, "state") and hasattr(request.state, "user"):
            u = request.state.user
            if isinstance(u, dict):
                uid = u.get("id") or u.get("user_id") or u.get("uid") or ""
                if isinstance(uid, str) and uid.strip():
                    return uid.strip()
    except Exception:
        pass
    try:
        if request is not None:
            xuid = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
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
                payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
                uid = payload.get("user_id") or payload.get("sub")
                if isinstance(uid, str) and uid.strip():
                    return uid.strip()
    except Exception:
        pass
    try:
        env_uid = os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID")
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
        raise HTTPException(status_code=500, detail="EmbeddingService不可用，无法回填RAG")

    source_types = [str(x).strip() for x in (payload.source_types or []) if str(x).strip()]
    if not source_types:
        raise HTTPException(status_code=400, detail="source_types不能为空")

    limit = int(payload.limit or 200)
    offset = int(payload.offset or 0)

    summary_filter = "" if payload.include_deleted else " AND COALESCE(is_deleted, 0) = 0"

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
                per = {"source_type": st_key, "processed_docs": 0, "inserted_chunks": 0, "errors": []}

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
                                text = _make_rag_text(title, r.get("summary"), r.get("content"))
                                per["processed_docs"] += 1
                                result["processed_docs"] += 1
                                if payload.dry_run:
                                    continue
                                inserted = _upsert_rag_document(
                                    cursor,
                                    user_id=uid,
                                    source_type="health_records",
                                    source_id=doc_id,
                                    record_type=str(record_type) if record_type is not None else None,
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
    token = request.headers.get("X-Admin-Token") or request.headers.get("x-admin-token")
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
        "dimension": getattr(es, "dimension", None) if es is not None else None,
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
async def admin_monitor_check(payload: MonitorCheckRequest, request: Request = None):
    _require_admin(request)

    targets = payload.targets or []
    timeout = float(payload.timeout or 1.5)
    results: List[Dict[str, Any]] = []
    for t in targets:
        results.append(await anyio.to_thread.run_sync(_probe_target, t, timeout))
    ok_count = sum(1 for r in results if r.get("ok"))
    return {"success": True, "count": len(results), "ok": ok_count, "items": results}


class AdminRAGDocsListRequest(BaseModel):
    user_id: Optional[str] = None
    source_type: Optional[str] = None
    q: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


@app.post("/api/admin/rag/docs")
async def admin_list_rag_docs(payload: AdminRAGDocsListRequest, request: Request = None):
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
async def admin_list_rag_chunks(payload: AdminRAGChunksListRequest, request: Request = None):
    _require_admin(request)

    uid = (payload.user_id or "").strip()
    st = (payload.source_type or "").strip()
    sid = (payload.source_id or "").strip()
    if not uid or not st or not sid:
        raise HTTPException(status_code=400, detail="user_id/source_type/source_id不能为空")

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
async def admin_rag_search(payload: AdminRAGSearchRequest, request: Request = None):
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
        raise HTTPException(status_code=400, detail="user_id为空且include_global为false")

    st = [str(x).strip() for x in (payload.source_types or []) if str(x).strip()]
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
async def admin_rag_reindex(payload: AdminRAGReindexRequest, request: Request = None):
    _require_admin(request)

    uid = (payload.user_id or "").strip()
    st = (payload.source_type or "").strip()
    sid = (payload.source_id or "").strip()
    if not uid or not st or not sid:
        raise HTTPException(status_code=400, detail="user_id/source_type/source_id不能为空")

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
        raise HTTPException(status_code=400, detail="user_id/source_type不能为空")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用")

    source_ids = [str(x).strip() for x in (payload.source_ids or []) if str(x).strip()]
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
async def upsert_medical_kb_doc(payload: MedicalKBDocUpsertRequest, request: Request = None):
    uid = _resolve_user_id(request, payload.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用，无法入库知识库文档")

    title = (payload.title or "").strip()
    content = (payload.content or "").strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="title 与 content 不能为空")

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
                raise HTTPException(status_code=500, detail=f"知识库入库失败: {e}")

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
async def bulk_upsert_medical_kb_docs(payload: MedicalKBDocBulkUpsertRequest, request: Request = None):
    uid = _resolve_user_id(request, payload.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用，无法入库知识库文档")

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
                text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()
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


@app.post("/api/admin/medical-kb/import")
async def admin_import_medical_kb(payload: AdminMedicalKBImportRequest, request: Request = None):
    _require_admin(request)

    es = _get_embedding_service()
    if es is None:
        raise HTTPException(status_code=500, detail="EmbeddingService不可用，无法入库知识库文档")

    docs = payload.docs or []
    if not docs:
        raise HTTPException(status_code=400, detail="docs不能为空")

    if payload.global_kb:
        kb_uid = _GLOBAL_KB_USER_ID
    else:
        kb_uid = (payload.user_id or "").strip()
        if not kb_uid:
            raise HTTPException(status_code=400, detail="global_kb=false时必须提供user_id")

    results: List[Dict[str, Any]] = []
    total_chunks = 0
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (d.title or "").strip()
                content = (d.content or "").strip()
                if not title or not content:
                    results.append(
                        {"success": False, "doc_id": d.doc_id, "error": "title 与 content 不能为空"}
                    )
                    continue
                doc_id = (d.doc_id or "").strip() or str(uuid.uuid4())
                doc_type = (d.doc_type or "").strip() or "medical_kb"
                text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()
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
                        {"success": True, "doc_id": doc_id, "inserted_chunks": int(inserted or 0)}
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append({"success": False, "doc_id": doc_id, "error": str(e)})

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
            raise HTTPException(status_code=400, detail="global_kb=false时必须提供user_id")

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
                raise HTTPException(status_code=500, detail=f"删除知识库文档失败: {e}")

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
                raise HTTPException(status_code=500, detail=f"删除知识库文档失败: {e}")

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
    return {"status": "healthy", "timestamp": datetime.now()}


@app.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            return DashboardStats()

        health_records_count = 0
        medication_count = 0
        summary_count = 0

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(
                        "SELECT COUNT(1) FROM health_records WHERE user_id = %s",
                        (uid,),
                    )
                    row = cursor.fetchone()
                    health_records_count = int(row[0] or 0) if row else 0
                except Exception:
                    health_records_count = 0

                try:
                    cursor.execute(
                        "SELECT COUNT(1) FROM visit_summaries WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0",
                        (uid,),
                    )
                    row = cursor.fetchone()
                    summary_count = int(row[0] or 0) if row else 0
                except Exception:
                    summary_count = 0

                try:
                    cursor.execute(
                        "SELECT COUNT(1) FROM user_medications WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0",
                        (uid,),
                    )
                    row = cursor.fetchone()
                    medication_count = int(row[0] or 0) if row else 0
                except Exception:
                    medication_count = 0

        recent_raw = await get_dashboard_recent_activities(limit=10, user_id=uid, request=request)  # type: ignore[arg-type]
        activities: List[DashboardActivity] = []
        try:
            for item in recent_raw or []:
                activities.append(
                    DashboardActivity(
                        id=str(item.get("id") or ""),
                        title=str(item.get("title") or ""),
                        time=str(item.get("time") or ""),
                        icon=str(item.get("icon") or ""),
                    )
                )
        except Exception:
            activities = []

        return DashboardStats(
            health_records_count=health_records_count,
            medication_count=medication_count,
            summary_count=summary_count,
            recent_activities=activities,
        )
    except Exception as e:
        logger.error(f"获取仪表板统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/visit-summaries/count")
async def get_visit_summary_count(
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            return {"count": 0}

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(1) FROM visit_summaries WHERE user_id = %s",
                    (uid,),
                )
                row = cursor.fetchone()
                count = int(row[0] or 0) if row else 0
        return {"count": count}
    except Exception as e:
        logger.error(f"获取就诊摘要数量失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/recent-activities")
async def get_dashboard_recent_activities(
    limit: int = Query(10, ge=1, le=50),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    def _format_time(dt: Any) -> str:
        if not dt:
            return ""
        if isinstance(dt, str):
            return dt[:16].replace("T", " ")
        try:
            if hasattr(dt, "astimezone"):
                dt_local = dt.astimezone()
            else:
                dt_local = dt
            now_local = datetime.now(dt_local.tzinfo) if getattr(dt_local, "tzinfo", None) else datetime.now()
            if dt_local.date() == now_local.date():
                return f"今天 {dt_local.strftime('%H:%M')}"
            if dt_local.date() == (now_local.date() - timedelta(days=1)):
                return f"昨天 {dt_local.strftime('%H:%M')}"
            return dt_local.strftime("%m-%d %H:%M")
        except Exception:
            try:
                return str(dt)
            except Exception:
                return ""

    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            return []

        activities: list[dict[str, Any]] = []

        def _to_sort_ts(v: Any) -> float:
            if not v:
                return 0.0
            if isinstance(v, datetime):
                try:
                    return float(v.timestamp())
                except Exception:
                    return 0.0
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return 0.0
                try:
                    return float(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
                except Exception:
                    try:
                        return float(datetime.fromisoformat(s.replace("T", " ").replace("Z", "+00:00")).timestamp())
                    except Exception:
                        return 0.0
            try:
                return float(v)
            except Exception:
                return 0.0

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                try:
                    cursor.execute(
                        """
                        SELECT id, record_type, title, created_at
                        FROM health_records
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        activities.append(
                            {
                                "id": f"health_record:{r.get('id')}",
                                "title": "新增健康档案",
                                "time": _format_time(r.get("created_at")),
                                "icon": "📋",
                                "_ts": r.get("created_at"),
                            }
                        )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        """
                        SELECT id, created_at
                        FROM visit_summaries
                        WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        activities.append(
                            {
                                "id": f"visit_summary:{r.get('id')}",
                                "title": "生成就诊摘要",
                                "time": _format_time(r.get("created_at")),
                                "icon": "📝",
                                "_ts": r.get("created_at"),
                            }
                        )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        """
                        SELECT id, created_at
                        FROM user_medications
                        WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        activities.append(
                            {
                                "id": f"medication:{r.get('id')}",
                                "title": "新增用药记录",
                                "time": _format_time(r.get("created_at")),
                                "icon": "💊",
                                "_ts": r.get("created_at"),
                            }
                        )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        """
                        SELECT reminder_id, scheduled_time, completion_time, status
                        FROM reminder_logs
                        WHERE user_id = %s
                        ORDER BY COALESCE(completion_time, created_at, scheduled_time) DESC NULLS LAST
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        status = str(r.get("status") or "").lower()
                        if status in ("completed", "taken"):
                            title = "完成服药"
                            icon = "✅"
                        elif status in ("missed", "skipped"):
                            title = "标记跳过用药"
                            icon = "⏭️"
                        else:
                            title = "用药记录"
                            icon = "💊"

                        ts = r.get("completion_time") or r.get("scheduled_time")
                        activities.append(
                            {
                                "id": f"reminder_log:{r.get('reminder_id')}:{r.get('scheduled_time')}",
                                "title": title,
                                "time": _format_time(ts),
                                "icon": icon,
                                "_ts": ts,
                            }
                        )
                except Exception:
                    pass

        uniq: dict[str, dict[str, Any]] = {}
        for a in activities:
            aid = str(a.get("id") or "")
            if not aid:
                continue
            uniq[aid] = a

        merged = list(uniq.values())
        merged.sort(key=lambda x: _to_sort_ts(x.get("_ts")), reverse=True)
        for a in merged:
            a.pop("_ts", None)
        return merged[: int(limit)]
    except Exception as e:
        logger.error(f"获取最近活动失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/visit-summaries/history", response_model=List[VisitSummary])
async def get_visit_summaries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """获取就诊摘要历史"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            # 如果没有用户ID，返回空列表而不是报错，或者可以抛出401
            return []

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM visit_summaries 
                    WHERE user_id = %s 
                    ORDER BY visit_date DESC NULLS LAST, created_at DESC 
                    LIMIT %s OFFSET %s
                    """,
                    (uid, limit, skip),
                )
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    for k in list(row.keys()):
                        row[k] = _sanitize_json_value(row.get(k))
                    # Handle JSONB fields
                    for field in ["files", "tests"]:
                        if isinstance(row.get(field), str):
                            try:
                                row[field] = json.loads(row[field])
                            except:
                                row[field] = []
                        elif row.get(field) is None:
                            row[field] = []
                    if not (row.get("diagnosis") or "").strip():
                        for src in (row.get("summary_content"), row.get("notes")):
                            s = (src or "").strip()
                            if not s:
                                continue
                            m = re.search(
                                r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,80})",
                                s,
                            )
                            if m:
                                v = (m.group(1) or "").strip()
                                if v:
                                    row["diagnosis"] = v
                                    break
                    if not (row.get("hospital") or "").strip():
                        for src in (row.get("summary_content"), row.get("notes")):
                            s = (src or "").strip()
                            if not s:
                                continue
                            m = re.search(
                                r"(?:医院|医疗机构名称|医疗机构|机构名称)\s*[:：]?\s*([^\n；;。]{2,80})",
                                s,
                            )
                            if m:
                                v = (m.group(1) or "").strip()
                                if v:
                                    row["hospital"] = v
                                    break
                    results.append(VisitSummary(**row))
                return results
    except Exception as e:
        logger.error(f"获取就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/visit-summaries/{summary_id}", response_model=VisitSummary)
async def get_visit_summary_detail(
    summary_id: str,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM visit_summaries WHERE id = %s AND user_id = %s",
                    (summary_id, uid),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="就诊摘要不存在或无权访问")

                for k in list(row.keys()):
                    row[k] = _sanitize_json_value(row.get(k))

                for field in ["files", "tests"]:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except Exception:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []

                if not (row.get("diagnosis") or "").strip():
                    for src in (row.get("summary_content"), row.get("notes")):
                        s = (src or "").strip()
                        if not s:
                            continue
                        m = re.search(
                            r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,80})",
                            s,
                        )
                        if m:
                            v = (m.group(1) or "").strip()
                            if v:
                                row["diagnosis"] = v
                                break

                if not (row.get("hospital") or "").strip():
                    for src in (row.get("summary_content"), row.get("notes")):
                        s = (src or "").strip()
                        if not s:
                            continue
                        m = re.search(
                            r"(?:医院|医疗机构名称|医疗机构|机构名称)\s*[:：]?\s*([^\n；;。]{2,80})",
                            s,
                        )
                        if m:
                            v = (m.group(1) or "").strip()
                            if v:
                                row["hospital"] = v
                                break

                return VisitSummary(**row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取就诊摘要详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/visit-summaries/create", response_model=VisitSummary)
async def create_visit_summary(
    summary: VisitSummaryCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """创建新的就诊摘要"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                new_id = summary.summary_id or generate_id()
                now = datetime.now()
                title = (summary.title or "").strip() or "就诊摘要"
                summary_content_val = (summary.summary_content or "").strip() or None
                notes = summary.notes
                if (not notes) and summary_content_val:
                    notes = summary_content_val

                cursor.execute(
                    "SELECT id FROM visit_summaries WHERE id = %s", (new_id,)
                )
                if cursor.fetchone():
                    raise HTTPException(status_code=400, detail="摘要ID已存在")

                cursor.execute(
                    """
                    INSERT INTO visit_summaries (
                        id, user_id, title, visit_date, doctor, hospital, department,
                        chief_complaint, symptoms, examination, diagnosis, treatment,
                        prescription, follow_up, summary_content, notes, files, tests, is_deleted,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s
                    ) RETURNING id
                    """,
                    (
                        new_id,
                        uid,
                        title,
                        summary.visit_date,
                        summary.doctor,
                        summary.hospital,
                        summary.department,
                        summary.chief_complaint,
                        summary.symptoms,
                        summary.examination,
                        summary.diagnosis,
                        summary.treatment,
                        summary.prescription,
                        summary.follow_up,
                        summary_content_val,
                        notes,
                        Json(summary.files or []),
                        Json(summary.tests or []),
                        0,
                        now,
                        now,
                    ),
                )
                new_id = cursor.fetchone()["id"]
                conn.commit()

                # Fetch back the created record
                cursor.execute("SELECT * FROM visit_summaries WHERE id = %s", (new_id,))
                row = cursor.fetchone()

                # Handle JSONB fields
                for field in ["files", "tests"]:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []

                try:
                    text = "\n".join(
                        [
                            f"标题: {row.get('title') or ''}",
                            f"就诊日期: {row.get('visit_date') or ''}",
                            f"医院: {row.get('hospital') or ''}",
                            f"科室: {row.get('department') or ''}",
                            f"医生: {row.get('doctor') or ''}",
                            f"主诉: {row.get('chief_complaint') or ''}",
                            f"症状: {row.get('symptoms') or ''}",
                            f"检查: {row.get('examination') or ''}",
                            f"诊断: {row.get('diagnosis') or ''}",
                            f"治疗: {row.get('treatment') or ''}",
                            f"处方: {row.get('prescription') or ''}",
                            f"复查/随访: {row.get('follow_up') or ''}",
                            f"摘要: {row.get('summary_content') or ''}",
                            f"备注: {row.get('notes') or ''}",
                        ]
                    ).strip()
                    _upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type="visit_summaries",
                        source_id=str(row.get("id")),
                        record_type="visit_summary",
                        title=row.get("title"),
                        text=text,
                    )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    logger.warning(f"创建就诊摘要后RAG入库失败：{e}")

                return VisitSummary(**row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_date_str(s: str) -> date | None:
    try:
        v = (s or "").strip()
        if not v:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(v, fmt).date()
            except Exception:
                pass
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", v)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(y, mo, d)
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", v)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(y, mo, d)
        return None
    except Exception:
        return None


def _extract_visit_summary_fields(ocr_text: str) -> dict[str, Any]:
    text = (ocr_text or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]
    joined = "\n".join(lines)

    def first_line_with(substr: str) -> str | None:
        for ln in lines:
            if substr in ln:
                return ln
        return None

    def match_after(labels: list[str]) -> str | None:
        for i, ln in enumerate(lines):
            for lab in labels:
                if lab not in ln:
                    continue
                m = re.search(rf"{re.escape(lab)}\s*[:：]?\s*(.+)$", ln)
                if m:
                    v = m.group(1).strip()
                    if v:
                        return v
                if re.search(rf"{re.escape(lab)}\s*[:：]?\s*$", ln) and i + 1 < len(
                    lines
                ):
                    v2 = (lines[i + 1] or "").strip()
                    if v2:
                        return v2
        return None

    visit_date = None
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", joined)
    if m:
        try:
            visit_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            visit_date = None
    if not visit_date:
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", joined)
        if m:
            try:
                visit_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except Exception:
                visit_date = None

    hospital = match_after(
        ["医院", "医疗机构", "医疗机构名称", "机构名称"]
    ) or first_line_with("医院")
    department = match_after(
        ["科室", "就诊科室", "门诊科室", "就诊科别", "病区"]
    ) or first_line_with("科室")
    doctor = match_after(["医生", "医师", "主治医师"])

    chief_complaint = match_after(["主诉"])
    symptoms = match_after(["症状", "现病史", "病史"])
    examination = match_after(["检查", "化验", "检验结果", "检查结果"])
    diagnosis = match_after(
        [
            "诊断",
            "临床诊断",
            "诊断意见",
            "初步诊断",
            "诊断印象",
            "印象",
            "入院诊断",
            "出院诊断",
        ]
    )
    treatment = match_after(["治疗", "处理", "处置"])
    follow_up = match_after(["复查", "随访"])
    notes = match_after(["医嘱", "注意事项", "备注"])

    prescription_lines: list[str] = []
    rx_keywords = [
        "处方",
        "用法",
        "用量",
        "每日",
        "每次",
        "mg",
        "g",
        "ml",
        "片",
        "粒",
        "胶囊",
        "bid",
        "tid",
        "qd",
        "q12h",
    ]
    for ln in lines:
        if any(k.lower() in ln.lower() for k in rx_keywords):
            prescription_lines.append(ln)
    if len(prescription_lines) > 15:
        prescription_lines = prescription_lines[:15]
    prescription = "\n".join(prescription_lines).strip() or None

    return {
        "visit_date": visit_date,
        "hospital": hospital,
        "department": department,
        "doctor": doctor,
        "chief_complaint": chief_complaint,
        "symptoms": symptoms,
        "examination": examination,
        "diagnosis": diagnosis,
        "treatment": treatment,
        "prescription": prescription,
        "follow_up": follow_up,
        "notes": notes,
    }


_VISIT_SUMMARY_BATCHES: dict[str, dict[str, Any]] = {}


class VisitSummaryBatchCompleteRequest(BaseModel):
    batch_id: str = Field(..., min_length=4)
    visit_date: Optional[str] = None


def _prune_visit_summary_batches() -> None:
    ttl_seconds = int(os.getenv("VISIT_SUMMARY_BATCH_TTL_SECONDS", "3600"))
    now_ts = time.time()
    for bid, b in list(_VISIT_SUMMARY_BATCHES.items()):
        try:
            created = float(b.get("created_ts") or 0.0)
        except Exception:
            created = 0.0
        if created <= 0:
            _VISIT_SUMMARY_BATCHES.pop(bid, None)
            continue
        if now_ts - created > ttl_seconds:
            _VISIT_SUMMARY_BATCHES.pop(bid, None)


def _merge_visit_summary_fields(items: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "visit_date": None,
        "hospital": None,
        "department": None,
        "doctor": None,
        "chief_complaint": None,
        "symptoms": None,
        "examination": None,
        "diagnosis": None,
        "treatment": None,
        "prescription": None,
        "follow_up": None,
        "notes": None,
    }

    def first_non_empty(key: str) -> None:
        if merged.get(key):
            return
        for it in items:
            v = (it.get(key) if isinstance(it, dict) else None) or None
            if isinstance(v, str) and not v.strip():
                v = None
            if v:
                merged[key] = v
                return

    for k in ["hospital", "department", "doctor", "chief_complaint", "symptoms", "treatment", "follow_up"]:
        first_non_empty(k)

    for it in items:
        vd = it.get("visit_date") if isinstance(it, dict) else None
        if isinstance(vd, date):
            merged["visit_date"] = vd
            break

    def merge_text(key: str, sep: str = "\n") -> None:
        parts: list[str] = []
        for it in items:
            v = it.get(key) if isinstance(it, dict) else None
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        if not parts:
            return
        uniq: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        merged[key] = sep.join(uniq).strip()

    merge_text("examination")
    merge_text("diagnosis", sep="；")
    merge_text("prescription")
    merge_text("notes", sep="\n\n")
    return merged


async def _process_visit_summary_batch_item_ocr(
    batch_id: str,
    user_id: str,
    file_id: str,
    file_path: str,
    mime_type: str,
    original_filename: str,
) -> None:
    try:
        p = Path(file_path)
        file_bytes = await anyio.to_thread.run_sync(p.read_bytes)
        if not file_bytes:
            raise ValueError("empty file")

        if not extract_text_from_image:
            raise ValueError("ocr tool missing")

        b64 = base64.b64encode(file_bytes).decode("utf-8")
        raw_ocr = await anyio.to_thread.run_sync(
            lambda: (
                extract_text_from_image.fn(b64)
                if hasattr(extract_text_from_image, "fn")
                else extract_text_from_image(b64)
            )
        )
        if isinstance(raw_ocr, str):
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
            if raw_ocr.startswith(ocr_err_prefixes):
                raise ValueError(raw_ocr[:200])
        ocr_text = _normalize_ocr_text(raw_ocr)
        extracted = _extract_visit_summary_fields(ocr_text) if ocr_text.strip() else {}

        batch = _VISIT_SUMMARY_BATCHES.get(batch_id)
        if not isinstance(batch, dict) or batch.get("user_id") != user_id:
            return
        items = batch.get("items")
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("file_id") or "") != str(file_id):
                continue
            it["ocr_text"] = ocr_text
            it["extracted"] = extracted
            it["ocr_status"] = "done"
            it.pop("ocr_error", None)
            break
    except Exception as e:
        batch = _VISIT_SUMMARY_BATCHES.get(batch_id)
        if not isinstance(batch, dict) or batch.get("user_id") != user_id:
            return
        items = batch.get("items")
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("file_id") or "") != str(file_id):
                continue
            it["ocr_status"] = "failed"
            it["ocr_error"] = str(e)[:300]
            break


async def _finalize_visit_summary_batch(
    summary_id: str,
    user_id: str,
    batch_id: str,
    visit_date_override: date | None,
) -> None:
    started = datetime.now()
    batch = _VISIT_SUMMARY_BATCHES.get(batch_id)
    try:
        if not isinstance(batch, dict) or batch.get("user_id") != user_id:
            raise ValueError("batch missing")

        tasks_map = batch.get("tasks")
        tasks = list(tasks_map.values()) if isinstance(tasks_map, dict) else []
        timeout_sec = float(os.getenv("VISIT_SUMMARY_BATCH_PROCESS_TIMEOUT_SECONDS", "900"))
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                raise ValueError("batch processing timeout")

        items = batch.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("empty batch")

        file_ids: list[str] = []
        ocr_texts: list[str] = []
        extracted_list: list[dict[str, Any]] = []
        ocr_failed = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            fid = str(it.get("file_id") or "").strip()
            if fid:
                file_ids.append(fid)
            if str(it.get("ocr_status") or "") == "failed":
                ocr_failed += 1
            txt = str(it.get("ocr_text") or "")
            if txt.strip():
                ocr_texts.append(txt.strip())
            ext = it.get("extracted")
            if isinstance(ext, dict):
                extracted_list.append(ext)

        if not ocr_texts:
            raise ValueError("no ocr text")

        extracted_merged = _merge_visit_summary_fields(extracted_list)
        if visit_date_override:
            extracted_merged["visit_date"] = visit_date_override

        combined_text = "\n\n".join(ocr_texts).strip()
        agent_summary_text, agent_fields, agent_raw = _try_generate_visit_summary_with_agent_multi(
            ocr_texts
        )
        llm_summary = await _maybe_llm_summary(combined_text, extracted_merged)
        summary_content = (
            llm_summary
            or agent_summary_text
            or _generate_ai_summary(combined_text, extracted_merged)
        )

        diagnosis_val = extracted_merged.get("diagnosis")
        if (not diagnosis_val) and isinstance(agent_fields, dict):
            diagnosis_val = agent_fields.get("diagnosis") or diagnosis_val
        extracted_merged["diagnosis"] = diagnosis_val

        prescription_val = extracted_merged.get("prescription")
        if (not prescription_val) and isinstance(agent_fields, dict):
            med_names = agent_fields.get("medication_names")
            if isinstance(med_names, list) and med_names:
                prescription_val = "；".join(
                    [str(x).strip() for x in med_names if str(x).strip()]
                )
        if prescription_val:
            extracted_merged["prescription"] = prescription_val

        notes_val = extracted_merged.get("notes")
        if summary_content:
            if notes_val:
                notes_val = f"{notes_val}\n\n{summary_content}"
            else:
                notes_val = summary_content
        summary_content = _sanitize_text_value(summary_content)
        notes_val = _sanitize_text_value(notes_val)
        agent_raw = _ensure_jsonable(agent_raw)

        cleaned_fields = {
            "doctor": _sanitize_text_value(extracted_merged.get("doctor")),
            "hospital": _sanitize_text_value(extracted_merged.get("hospital")),
            "department": _sanitize_text_value(extracted_merged.get("department")),
            "chief_complaint": _sanitize_text_value(extracted_merged.get("chief_complaint")),
            "symptoms": _sanitize_text_value(extracted_merged.get("symptoms")),
            "examination": _sanitize_text_value(extracted_merged.get("examination")),
            "diagnosis": _sanitize_text_value(diagnosis_val),
            "treatment": _sanitize_text_value(extracted_merged.get("treatment")),
            "prescription": _sanitize_text_value(extracted_merged.get("prescription")),
            "follow_up": _sanitize_text_value(extracted_merged.get("follow_up")),
        }

        tests_val: list[dict[str, Any]] = []
        tests_val.append(
            {
                "type": "batch",
                "data": {
                    "batch_id": batch_id,
                    "total": len(file_ids),
                    "ocr_failed": int(ocr_failed),
                    "started_at": started.isoformat(),
                    "completed_at": datetime.now().isoformat(),
                },
            }
        )
        if agent_raw:
            tests_val.append({"type": "agent_summary", "data": agent_raw})

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    UPDATE visit_summaries
                    SET
                        visit_date = %s,
                        doctor = %s,
                        hospital = %s,
                        department = %s,
                        chief_complaint = %s,
                        symptoms = %s,
                        examination = %s,
                        diagnosis = %s,
                        treatment = %s,
                        prescription = %s,
                        follow_up = %s,
                        summary_content = %s,
                        notes = %s,
                        tests = %s,
                        status = %s,
                        error_message = NULL,
                        updated_at = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        extracted_merged.get("visit_date"),
                        cleaned_fields["doctor"],
                        cleaned_fields["hospital"],
                        cleaned_fields["department"],
                        cleaned_fields["chief_complaint"],
                        cleaned_fields["symptoms"],
                        cleaned_fields["examination"],
                        cleaned_fields["diagnosis"],
                        cleaned_fields["treatment"],
                        cleaned_fields["prescription"],
                        cleaned_fields["follow_up"],
                        summary_content,
                        notes_val,
                        Json(tests_val),
                        "done",
                        datetime.now(),
                        summary_id,
                        user_id,
                    ),
                )
                conn.commit()
    except Exception as e:
        try:
            with get_db_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        UPDATE visit_summaries
                        SET status = %s, error_message = %s, updated_at = %s
                        WHERE id = %s AND user_id = %s
                        """,
                        ("failed", str(e)[:800], datetime.now(), summary_id, user_id),
                    )
                    conn.commit()
        except Exception:
            pass
    finally:
        _VISIT_SUMMARY_BATCHES.pop(batch_id, None)


@app.post("/api/visit-summaries/analyze-image", response_model=VisitSummary)
async def analyze_visit_summary_image(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    visit_date: str = Form(None),
    request: Request = None,
):
    limiter = _get_upload_limiter()
    await limiter.acquire()
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        ct = (getattr(file, "content_type", None) or "").strip().lower()
        if not ct.startswith("image/"):
            raise HTTPException(status_code=400, detail="仅支持图片上传")

        file_id = generate_id()
        ext = Path(file.filename or "").suffix
        saved_name = f"{file_id}{ext}"
        saved_path = UPLOAD_DIR / saved_name

        max_size = 10 * 1024 * 1024
        chunk_size = int(
            os.getenv("HEALTH_RECORDS_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        content_buf = bytearray()
        try:
            with open(saved_path, "wb") as out:
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
                            os.remove(saved_path)
                        except Exception:
                            pass
                        raise HTTPException(
                            status_code=400, detail="文件大小超过限制（10MB）"
                        )
                    await anyio.to_thread.run_sync(out.write, chunk)
                    content_buf.extend(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        content = bytes(content_buf)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO file_attachments (id, record_id, filename, original_filename, file_path, file_size, mime_type)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        saved_name,
                        file.filename or saved_name,
                        str(saved_path),
                        file_size,
                        ct,
                    ),
                )
                conn.commit()

        if not extract_text_from_image:
            raise HTTPException(status_code=503, detail="OCR模块未加载，无法识别图片")

        b64 = base64.b64encode(content).decode("utf-8")
        raw_ocr = (
            extract_text_from_image.fn(b64)
            if hasattr(extract_text_from_image, "fn")
            else extract_text_from_image(b64)
        )
        if isinstance(raw_ocr, str):
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
            if raw_ocr.startswith(ocr_err_prefixes):
                raise HTTPException(status_code=503, detail=raw_ocr[:800])
        ocr_text = _normalize_ocr_text(raw_ocr)
        if not ocr_text.strip():
            raise HTTPException(status_code=422, detail="OCR识别结果为空")

        extracted = _extract_visit_summary_fields(ocr_text)
        vd_override = (
            _parse_date_str(visit_date) if isinstance(visit_date, str) else None
        )
        if vd_override:
            extracted["visit_date"] = vd_override

        summary_id = generate_id()
        summary_title = f"就诊记录OCR - {(file.filename or '').strip() or 'image'}"
        agent_summary_text, agent_fields, agent_raw = (
            _try_generate_visit_summary_with_agent(ocr_text)
        )
        llm_summary = await _maybe_llm_summary(ocr_text, extracted)
        summary_content = (
            llm_summary
            or agent_summary_text
            or _generate_ai_summary(ocr_text, extracted)
        )
        diagnosis_val = extracted.get("diagnosis")
        if (not diagnosis_val) and isinstance(agent_fields, dict):
            diagnosis_val = agent_fields.get("diagnosis") or diagnosis_val
        if not diagnosis_val:
            for src in (summary_content, ocr_text):
                s = (src or "").strip()
                if not s:
                    continue
                m = re.search(
                    r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,80})",
                    s,
                )
                if m:
                    v = (m.group(1) or "").strip()
                    if v:
                        diagnosis_val = v
                        break
        extracted["diagnosis"] = diagnosis_val

        prescription_val = extracted.get("prescription")
        if (not prescription_val) and isinstance(agent_fields, dict):
            med_names = agent_fields.get("medication_names")
            if isinstance(med_names, list) and med_names:
                prescription_val = "；".join(
                    [str(x).strip() for x in med_names if str(x).strip()]
                )
        if prescription_val:
            extracted["prescription"] = prescription_val
        notes_val = extracted.get("notes")
        if summary_content:
            if notes_val:
                notes_val = f"{notes_val}\n\n{summary_content}"
            else:
                notes_val = summary_content
        summary_content = _sanitize_text_value(summary_content)
        notes_val = _sanitize_text_value(notes_val)
        agent_raw = _ensure_jsonable(agent_raw)
        cleaned_fields = {
            "doctor": _sanitize_text_value(extracted.get("doctor")),
            "hospital": _sanitize_text_value(extracted.get("hospital")),
            "department": _sanitize_text_value(extracted.get("department")),
            "chief_complaint": _sanitize_text_value(extracted.get("chief_complaint")),
            "symptoms": _sanitize_text_value(extracted.get("symptoms")),
            "examination": _sanitize_text_value(extracted.get("examination")),
            "diagnosis": _sanitize_text_value(diagnosis_val),
            "treatment": _sanitize_text_value(extracted.get("treatment")),
            "prescription": _sanitize_text_value(extracted.get("prescription")),
            "follow_up": _sanitize_text_value(extracted.get("follow_up")),
        }

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    INSERT INTO visit_summaries (
                        id, user_id, title, visit_date, doctor, hospital, department,
                        chief_complaint, symptoms, examination, diagnosis, treatment,
                        prescription, follow_up, summary_content, notes, files, tests, is_deleted,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s
                    ) RETURNING id
                    """,
                    (
                        summary_id,
                        uid,
                        summary_title,
                        extracted.get("visit_date"),
                        cleaned_fields["doctor"],
                        cleaned_fields["hospital"],
                        cleaned_fields["department"],
                        cleaned_fields["chief_complaint"],
                        cleaned_fields["symptoms"],
                        cleaned_fields["examination"],
                        cleaned_fields["diagnosis"],
                        cleaned_fields["treatment"],
                        cleaned_fields["prescription"],
                        cleaned_fields["follow_up"],
                        summary_content,
                        notes_val,
                        Json([file_id]),
                        Json(
                            [{"type": "agent_summary", "data": agent_raw}]
                            if agent_raw
                            else []
                        ),
                        0,
                        datetime.now(),
                        datetime.now(),
                    ),
                )
                new_id = cursor.fetchone()["id"]
                conn.commit()
                cursor.execute("SELECT * FROM visit_summaries WHERE id = %s", (new_id,))
                row = cursor.fetchone()

        for k in list(row.keys()):
            row[k] = _sanitize_json_value(row.get(k))
        for field in ["files", "tests"]:
            if isinstance(row.get(field), str):
                try:
                    row[field] = json.loads(row[field])
                except Exception:
                    row[field] = []
            elif row.get(field) is None:
                row[field] = []

        return VisitSummary(**row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"就诊摘要图片识别失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        limiter.release()


@app.post("/api/visit-summaries/batch/collect-image")
async def collect_visit_summary_image(
    file: UploadFile = File(...),
    batch_id: str = Form(...),
    user_id: str = Form(None),
    request: Request = None,
):
    limiter = _get_upload_limiter()
    await limiter.acquire()
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        bid = (batch_id or "").strip()
        if len(bid) < 4:
            raise HTTPException(status_code=400, detail="batch_id 无效")

        ct = (getattr(file, "content_type", None) or "").strip().lower()
        if not ct.startswith("image/"):
            raise HTTPException(status_code=400, detail="仅支持图片上传")

        file_id = generate_id()
        ext = Path(file.filename or "").suffix
        saved_name = f"{file_id}{ext}"
        saved_path = UPLOAD_DIR / saved_name

        max_size = 10 * 1024 * 1024
        chunk_size = int(
            os.getenv("HEALTH_RECORDS_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        try:
            with open(saved_path, "wb") as out:
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
                            os.remove(saved_path)
                        except Exception:
                            pass
                        raise HTTPException(
                            status_code=400, detail="文件大小超过限制（10MB）"
                        )
                    await anyio.to_thread.run_sync(out.write, chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO file_attachments (id, record_id, filename, original_filename, file_path, file_size, mime_type)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        saved_name,
                        file.filename or saved_name,
                        str(saved_path),
                        file_size,
                        ct,
                    ),
                )
                conn.commit()

        _prune_visit_summary_batches()
        batch = _VISIT_SUMMARY_BATCHES.get(bid)
        if not batch:
            batch = {
                "user_id": uid,
                "created_ts": time.time(),
                "items": [],
                "tasks": {},
            }
            _VISIT_SUMMARY_BATCHES[bid] = batch
        if batch.get("user_id") != uid:
            raise HTTPException(status_code=403, detail="batch_id 不属于当前用户")

        batch_items = batch.get("items")
        if not isinstance(batch_items, list):
            batch_items = []
            batch["items"] = batch_items
        tasks_map = batch.get("tasks")
        if not isinstance(tasks_map, dict):
            tasks_map = {}
            batch["tasks"] = tasks_map
        batch_items.append(
            {
                "file_id": str(file_id),
                "original_filename": (file.filename or saved_name),
                "file_path": str(saved_path),
                "mime_type": ct,
                "ocr_status": "pending",
            }
        )
        tasks_map[str(file_id)] = asyncio.create_task(
            _process_visit_summary_batch_item_ocr(
                batch_id=bid,
                user_id=uid,
                file_id=str(file_id),
                file_path=str(saved_path),
                mime_type=ct,
                original_filename=(file.filename or saved_name),
            )
        )

        return {
            "batch_id": bid,
            "count": len(batch_items),
            "file_id": str(file_id),
        }
    finally:
        limiter.release()


@app.post("/api/visit-summaries/batch/complete", response_model=VisitSummary)
async def complete_visit_summary_batch(
    payload: VisitSummaryBatchCompleteRequest,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    uid = _resolve_user_id(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证用户")

    bid = (payload.batch_id or "").strip()
    batch = _VISIT_SUMMARY_BATCHES.get(bid)
    if not batch:
        raise HTTPException(status_code=404, detail="未找到批量任务")
    if batch.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="无权访问该批量任务")

    batch_items = batch.get("items") if isinstance(batch, dict) else None
    if not isinstance(batch_items, list) or not batch_items:
        raise HTTPException(status_code=400, detail="批量任务为空")

    vd_override = _parse_date_str(payload.visit_date) if payload.visit_date else None
    summary_id = generate_id()
    summary_title = "就诊记录批量汇总"
    file_ids: list[str] = []
    for it in batch_items:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("file_id") or "").strip()
        if fid:
            file_ids.append(fid)

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO visit_summaries (
                    id, user_id, title, visit_date, doctor, hospital, department,
                    chief_complaint, symptoms, examination, diagnosis, treatment,
                    prescription, follow_up, summary_content, notes, files, tests, is_deleted,
                    status, error_message, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                ) RETURNING id
                """,
                (
                    summary_id,
                    uid,
                    summary_title,
                    vd_override,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    Json(file_ids),
                    Json(
                        [
                            {
                                "type": "batch",
                                "data": {
                                    "batch_id": bid,
                                    "total": len(file_ids),
                                    "submitted_at": datetime.now().isoformat(),
                                },
                            }
                        ]
                    ),
                    0,
                    "processing",
                    None,
                    datetime.now(),
                    datetime.now(),
                ),
            )
            new_id = cursor.fetchone()["id"]
            conn.commit()
            cursor.execute("SELECT * FROM visit_summaries WHERE id = %s", (new_id,))
            row = cursor.fetchone()

    for k in list(row.keys()):
        row[k] = _sanitize_json_value(row.get(k))
    for field in ["files", "tests"]:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except Exception:
                row[field] = []
        elif row.get(field) is None:
            row[field] = []

    asyncio.create_task(
        _finalize_visit_summary_batch(
            summary_id=summary_id,
            user_id=uid,
            batch_id=bid,
            visit_date_override=vd_override,
        )
    )
    return VisitSummary(**row)


@app.get("/api/consultations/history", response_model=List[Consultation])
async def get_consultation_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    include_summary: bool = Query(False),
    include_health_records: bool = Query(False),
    request: Request = None,
):
    """获取健康咨询历史"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            return []

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                where_clauses = ["user_id = %s"]
                if not include_summary:
                    where_clauses.append("(tags IS NULL OR NOT (tags ? 'summary'))")
                if not include_health_records:
                    where_clauses.append(
                        "(tags IS NULL OR NOT (tags ? 'health_records'))"
                    )
                where_sql = " AND ".join(where_clauses)
                sql = f"""
                    SELECT * FROM consultations
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (uid, limit, skip))
                rows = cursor.fetchall()
                # Handle JSONB tags field
                results = []
                for row in rows:
                    if isinstance(row.get("tags"), str):
                        try:
                            row["tags"] = json.loads(row["tags"])
                        except:
                            row["tags"] = []
                    elif row.get("tags") is None:
                        row["tags"] = []
                    results.append(Consultation(**row))
                return results
    except Exception as e:
        logger.error(f"获取咨询历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/visit-summaries/update/{summary_id}", response_model=VisitSummary)
async def update_visit_summary(
    summary_id: str,
    summary: VisitSummaryCreate,
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """更新就诊摘要"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查是否存在
                cursor.execute(
                    "SELECT * FROM visit_summaries WHERE id = %s AND user_id = %s",
                    (summary_id, uid),
                )
                existing = cursor.fetchone()
                if not existing:
                    raise HTTPException(
                        status_code=404, detail="就诊摘要不存在或无权修改"
                    )

                now = datetime.now()
                update_fields = []
                params = []

                if summary.title is not None:
                    update_fields.append("title = %s")
                    params.append(summary.title)
                if summary.visit_date is not None:
                    update_fields.append("visit_date = %s")
                    params.append(summary.visit_date)
                if summary.doctor is not None:
                    update_fields.append("doctor = %s")
                    params.append(summary.doctor)
                if summary.hospital is not None:
                    update_fields.append("hospital = %s")
                    params.append(summary.hospital)
                if summary.department is not None:
                    update_fields.append("department = %s")
                    params.append(summary.department)
                if summary.chief_complaint is not None:
                    update_fields.append("chief_complaint = %s")
                    params.append(summary.chief_complaint)
                if summary.symptoms is not None:
                    update_fields.append("symptoms = %s")
                    params.append(summary.symptoms)
                if summary.examination is not None:
                    update_fields.append("examination = %s")
                    params.append(summary.examination)
                if summary.diagnosis is not None:
                    update_fields.append("diagnosis = %s")
                    params.append(summary.diagnosis)
                if summary.treatment is not None:
                    update_fields.append("treatment = %s")
                    params.append(summary.treatment)
                if summary.prescription is not None:
                    update_fields.append("prescription = %s")
                    params.append(summary.prescription)
                if summary.follow_up is not None:
                    update_fields.append("follow_up = %s")
                    params.append(summary.follow_up)
                if summary.notes is not None:
                    update_fields.append("notes = %s")
                    params.append(summary.notes)
                if summary.files is not None:
                    update_fields.append("files = %s")
                    params.append(Json(summary.files))
                if summary.tests is not None:
                    update_fields.append("tests = %s")
                    params.append(Json(summary.tests))
                if summary.summary_content is not None:
                    update_fields.append("summary_content = %s")
                    params.append(summary.summary_content)

                if not update_fields:
                    # 没有要更新的字段，直接返回原记录
                    # Handle JSONB fields for return
                    for field in ["files", "tests"]:
                        if isinstance(existing.get(field), str):
                            try:
                                existing[field] = json.loads(existing[field])
                            except:
                                existing[field] = []
                        elif existing.get(field) is None:
                            existing[field] = []
                    return VisitSummary(**existing)

                query = f"UPDATE visit_summaries SET {', '.join(update_fields)} WHERE id = %s RETURNING *"
                params.append(summary_id)

                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                conn.commit()

                # Handle JSONB fields
                for field in ["files", "tests"]:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []

                try:
                    text = "\n".join(
                        [
                            f"标题: {row.get('title') or ''}",
                            f"就诊日期: {row.get('visit_date') or ''}",
                            f"医院: {row.get('hospital') or ''}",
                            f"科室: {row.get('department') or ''}",
                            f"医生: {row.get('doctor') or ''}",
                            f"主诉: {row.get('chief_complaint') or ''}",
                            f"症状: {row.get('symptoms') or ''}",
                            f"检查: {row.get('examination') or ''}",
                            f"诊断: {row.get('diagnosis') or ''}",
                            f"治疗: {row.get('treatment') or ''}",
                            f"处方: {row.get('prescription') or ''}",
                            f"复查/随访: {row.get('follow_up') or ''}",
                            f"摘要: {row.get('summary_content') or ''}",
                            f"备注: {row.get('notes') or ''}",
                        ]
                    ).strip()
                    _upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type="visit_summaries",
                        source_id=str(row.get("id")),
                        record_type="visit_summary",
                        title=row.get("title"),
                        text=text,
                    )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    logger.warning(f"更新就诊摘要后RAG入库失败：{e}")

                return VisitSummary(**row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/visit-summaries/delete/{summary_id}")
async def delete_visit_summary(
    summary_id: str, user_id: Optional[str] = Query(None), request: Request = None
):
    """删除就诊摘要"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM visit_summaries WHERE id = %s AND user_id = %s RETURNING id",
                    (summary_id, uid),
                )
                deleted = cursor.fetchone()
                if not deleted:
                    raise HTTPException(
                        status_code=404, detail="就诊摘要不存在或无权删除"
                    )
                conn.commit()
                return {"message": "删除成功", "id": summary_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """创建新的咨询记录"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查是否存在同名ID (如果提供了)
                if consultation.consultation_id:
                    cursor.execute(
                        "SELECT id FROM consultations WHERE consultation_id = %s",
                        (consultation.consultation_id,),
                    )
                    if cursor.fetchone():
                        raise HTTPException(status_code=400, detail="咨询ID已存在")

                new_consultation_id = consultation.consultation_id or generate_id()
                now = datetime.now()

                cursor.execute(
                    """
                    INSERT INTO consultations (
                        user_id, consultation_id, session_id, question, answer, tags, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    ) RETURNING id
                    """,
                    (
                        uid,
                        new_consultation_id,
                        consultation.session_id,
                        consultation.question,
                        consultation.answer,
                        Json(consultation.tags or []),
                        now,
                    ),
                )
                new_id = cursor.fetchone()["id"]
                conn.commit()

                # Fetch back
                cursor.execute("SELECT * FROM consultations WHERE id = %s", (new_id,))
                row = cursor.fetchone()

                # Handle JSONB fields
                if isinstance(row.get("tags"), str):
                    try:
                        row["tags"] = json.loads(row["tags"])
                    except:
                        row["tags"] = []
                elif row.get("tags") is None:
                    row["tags"] = []

                return Consultation(**row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建咨询记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/consultations/delete/{consultation_id}")
async def delete_consultation(
    consultation_id: int, user_id: Optional[str] = Query(None), request: Request = None
):
    """删除咨询记录"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM consultations WHERE id = %s AND user_id = %s RETURNING id",
                    (consultation_id, uid),
                )
                deleted = cursor.fetchone()
                if not deleted:
                    raise HTTPException(
                        status_code=404, detail="咨询记录不存在或无权删除"
                    )
                conn.commit()
                return {"message": "删除成功", "id": consultation_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除咨询记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """保存咨询对话消息"""
    try:
        uid = _resolve_user_id(request, user_id)
        # 消息保存暂不强制鉴权，便于智能体回调，但建议后续加上

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                msg_id = generate_id()
                cursor.execute(
                    """
                    INSERT INTO chat_messages (id, consultation_id, role, content, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        msg_id,
                        message.consultation_id,
                        message.role,
                        message.content,
                        datetime.now(),
                    ),
                )
                conn.commit()
                return {"success": True, "id": msg_id}
    except Exception as e:
        logger.error(f"保存消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/consultations/{consultation_id}/messages")
async def get_consultation_messages(
    consultation_id: str, user_id: Optional[str] = Query(None), request: Request = None
):
    """获取咨询对话历史"""
    try:
        uid = _resolve_user_id(request, user_id)
        # 暂不强制鉴权，便于调试

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM chat_messages
                    WHERE consultation_id = %s
                    ORDER BY created_at ASC
                    """,
                    (consultation_id,),
                )
                rows = cursor.fetchall()
                return {"success": True, "messages": rows}
    except Exception as e:
        logger.error(f"获取消息历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health-records", response_model=List[HealthRecord])
async def get_health_records(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    record_type: Optional[RecordType] = Query(None, description="记录类型筛选"),
    importance: Optional[ImportanceLevel] = Query(None, description="重要性筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    request: Request = None,
):
    """获取健康档案列表（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                conditions = []
                params = []
                uid = _resolve_user_id(request, user_id)
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
                where_clause = " AND ".join(conditions) if conditions else "TRUE"
                query = f"""
                    SELECT * FROM health_records
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, skip])
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [row_to_health_record(row) for row in rows]
    except Exception as e:
        logger.error(f"获取健康档案列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health-records/{record_id}", response_model=HealthRecord)
async def get_health_record(
    record_id: str,
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    request: Request = None,
):
    """获取单个健康档案详情（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                uid = _resolve_user_id(request, user_id)
                if uid:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, uid),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s", (record_id,)
                    )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=404, detail="健康档案不存在或无权限访问"
                    )
                return row_to_health_record(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取健康档案详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/health-records", response_model=HealthRecord)
async def create_health_record(
    record: HealthRecordCreate,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    """创建健康档案（按用户隔离）"""
    try:
        # 基于附件ID的去重：如提交的 metadata.files 或顶层 files 包含已生成OCR的附件，则改为更新既有记录而非新增
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

        record_id = generate_id()
        now = datetime.now()
        uid = _resolve_user_id(request, user_id)

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                target_existing_id = None
                if file_ids:
                    placeholders = ",".join(["%s"] * len(file_ids))
                    try:
                        cursor.execute(
                            f"SELECT record_id FROM file_attachments WHERE id IN ({placeholders})",
                            tuple(file_ids),
                        )
                        existing_links = [r[0] for r in cursor.fetchall() if r and r[0]]
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
                                # 进行更新而非新增，且不覆盖已有OCR content
                                # 合并metadata（以新提交为主）
                                try:
                                    old_meta = (
                                        linked[2] if isinstance(linked[2], dict) else {}
                                    )
                                except Exception:
                                    old_meta = {}
                                new_meta = record.metadata or {}
                                merged_meta = {**(old_meta or {}), **(new_meta or {})}
                                merged_meta = _prepare_metadata_with_tests(
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
                                    Json(record.tags or []),
                                    Json(merged_meta),
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
                                return row_to_health_record(row)
                    except Exception:
                        pass

                # 正常新增
                # 追加：若提交为空内容且无文件ID，尝试与最近OCR生成的记录合并，避免重复
                try:
                    content_empty = (record.content is None) or (
                        isinstance(record.content, str) and record.content.strip() == ""
                    )
                    summary_empty = (record.summary is None) or (
                        isinstance(record.summary, str) and record.summary.strip() == ""
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
                                    md = deserialize_metadata(md)
                                if isinstance(md, dict):
                                    if (
                                        md.get("uploaded_files")
                                        or md.get("file_id")
                                        or md.get("ocr_info")
                                    ):
                                        return True
                                tags_v = r.get("tags")
                                if isinstance(tags_v, str):
                                    tags_v = deserialize_tags(tags_v)
                                return isinstance(tags_v, list) and (
                                    "ocr" in tags_v or "auto_import" in tags_v
                                )
                            except Exception:
                                return False

                        def _within_minutes(r: dict | None, minutes: int = 10) -> bool:
                            if not r:
                                return False
                            try:
                                created_at = r.get("created_at")
                                if isinstance(created_at, str):
                                    created_dt = datetime.fromisoformat(created_at)
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
                                merged_meta = {}
                                try:
                                    old_meta = recent.get("metadata")
                                    if isinstance(old_meta, str):
                                        old_meta = deserialize_metadata(old_meta)
                                    if isinstance(old_meta, dict):
                                        merged_meta.update(old_meta)
                                except Exception:
                                    pass
                                if isinstance(record.metadata, dict):
                                    merged_meta.update(record.metadata)
                                merged_meta = _prepare_metadata_with_tests(
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
                                    Json(record.tags or []),
                                    Json(merged_meta),
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
                                logger.info(
                                    f"create dedup merged into recent id={recent.get('id')} user_id={uid}"
                                )
                                return row_to_health_record(row)
                            except Exception:
                                pass
                except Exception:
                    pass

                record.metadata = _prepare_metadata_with_tests(
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
                        Json(record.tags or []),
                        Json(record.metadata or {}),
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
                created = row_to_health_record(row)

            try:
                text = _make_rag_text(created.title, created.summary, created.content)
                rt = (
                    created.record_type.value
                    if hasattr(created.record_type, "value")
                    else str(created.record_type)
                )
                _upsert_rag_document(
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
                logger.warning(f"创建记录后RAG入库失败：{e}")

            # 新增：写入HRM（PostgreSQL）以供Agent检索
            try:
                _save_to_hrm(
                    user_id=uid,
                    record_type=created.record_type,
                    title=created.title,
                    content=created.content or (created.summary or ""),
                    extracted_data=created.metadata or {},
                )
            except Exception as e:
                logger.warning(f"创建记录后HRM双写失败：{e}")

            try:
                if health_records_memory_service is not None:
                    if not health_records_memory_service.is_available():
                        await health_records_memory_service.initialize()
                    imp_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
                    imp_key = (
                        created.importance.value
                        if hasattr(created.importance, "value")
                        else str(created.importance)
                    )
                    imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                    await health_records_memory_service.store_health_record(
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
                logger.warning(f"创建记录后写入记忆失败：{e}")

            return created

    except Exception as e:
        logger.error(f"创建健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/health-records/{record_id}", response_model=HealthRecord)
async def update_health_record(
    record_id: str,
    record_update: HealthRecordUpdate,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    """更新健康档案（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查记录是否存在并属于用户
                uid = _resolve_user_id(request, user_id)
                if user_id:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, user_id),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s", (record_id,)
                    )
                existing_record = cursor.fetchone()
                if not existing_record:
                    raise HTTPException(
                        status_code=404, detail="健康档案不存在或无权限访问"
                    )

                # 构建更新字段
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
                    params.append(Json(record_update.tags))

                existing_meta = existing_record.get("metadata")
                if isinstance(existing_meta, str):
                    existing_meta = deserialize_metadata(existing_meta)
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
                            [str(x) for x in mfiles if isinstance(x, (str, int))]
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
                    prepared_meta = _prepare_metadata_with_tests(
                        content_for_extract, merged_meta
                    )
                    update_fields.append("metadata = %s")
                    params.append(Json(prepared_meta))

                if not update_fields:
                    return row_to_health_record(existing_record)

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
                        "SELECT * FROM health_records WHERE id = %s", (record_id,)
                    )
                row = cursor.fetchone()
                updated = row_to_health_record(row)

                try:
                    text = _make_rag_text(updated.title, updated.summary, updated.content)
                    rt = (
                        updated.record_type.value
                        if hasattr(updated.record_type, "value")
                        else str(updated.record_type)
                    )
                    _upsert_rag_document(
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
                    logger.warning(f"更新记录后RAG入库失败：{e}")
                try:
                    _save_to_hrm(
                        user_id=uid,
                        record_type=updated.record_type,
                        title=updated.title,
                        content=updated.content or (updated.summary or ""),
                        extracted_data=updated.metadata or {},
                    )
                except Exception as e:
                    logger.warning(f"更新记录后HRM双写失败：{e}")
                try:
                    if health_records_memory_service is not None:
                        if not health_records_memory_service.is_available():
                            await health_records_memory_service.initialize()
                        mem_id = None
                        try:
                            meta = updated.metadata or {}
                            mem_id = meta.get("memory_id")
                        except Exception:
                            mem_id = None
                        if mem_id and getattr(
                            health_records_memory_service, "memory_system", None
                        ):
                            try:
                                health_records_memory_service.memory_system.update_memory(
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
                                imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                                await health_records_memory_service.store_health_record(
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
                            await health_records_memory_service.store_health_record(
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
                    logger.warning(f"更新记录后写入记忆失败：{e}")
                return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/health-records/{record_id}")
async def delete_health_record(
    record_id: str,
    user_id: Optional[str] = Query(None, description="用户ID"),
    request: Request = None,
):
    """删除健康档案（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查记录是否存在并属于用户
                uid = _resolve_user_id(request, user_id)
                if uid:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, uid),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM health_records WHERE id = %s", (record_id,)
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
                            deserialize_metadata(r[0])
                            if r and isinstance(r[0], str)
                            else (r[0] if r else {})
                        )
                        if isinstance(meta, dict):
                            mem_id = meta.get("memory_id")
                    except Exception:
                        mem_id = None
                    if (
                        mem_id
                        and health_records_memory_service
                        and health_records_memory_service.is_available()
                    ):
                        try:
                            health_records_memory_service.memory_system.delete_memory(
                                mem_id
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                cursor.execute(
                    "DELETE FROM file_attachments WHERE record_id = %s", (record_id,)
                )
                if uid:
                    cursor.execute(
                        "DELETE FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, uid),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM health_records WHERE id = %s", (record_id,)
                    )
                conn.commit()

                return {"message": "健康档案删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health-records/statistics", response_model=HealthStatistics)
async def get_health_statistics():
    """获取健康数据统计"""
    try:
        with get_db_connection() as conn:
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

                return HealthStatistics(
                    total_records=total_records,
                    records_by_type=records_by_type,
                    records_by_importance=records_by_importance,
                    recent_records_count=recent_records_count,
                    last_updated=last_updated,
                )

    except Exception as e:
        logger.error(f"获取健康统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
                            (Json(meta_val), datetime.now(), row.get("id"), uid),
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
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")
        store: dict = {}
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
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
                        meta_val = deserialize_metadata(meta_val)
                    elif not isinstance(meta_val, dict):
                        meta_val = {}
                    meta_val = _prepare_metadata_with_tests(
                        row.get("content"), meta_val
                    )
                    extracted = _ensure_dict_value(
                        meta_val.get("extracted_info") or meta_val.get("extracted_data")
                    )
                    tests = extracted.get("test_results") or extracted.get("tests")
                    if tests:
                        _collect_test_points(
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
                        tests = _ensure_list_value(tests) or _ensure_dict_value(tests)
                    if tests:
                        _collect_test_points(
                            store,
                            tests,
                            row.get("visit_date") or row.get("created_at"),
                            "visit_summaries",
                            str(row.get("id")) if row.get("id") is not None else None,
                        )
        indicators = _finalize_indicator_items(store, include_points)
        return {"days": days, "indicators": indicators}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取健康趋势指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health-trends/indicator")
async def get_health_trend_indicator(
    name: str = Query(...),
    days: int = Query(180),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")
        store: dict = {}
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
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
                        meta_val = deserialize_metadata(meta_val)
                    elif not isinstance(meta_val, dict):
                        meta_val = {}
                    meta_val = _prepare_metadata_with_tests(
                        row.get("content"), meta_val
                    )
                    extracted = _ensure_dict_value(
                        meta_val.get("extracted_info") or meta_val.get("extracted_data")
                    )
                    tests = extracted.get("test_results") or extracted.get("tests")
                    if tests:
                        _collect_test_points(
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
                        tests = _ensure_list_value(tests) or _ensure_dict_value(tests)
                    if tests:
                        _collect_test_points(
                            store,
                            tests,
                            row.get("visit_date") or row.get("created_at"),
                            "visit_summaries",
                            str(row.get("id")) if row.get("id") is not None else None,
                        )
        indicators = _finalize_indicator_items(store, True)
        selected = None
        for item in indicators:
            if item.get("name") == name:
                selected = item
                break
        return {"days": days, "indicator": selected}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取健康趋势详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health-records/insights", response_model=HealthInsightsResponse)
async def get_health_insights(
    analysis_type: str = Query("comprehensive", description="分析类型"),
    include_recommendations: bool = Query(True, description="包含建议"),
    include_trends: bool = Query(True, description="包含趋势"),
    include_risks: bool = Query(True, description="包含风险"),
):
    """获取健康洞察"""
    try:
        # 这里是模拟的洞察数据，实际应用中应该基于真实的健康数据分析
        insights = [
            HealthInsight(
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
            HealthInsight(
                id="insight_2",
                type="recommendation",
                title="运动建议",
                summary="建议增加有氧运动频率",
                details="基于您的健康档案，建议每周进行3-4次中等强度的有氧运动，每次30-45分钟。",
                severity="medium",
                confidence=0.75,
                tags=["运动", "健康建议"],
                recommendations=["每周游泳2-3次", "每天快走30分钟", "定期进行力量训练"],
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
            {"title": "多喝水", "description": "每天至少饮用8杯水，保持身体水分平衡"},
            {"title": "规律作息", "description": "保持每天7-8小时的优质睡眠"},
            {"title": "均衡饮食", "description": "多吃蔬菜水果，减少加工食品摄入"},
        ]

        return HealthInsightsResponse(
            insights=insights, health_score=health_score, quick_tips=quick_tips
        )

    except Exception as e:
        logger.error(f"获取健康洞察失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/health-records/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    skip_ocr: str | None = Form(None),
    request: Request = None,
):
    """上传文件"""
    limiter = _get_upload_limiter()
    await limiter.acquire()
    try:
        logger.info(
            f"upload start filename={getattr(file,'filename',None)} ct={getattr(file,'content_type',None)}"
        )
        # 检查与规范化文件类型（支持 octet-stream 与扩展名推断）
        allowed_types = {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/gif",
            # 扩展前端支持的图片类型，避免前端允许而后端拒绝
            "image/webp",
            "image/bmp",
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

        # 初始类型
        incoming_ct = (getattr(file, "content_type", None) or "").strip().lower()

        # 当为通用流或未设置时，尝试依据文件名推断类型
        normalized_ct = incoming_ct
        if not normalized_ct or normalized_ct == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(file.filename or "")
            if guessed:
                normalized_ct = guessed.lower()
        # 常见扩展手动兜底
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

        # 统一 jpg 到 jpeg
        if normalized_ct == "image/jpg":
            normalized_ct = "image/jpeg"

        # 最终类型校验
        if normalized_ct not in allowed_types:
            raise HTTPException(status_code=400, detail="不支持的文件类型")

        max_size = int(
            os.getenv("HEALTH_RECORDS_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
        )

        # 解析用户ID（优先表单，其次头部/Token）
        try:
            user_id = _resolve_user_id(request, user_id)
        except Exception:
            pass

        skip_ocr_flag = str(skip_ocr or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

        # 生成文件名
        file_id = generate_id()
        file_extension = Path(file.filename).suffix
        filename = f"{file_id}{file_extension}"
        file_path = UPLOAD_DIR / filename

        chunk_size = int(os.getenv("HEALTH_RECORDS_UPLOAD_CHUNK_BYTES", str(1024 * 1024)))
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
                        raise HTTPException(status_code=400, detail="文件大小超过限制")
                    await anyio.to_thread.run_sync(out.write, chunk)
                    if content_buf is not None:
                        content_buf.extend(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        file_content = bytes(content_buf) if content_buf is not None else b""

        # 使用单个事务：先写附件，再进行图片OCR并入库；图片OCR失败则回滚并报错
        with get_db_connection() as conn:
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
                    record_id = generate_id()
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
                            RecordType.OTHER.value,
                            "已上传附件，内容待识别",
                            "",
                            ImportanceLevel.MEDIUM.value,
                            Json(tags),
                            Json(metadata),
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
                                record_id=str(record_id),
                                file_id=str(file_id),
                                user_id=str(user_id),
                                file_path=str(file_path),
                                original_filename=str(file.filename or ""),
                                mime_type=str(normalized_ct or ""),
                            )
                        )
                    except Exception as e:
                        logger.warning(f"后台OCR任务启动失败: {e}")
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
                    image_base64 = base64.b64encode(file_content).decode("utf-8")
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
                            ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch")
                            result = ocr_engine.ocr(tmp_path, cls=True)
                            lines = [line[1] for line in (result[0] if result else [])]
                            ocr_text = "\n".join([t[0] for t in lines])
                            confs = [
                                float(t[1])
                                for t in lines
                                if isinstance(t[1], (int, float))
                            ]
                            confidence = (sum(confs) / len(confs)) if confs else 0.5
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                    except Exception:
                        _used_paddle = False
                    if not ocr_text:
                        if not extract_text_from_image:
                            conn.rollback()
                            raise HTTPException(
                                status_code=503,
                                detail="OCR模块未加载，无法对图片进行识别与入库",
                            )
                        ocr_text = (
                            extract_text_from_image.fn(image_base64)
                            if hasattr(extract_text_from_image, "fn")
                            else extract_text_from_image(image_base64)
                        )
                        used_external = True
                    ocr_text = _normalize_ocr_text(ocr_text)
                    if (
                        _is_ocr_placeholder_text(ocr_text)
                        and extract_text_from_image
                        and _used_paddle
                        and not used_external
                    ):
                        ocr_text = (
                            extract_text_from_image.fn(image_base64)
                            if hasattr(extract_text_from_image, "fn")
                            else extract_text_from_image(image_base64)
                        )
                        used_external = True
                        ocr_text = _normalize_ocr_text(ocr_text)
                    if _is_ocr_placeholder_text(ocr_text):
                        conn.rollback()
                        raise HTTPException(status_code=422, detail="OCR识别结果无效")

                    if validate_medical_document:
                        try:
                            validation_json = (
                                validate_medical_document.fn(ocr_text)
                                if hasattr(validate_medical_document, "fn")
                                else validate_medical_document(ocr_text)
                            )
                            val = (
                                json.loads(validation_json)
                                if isinstance(validation_json, str)
                                else (validation_json or {})
                            )
                            document_type = val.get("document_type") or "unknown"
                            vconf = val.get("confidence")
                            if isinstance(vconf, (int, float)):
                                confidence = max(float(confidence), float(vconf))
                        except Exception as e:
                            logger.warning(f"文档验证失败，使用默认类型: {e}")
                        validation = validation_json
                    else:
                        validation = {}

                    # 结构化信息提取（集成 HealthRecordsManager 的数据提取工具）
                    extracted_info = None
                    try:
                        from HealthRecordsManager.mcpserver.data_extraction_tool import extract_medical_info as _extract_medical_info  # type: ignore
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
                            logger.warning(f"结构化提取失败: {e}")

                    try:
                        validation_data = (
                            json.loads(validation)
                            if isinstance(validation, str)
                            else validation
                        )
                    except Exception:
                        validation_data = {"raw": validation}
                    document_type = _normalize_document_type(
                        validation_data.get("document_type")
                    )
                    try:
                        confidence = float(validation_data.get("confidence", 0.5))
                    except Exception:
                        confidence = 0.5

                    # 可选的信息抽取
                    extracted_info = {}
                    if extract_medical_info:
                        try:
                            info_json = (
                                extract_medical_info.fn(ocr_text)
                                if hasattr(extract_medical_info, "fn")
                                else extract_medical_info(ocr_text)
                            )
                            extracted_info = (
                                json.loads(info_json)
                                if isinstance(info_json, str)
                                else (info_json or {})
                            )
                        except Exception as e:
                            logger.warning(f"信息抽取失败，已忽略: {e}")
                            extracted_info = {}
                    if isinstance(extracted_info, dict):
                        tests_val = extracted_info.get("test_results") or extracted_info.get("tests")
                        filtered = _filter_test_results(tests_val)
                        if filtered is not None:
                            if filtered:
                                extracted_info["test_results"] = filtered
                            else:
                                extracted_info.pop("test_results", None)
                            extracted_info.pop("tests", None)

                    # 存入记忆系统（可选，不影响事务）
                    if health_records_memory_service is not None:
                        try:
                            if not health_records_memory_service.is_available():
                                await health_records_memory_service.initialize()
                            try:
                                memory_id = await asyncio.wait_for(
                                    health_records_memory_service.store_ocr_result(
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
                                logger.warning("存储OCR结果到记忆超时，已跳过")
                                memory_id = None
                        except Exception as e:
                            logger.warning(f"存储OCR结果到记忆失败: {e}")

                    # —— 将OCR识别结果入库到健康档案，并关联附件 ——
                    # 若OCR文本为空则视为失败
                    ocr_text_str = _normalize_ocr_text(
                        ocr_text if isinstance(ocr_text, str) else str(ocr_text)
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
                    prescription_keywords = ["处方", "医嘱", "用药", "药品", "药方"]
                    surgery_keywords = ["手术", "术后", "术前", "麻醉"]
                    allergy_keywords = ["过敏", "皮试", "过敏史"]
                    vaccination_keywords = ["疫苗", "接种", "免疫"]
                    vital_keywords = ["血压", "心率", "体温", "呼吸", "身高", "体重"]

                    def has_any(text: str, kws: list[str]) -> bool:
                        return any(k in text for k in kws)

                    if doc_type_lower in {
                        "test_report",
                        "lab_result",
                        "inspection_report",
                        "检验报告",
                        "化验单",
                    } or has_any(ocr_text_str, lab_keywords):
                        record_type = RecordType.LAB_RESULT.value
                    elif doc_type_lower in {
                        "prescription",
                        "medication",
                        "处方",
                    } or has_any(ocr_text_str, prescription_keywords):
                        record_type = RecordType.PRESCRIPTION.value
                    elif has_any(ocr_text_str, surgery_keywords):
                        record_type = RecordType.SURGERY.value
                    elif doc_type_lower in {
                        "medical_record",
                        "病历",
                        "门诊记录",
                        "出院记录",
                        "入院记录",
                    }:
                        record_type = RecordType.MEDICAL_REPORT.value
                    elif has_any(ocr_text_str, allergy_keywords):
                        record_type = RecordType.ALLERGY.value
                    elif has_any(ocr_text_str, vaccination_keywords):
                        record_type = RecordType.VACCINATION.value
                    elif has_any(ocr_text_str, vital_keywords):
                        record_type = RecordType.VITAL_SIGNS.value
                    else:
                        record_type = RecordType.MEDICAL_REPORT.value

                    now = datetime.now()
                    record_id = generate_id()
                    title = f"{document_type or 'OCR文档'} - {file.filename}"
                    tags = [
                        "ocr",
                        "auto_import",
                        document_type or "unknown",
                    ]
                    # 计算文件哈希用于去重
                    try:
                        import hashlib

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
                            extracted_info if isinstance(extracted_info, dict) else {}
                        ),
                        "uploaded_files": [file_id],
                        **({"file_hash": file_hash} if file_hash else {}),
                    }

                    # 去重：同一用户相同OCR内容或文件哈希命中则复用记录并仅关联附件
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
                        if dup and (dup.get("id") if isinstance(dup, dict) else dup[0]):
                            dup_id = dup.get("id") if isinstance(dup, dict) else dup[0]
                            cursor.execute(
                                "UPDATE file_attachments SET record_id = %s WHERE id = %s",
                                (dup_id, file_id),
                            )
                            conn.commit()
                            logger.info(
                                f"upload dedup merged file_id={file_id} record_id={dup_id} user_id={user_id} hash={file_hash}"
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

                    structured_summary = _build_structured_summary(
                        metadata.get("extracted_info")
                        if isinstance(metadata, dict)
                        else None
                    )
                    if structured_summary and isinstance(metadata, dict):
                        metadata["structured_summary"] = structured_summary

                    llm_summary = None
                    try:
                        llm_summary = await _maybe_llm_summary(
                            ocr_text_str,
                            (
                                metadata.get("extracted_info")
                                if isinstance(metadata, dict)
                                else None
                            ),
                        )
                    except Exception as e:
                        logger.warning(f"调用 LLM 摘要失败: {e}")
                        llm_summary = None
                    if llm_summary is not None:
                        logger.info("使用 LLM 摘要")
                    elif structured_summary:
                        logger.info("使用结构化摘要")
                    else:
                        logger.info("使用规则摘要")
                    final_summary = (
                        llm_summary
                        or structured_summary
                        or _generate_ai_summary(
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
                            ImportanceLevel.MEDIUM.value,
                            Json(tags),
                            Json(metadata),
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

                    # 成功则提交事务
                    conn.commit()
                    logger.info(
                        f"upload insert record_id={record_id} user_id={user_id} file_id={file_id} type={record_type} summary_len={len(final_summary or '')} content_len={len(ocr_text_str or '')}"
                    )

                    # 新增：写入HRM（PostgreSQL）以供Agent检索
                    try:
                        _save_to_hrm(
                            user_id=user_id,
                            record_type=record_type,
                            title=title,
                            content=ocr_text_str,
                            extracted_data=metadata.get("extracted_info") or {},
                        )
                    except Exception as e:
                        logger.warning(f"OCR入库后HRM双写失败：{e}")
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
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            limiter.release()
        except Exception:
            pass


async def _process_pending_ocr(
    record_id: str,
    file_id: str,
    user_id: str,
    file_path: str,
    original_filename: str = "",
    mime_type: str = "",
):
    started_at = datetime.now()
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
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
                    deserialize_metadata(row["metadata"])
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
                    (Json(meta), started_at, record_id, user_id),
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
                logger.warning(f"后台OCR PaddleOCR失败: {e}")

        if (not ocr_text) and extract_text_from_image:
            image_base64 = base64.b64encode(file_bytes).decode("utf-8")
            try:
                ocr_text = await anyio.to_thread.run_sync(
                    lambda: (
                        extract_text_from_image.fn(image_base64)
                        if hasattr(extract_text_from_image, "fn")
                        else extract_text_from_image(image_base64)
                    )
                )
            except Exception as e:
                logger.warning(f"后台OCR 外部OCR失败: {e}")

        ocr_text_str = _normalize_ocr_text(
            ocr_text if isinstance(ocr_text, str) else (str(ocr_text) if ocr_text else "")
        )
        if not ocr_text_str or _is_ocr_placeholder_text(ocr_text_str):
            raise ValueError("invalid ocr result")

        if validate_medical_document:
            try:
                validation_json = await anyio.to_thread.run_sync(
                    lambda: (
                        validate_medical_document.fn(ocr_text_str)
                        if hasattr(validate_medical_document, "fn")
                        else validate_medical_document(ocr_text_str)
                    )
                )
                val = (
                    json.loads(validation_json)
                    if isinstance(validation_json, str)
                    else (validation_json or {})
                )
                document_type = _normalize_document_type(val.get("document_type"))
                vconf = val.get("confidence")
                if isinstance(vconf, (int, float)):
                    confidence = max(float(confidence), float(vconf))
            except Exception as e:
                logger.warning(f"后台OCR 文档验证失败: {e}")

        extracted_info: dict = {}
        if extract_medical_info:
            try:
                info_json = await anyio.to_thread.run_sync(
                    lambda: (
                        extract_medical_info.fn(ocr_text_str)
                        if hasattr(extract_medical_info, "fn")
                        else extract_medical_info(ocr_text_str)
                    )
                )
                extracted_info = (
                    json.loads(info_json) if isinstance(info_json, str) else (info_json or {})
                )
                if not isinstance(extracted_info, dict):
                    extracted_info = {}
            except Exception as e:
                logger.warning(f"后台OCR 信息抽取失败: {e}")
                extracted_info = {}

        tests_val = extracted_info.get("test_results") or extracted_info.get("tests")
        filtered = _filter_test_results(tests_val)
        if filtered is not None:
            if filtered:
                extracted_info["test_results"] = filtered
            else:
                extracted_info.pop("test_results", None)
            extracted_info.pop("tests", None)

        memory_id = None
        if health_records_memory_service is not None:
            try:
                if not health_records_memory_service.is_available():
                    await health_records_memory_service.initialize()
                try:
                    memory_id = await asyncio.wait_for(
                        health_records_memory_service.store_ocr_result(
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
                    logger.warning("后台OCR存储记忆超时，已跳过")
                    memory_id = None
            except Exception as e:
                logger.warning(f"后台OCR存储记忆失败: {e}")
                memory_id = None

        doc_type_lower = (document_type or "").lower()
        if doc_type_lower in {
            "test_report",
            "lab_result",
            "inspection_report",
            "检验报告",
            "化验单",
        }:
            record_type = RecordType.LAB_RESULT.value
        elif doc_type_lower in {"prescription", "medication", "处方"}:
            record_type = RecordType.PRESCRIPTION.value
        else:
            record_type = RecordType.MEDICAL_REPORT.value

        structured_summary = _build_structured_summary(extracted_info)
        llm_summary = None
        try:
            llm_summary = await _maybe_llm_summary(ocr_text_str, extracted_info)
        except Exception:
            llm_summary = None
        final_summary = llm_summary or structured_summary or _generate_ai_summary(ocr_text_str, extracted_info)

        try:
            file_hash = hashlib.sha256(file_bytes).hexdigest()
        except Exception:
            file_hash = None

        finished_at = datetime.now()
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
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
                    deserialize_metadata(row["metadata"])
                    if isinstance(row.get("metadata"), str)
                    else (row.get("metadata") or {})
                )
                if not isinstance(meta, dict):
                    meta = {}
                if not isinstance(current_tags, list):
                    current_tags = []

                new_record_type = current_record_type
                if (not current_record_type) or (current_record_type == RecordType.OTHER.value):
                    new_record_type = record_type

                ui_doc_type = str(new_record_type or "").strip().lower()
                if not ui_doc_type:
                    ui_doc_type = str(document_type or "unknown").strip().lower()

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
                title_label = doc_type_label_map.get(ui_doc_type, "") or (
                    str(document_type or "OCR文档").strip()
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
                if (not current_title) or str(current_title).startswith("附件 -"):
                    suffix = (original_filename or "").strip()
                    if suffix:
                        suffix = suffix.replace("\\", "/").split("/")[-1].strip()
                    if suffix and "." not in suffix and re.fullmatch(r"[A-Za-z0-9]{12,}", suffix):
                        suffix = ""
                    if suffix:
                        new_title = f"{title_label} - {suffix}".strip(" -")
                    else:
                        new_title = str(title_label).strip() or "健康档案"

                new_summary = current_summary
                if (not current_summary) or (str(current_summary).strip() == "已上传附件，内容待识别"):
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
                        "mime_type": meta.get("mime_type") or (mime_type or ""),
                        "uploaded_files": uploaded_files,
                        "ocr_info": {
                            "document_type": ui_doc_type,
                            "raw_document_type": str(document_type or "").strip(),
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
                        Json(tags),
                        Json(meta),
                        finished_at,
                        record_id,
                        user_id,
                    ),
                )

                try:
                    text = _make_rag_text(new_title, new_summary, new_content)
                    _upsert_rag_document(
                        cursor,
                        user_id=user_id,
                        source_type="health_records",
                        source_id=str(record_id),
                        record_type=str(new_record_type),
                        title=new_title,
                        text=text,
                    )
                except Exception as e:
                    logger.warning(f"后台OCR RAG入库失败：{e}")

                conn.commit()

        try:
            _save_to_hrm(
                user_id=user_id,
                record_type=new_record_type,
                title=new_title,
                content=new_content or (new_summary or ""),
                extracted_data=meta.get("extracted_info") or {},
            )
        except Exception as e:
            logger.warning(f"后台OCR HRM双写失败：{e}")

        try:
            if health_records_memory_service is not None:
                if not health_records_memory_service.is_available():
                    await health_records_memory_service.initialize()
                imp_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
                imp_key = row.get("importance") or "medium"
                imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                await health_records_memory_service.store_health_record(
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
            logger.warning(f"后台OCR 写入健康档案记忆失败：{e}")
    except Exception as e:
        failed_at = datetime.now()
        try:
            with get_db_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        "SELECT metadata FROM health_records WHERE id = %s AND user_id = %s",
                        (record_id, user_id),
                    )
                    row = cursor.fetchone() or {}
                    meta = (
                        deserialize_metadata(row.get("metadata"))
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
                        (Json(meta), failed_at, record_id, user_id),
                    )
                    conn.commit()
        except Exception:
            pass
        logger.warning(f"后台OCR处理失败 record_id={record_id}: {e}")


# 新增：批量上传多个文件（逐个调用单文件上传逻辑，保证返回结构一致）
@app.post("/api/health-records/upload/multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    user_id: str = Form(None),
    request: Request = None,
):
    try:
        if not files:
            raise HTTPException(status_code=400, detail="未提供文件")

        results = []
        for f in files:
            try:
                # 复用单文件上传的完整逻辑（含OCR与入库）
                res = await upload_file(file=f, user_id=user_id, request=request)
                results.append(res)
            except HTTPException as he:
                results.append(
                    {"filename": getattr(f, "filename", None), "error": he.detail}
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
        logger.error(f"批量文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 新增：将指定用户的本地SQLite健康记录同步到HRM（PostgreSQL）
@app.post("/api/health-records/sync-to-hrm")
async def sync_sqlite_to_hrm(user_id: str = Query(..., description="需要同步的用户ID")):
    try:
        synced = 0
        skipped = 0
        if not HRM_SAVE_RECORD:
            raise HTTPException(status_code=503, detail="HRM存储工具不可用，无法同步")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT id, title, record_type, summary, content, metadata FROM health_records WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,),
                )
                rows = cursor.fetchall()

            for row in rows:
                try:
                    rid = row["id"]
                    title = row["title"] or "记录"
                    rtype = row["record_type"] or "other"
                    content = row["content"] or (row["summary"] or "")
                    meta = (
                        deserialize_metadata(row["metadata"])
                        if isinstance(row["metadata"], str)
                        else (row["metadata"] or {})
                    )
                    extracted = meta.get("extracted_info") or meta

                    # 空内容的记录不同步到HRM
                    if not content or not str(content).strip():
                        skipped += 1
                        continue

                    _save_to_hrm(
                        user_id=user_id,
                        record_type=rtype,
                        title=title,
                        content=str(content),
                        extracted_data=extracted,
                    )
                    synced += 1
                except Exception as e:
                    logger.warning(f"同步单条记录失败（已跳过）: {e}")
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
        logger.error(f"健康记录同步到HRM失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 新增：获取指定记录的结构化与OCR信息（上移到启动语句之前）
@app.get("/api/health-records/{record_id}/extracted")
async def get_record_extracted_info(record_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT metadata FROM health_records WHERE id = %s", (record_id,)
                )
                row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="健康档案不存在")
            metadata = deserialize_metadata(
                row[0] if isinstance(row, tuple) else row["metadata"]
            )
            return {
                "extracted_info": metadata.get("extracted_info") or {},
                "ocr_info": metadata.get("ocr_info") or {},
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取结构化信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 新增：按 file_id 读取并以内联方式返回附件文件
@app.get("/api/health-records/files/{file_id}")
async def get_file_attachment(file_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT original_filename, file_path, mime_type FROM file_attachments WHERE id = %s",
                    (file_id,),
                )
                row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="附件不存在")
            # sqlite3.Row 支持下标与键访问
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
            # 以内联方式展示，浏览器可直接预览图片/PDF
            headers = {"Content-Disposition": f'inline; filename="{original_name}"'}
            return FileResponse(str(file_path), media_type=mime, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取附件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
