from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    UploadFile,
    File,
    Form,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
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
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
import jwt
import re

try:
    from embedding_manager import EmbeddingService
except Exception:
    EmbeddingService = None  # type: ignore

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
    from HealthRecordsManager.memory_service import health_records_memory_service
except Exception as _import_err:
    logger.warning(f"可选OCR/记忆模块加载失败，将跳过OCR与入库: {_import_err}")
    extract_text_from_image = None
    validate_medical_document = None
    extract_medical_info = None
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

_RAG_VECTOR_DIM = int(os.getenv("RAG_VECTOR_DIM", "384"))
_RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL") or os.getenv(
    "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)
_rag_schema_ready = False
_embedding_service = None

def _get_embedding_service():
    global _embedding_service
    if _embedding_service is not None:
        return _embedding_service
    if EmbeddingService is None:
        _embedding_service = None
        return _embedding_service
    try:
        _embedding_service = EmbeddingService(model_name=_RAG_EMBEDDING_MODEL)
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
            );
            """
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

    cursor.execute(
        """
        DELETE FROM rag_chunks
        WHERE source_type = %s AND source_id = %s AND embedding_model = %s
        """,
        (source_type, source_id, es.model_name),
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
            ON CONFLICT (source_type, source_id, chunk_index, embedding_model)
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
                datetime.now(),
                datetime.now(),
            ),
        )
        inserted += 1
    return inserted


@contextmanager
def get_db_connection():
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

        # 优先使用OCR正文；若OCR文本足够（>=50字），直接截断为摘要
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


def _sanitize_json_value(v: Any) -> Any:
    if isinstance(v, str) and "\x00" in v:
        return v.replace("\x00", "")
    return v


async def _maybe_llm_summary(ocr_text: str, extracted: dict | None) -> str | None:
    try:
        use_llm = str(os.getenv("USE_LLM_SUMMARY", "0")).lower() in ("1", "true", "yes")
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
            return "test_report"
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
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库并预热可选工具（OCR与记忆系统）"""
    init_database()

    # 预热：在启动阶段加载 OCR 与记忆系统，避免首次图片上传时阻塞
    try:
        # 初始化记忆系统并预热嵌入模型
        if (
            "health_records_memory_service" in globals()
            and health_records_memory_service
        ):
            try:
                await health_records_memory_service.initialize()
                ms = getattr(health_records_memory_service, "memory_system", None)
                if ms and getattr(ms, "embedding_service", None):
                    # 生成一次小样本嵌入以触发模型加载
                    try:
                        ms.embedding_service.generate_embedding("warmup for embeddings")
                        logger.info("记忆嵌入模型预热完成")
                    except Exception as e:
                        logger.warning(f"记忆嵌入模型预热异常: {e}")
            except Exception as e:
                logger.warning(f"记忆系统初始化/预热失败，将继续启动: {e}")

        # 预热 OCR 工具与文档验证器
        # 使用 1x1 PNG 的 base64 触发一次轻量调用，避免首次上传图片时冷启动
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
        logger.warning(f"工具预热过程出现异常（忽略，继续启动）: {e}")


def _resolve_user_id(request: Request | None, user_id: str | None) -> str | None:
    if user_id:
        return str(user_id)
    if request and hasattr(request, "state") and hasattr(request.state, "user"):
        u = request.state.user
        if isinstance(u, dict):
            return str(u.get("id") or u.get("user_id") or u.get("uid") or "")
    return None


@app.post("/api/health-records/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """上传健康档案文件并进行OCR识别"""
    try:
        uid = _resolve_user_id(request, user_id)
        # 允许匿名上传用于OCR预览，但最好还是要求登录

        file_ext = os.path.splitext(file.filename)[1]
        new_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = UPLOAD_DIR / new_filename

        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        # OCR处理
        ocr_text = ""
        ocr_info = {}
        if extract_text_from_image:
            try:
                b64 = base64.b64encode(content).decode("utf-8")
                # extract_text_from_image might be a Tool object or function
                if hasattr(extract_text_from_image, "fn"):
                    ocr_text = extract_text_from_image.fn(b64)
                else:
                    ocr_text = extract_text_from_image(b64)
            except Exception as e:
                logger.warning(f"OCR失败: {e}")

        # 尝试结构化提取
        if extract_medical_info and ocr_text:
            try:
                if hasattr(extract_medical_info, "fn"):
                    ocr_info = extract_medical_info.fn(ocr_text)
                else:
                    ocr_info = extract_medical_info(ocr_text)
                if isinstance(ocr_info, str):
                    try:
                        ocr_info = json.loads(ocr_info)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"结构化提取失败: {e}")

        # 保存文件记录
        file_id = str(uuid.uuid4())
        file_size = len(content)
        mime_type = file.content_type

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO file_attachments (id, record_id, filename, original_filename, file_path, file_size, mime_type)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        new_filename,
                        file.filename,
                        str(file_path),
                        file_size,
                        mime_type,
                    ),
                )
                conn.commit()

        return {
            "file_id": file_id,
            "filename": new_filename,
            "ocr_text": ocr_text,
            "ocr_info": ocr_info,
            "message": "上传成功",
        }
    except Exception as e:
        logger.error(f"上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.post("/api/visit-summaries/analyze-image", response_model=VisitSummary)
async def analyze_visit_summary_image(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    visit_date: str = Form(None),
    request: Request = None,
):
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            raise HTTPException(status_code=401, detail="未认证用户")

        ct = (getattr(file, "content_type", None) or "").strip().lower()
        if not ct.startswith("image/"):
            raise HTTPException(status_code=400, detail="仅支持图片上传")

        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过限制（10MB）")

        file_id = generate_id()
        ext = Path(file.filename or "").suffix
        saved_name = f"{file_id}{ext}"
        saved_path = UPLOAD_DIR / saved_name
        with open(saved_path, "wb") as f:
            f.write(content)

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
                        len(content),
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
                        extracted.get("doctor"),
                        extracted.get("hospital"),
                        extracted.get("department"),
                        extracted.get("chief_complaint"),
                        extracted.get("symptoms"),
                        extracted.get("examination"),
                        diagnosis_val,
                        extracted.get("treatment"),
                        extracted.get("prescription"),
                        extracted.get("follow_up"),
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
                cursor.execute(
                    "UPDATE file_attachments SET record_id = %s WHERE id = %s",
                    (new_id, file_id),
                )
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


@app.get("/api/consultations/history", response_model=List[Consultation])
async def get_consultation_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    request: Request = None,
):
    """获取健康咨询历史"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
            return []

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM consultations 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT %s OFFSET %s
                    """,
                    (uid, limit, skip),
                )
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
        # 后端保护：如请求体包含文件但未提供内容，返回400，避免产生空内容记录
        try:
            has_files = False
            if record.metadata and isinstance(record.metadata, dict):
                meta_files = record.metadata.get("files") or record.metadata.get(
                    "uploaded_files"
                )
                if isinstance(meta_files, list) and len(meta_files) > 0:
                    has_files = True
            content_empty = (record.content is None) or (
                isinstance(record.content, str) and record.content.strip() == ""
            )
            if has_files and content_empty:
                raise HTTPException(
                    status_code=400,
                    detail="检测到文件ID但内容为空：请使用 /api/health-records/upload 进行上传与OCR，或在创建时提供内容",
                )
        except HTTPException:
            raise
        except Exception:
            pass

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

                if record_update.metadata is not None:
                    update_fields.append("metadata = %s")
                    params.append(Json(record_update.metadata))

                if record_update.record_date is not None:
                    update_fields.append("record_date = %s")
                    params.append(record_update.record_date)

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
    file: UploadFile = File(...), user_id: str = Form(None), request: Request = None
):
    """上传文件"""
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

        # 检查文件大小（10MB限制）
        max_size = 10 * 1024 * 1024  # 10MB
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(status_code=400, detail="文件大小超过限制（10MB）")

        # 解析用户ID（优先表单，其次头部/Token）
        try:
            user_id = _resolve_user_id(request, user_id)
        except Exception:
            pass

        # 生成文件名
        file_id = generate_id()
        file_extension = Path(file.filename).suffix
        filename = f"{file_id}{file_extension}"
        file_path = UPLOAD_DIR / filename

        # 保存文件
        with open(file_path, "wb") as f:
            f.write(file_content)

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
                        len(file_content),
                        normalized_ct,
                        datetime.now(),
                        None,
                    ),
                )

                ocr_info = None
                memory_id = None
                record_id = None

                if normalized_ct.startswith("image/"):
                    image_base64 = base64.b64encode(file_content).decode("utf-8")
                    ocr_text = ""
                    document_type = "unknown"
                    confidence = 0.0
                    _used_paddle = False
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
                    ocr_text = _normalize_ocr_text(ocr_text)

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
                    document_type = validation_data.get("document_type") or "unknown"
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
                        f"file:{file_id}",
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

                    # 生成摘要：优先使用大模型；失败则回退规则摘要
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
                    else:
                        logger.info("使用规则摘要")
                    final_summary = llm_summary or _generate_ai_summary(
                        ocr_text_str,
                        (
                            metadata.get("extracted_info")
                            if isinstance(metadata, dict)
                            else None
                        ),
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
            "file_size": len(file_content),
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "your-secret-key-change-this-in-production"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def _resolve_user_id(request: Request, user_id: str | None) -> str:
    try:
        if user_id and str(user_id).strip():
            return str(user_id).strip()
    except Exception:
        pass
    try:
        xuid = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
        if isinstance(xuid, str) and xuid.strip():
            return xuid.strip()
    except Exception:
        pass
    try:
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
