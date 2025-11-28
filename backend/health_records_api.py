from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Query, Request
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

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 可选：加载OCR与记忆服务（如果不可用则降级跳过）
try:
    from HealthRecordsManager.mcpserver.ocr_tool import extract_text_from_image, validate_medical_document
    try:
        from HealthRecordsManager.mcpserver.data_extraction_tool import extract_medical_info
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
    hrm_db_config = importlib.import_module('HealthRecordsManager.database_config')
    sys.modules['database_config'] = hrm_db_config

    from HealthRecordsManager.mcpserver.storage_tool import save_health_record as HRM_SAVE_RECORD  # type: ignore
except Exception as _hrm_err:
    logger.warning(f"HRM存储工具加载失败，将跳过双写: {_hrm_err}")
    HRM_SAVE_RECORD = None  # type: ignore

# 创建FastAPI应用
app = FastAPI(
    title="健康档案管理API",
    description="提供健康档案的创建、查询、更新、删除等功能",
    version="1.0.0"
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
    importance: ImportanceLevel = Field(ImportanceLevel.MEDIUM, description="重要性级别")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")
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
    file_attachments: Optional[List[str]] = Field(default_factory=list, description="附件文件列表")

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
    id: int
    user_id: str
    summary_id: Optional[str]
    title: Optional[str]
    visit_date: Optional[date]
    doctor: Optional[str]
    hospital: Optional[str]
    department: Optional[str]
    chief_complaint: Optional[str]
    symptoms: Optional[str]
    examination: Optional[str]
    diagnosis: Optional[str]
    treatment: Optional[str]
    prescription: Optional[str]
    follow_up: Optional[str]
    notes: Optional[str]
    files: Optional[List[str]] = []
    tests: Optional[List[Dict[str, Any]]] = []
    summary_content: Optional[str]
    generated_by: Optional[str]
    created_at: datetime

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
    id: int
    user_id: str
    consultation_id: Optional[str]
    session_id: Optional[str]
    question: Optional[str]
    answer: Optional[str]
    tags: Optional[List[str]]
    created_at: datetime

MODULE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = MODULE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "pha"),
    "password": os.getenv("DB_PASSWORD", "pha_pass"),
    "dbname": os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "personal_health_assistant")),
}

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
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    summary_id VARCHAR(64) UNIQUE,
                    title TEXT,
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
                    notes TEXT,
                    files JSONB,
                    tests JSONB,
                    summary_content TEXT,
                    generated_by VARCHAR(50),
                    created_at TIMESTAMPTZ DEFAULT now()
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
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS notes TEXT",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS files JSONB",
                "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS tests JSONB",
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
        s = (raw or "")
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
                for key in ("content", "Content"):
                    v = obj.get(key)
                    if isinstance(v, str) and v.strip():
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
                                parts.append(str(it.get("text") or it.get("word") or "").strip())
                            elif isinstance(it, str):
                                parts.append(it.strip())
                        text = "\n".join([p for p in parts if p])
                        if text.strip():
                            return text.strip()
                elif isinstance(data, str) and data.strip():
                    return data.strip()
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
                        parts.append(str(it.get("text") or it.get("word") or "").strip())
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
            prescription = extracted.get("prescription") or extracted.get("medications") or ""
            tests = extracted.get("tests") or ""
            key = extracted.get("key_findings") or extracted.get("summary") or ""
            if doc_type:
                parts.append(f"类型：{doc_type}")
            if date:
                parts.append(f"日期：{date}")
            if key:
                parts.append(f"要点：{str(key)[:120]}")
            if diagnosis:
                parts.append(f"诊断：{str(diagnosis)[:120]}")
            if result:
                parts.append(f"结果：{str(result)[:120]}")
            if prescription:
                parts.append(f"用药：{str(prescription)[:120]}")
            if tests:
                parts.append(f"检查：{str(tests)[:120]}")

        # 优先使用OCR正文；若OCR文本足够（>=50字），直接截断为摘要
        if len(text_clean) >= 50:
            summary = text_clean[:300]
        else:
            # 若仅有少量元信息，尝试组合元信息 + OCR片段
            info = "；".join([p for p in parts if p])
            if info and text_clean:
                remain = 300 - len(info)
                summary = (info + "；" + text_clean[:max(remain, 0)])
            else:
                summary = info or text_clean
            summary = summary[:300]

        return summary
    except Exception:
        t = (ocr_text or "")
        t = t.strip().replace("\n", " ")
        return t[:300]

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

        api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("LLM 密钥缺失，跳过")
            return None
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"
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
            "输出不超过300字，面向医生。"
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
            f"任务：在300字内概述真实信息，按‘{sections_str}’组织。"
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
                max_tokens=400,
            )
            text = resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM 摘要请求失败: {e}")
            return None

        text = (text or "").strip().replace("\n", " ")
        if not text:
            return None
        if len(text) > 300:
            text = text[:300]
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
def _save_to_hrm(user_id: str | None, record_type: str, title: str, content: str, extracted_data: dict | None = None):
    if not HRM_SAVE_RECORD:
        return
    try:
        enabled = str(os.getenv("HRM_DOUBLEWRITE_ENABLED", "0")).lower() in ("1", "true", "yes")
        if not enabled:
            return
        # 空内容不进行HRM入库，避免生成空记录
        if content is None or (isinstance(content, str) and content.strip() == ""):
            return
        uid = user_id or os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID")
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
        if 'health_records_memory_service' in globals() and health_records_memory_service:
            try:
                await health_records_memory_service.initialize()
                ms = getattr(health_records_memory_service, 'memory_system', None)
                if ms and getattr(ms, 'embedding_service', None):
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
        tiny_png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )
        if 'extract_text_from_image' in globals() and extract_text_from_image:
            try:
                _ = extract_text_from_image.fn(tiny_png_b64) if hasattr(extract_text_from_image, "fn") else extract_text_from_image(tiny_png_b64)
                logger.info("OCR工具预热完成")
            except Exception as e:
                logger.warning(f"OCR工具预热异常: {e}")
        if 'validate_medical_document' in globals() and validate_medical_document:
            try:
                _ = validate_medical_document.fn("warmup text") if hasattr(validate_medical_document, "fn") else validate_medical_document("warmup text")
                logger.info("医疗文档验证器预热完成")
            except Exception as e:
                logger.warning(f"医疗文档验证器预热异常: {e}")
    except Exception as e:
        logger.warning(f"工具预热过程出现异常（忽略，继续启动）: {e}")

@app.get("/api/health-records/status")
async def get_api_status():
    """检查API状态"""
    return {"status": "healthy", "timestamp": datetime.now()}

@app.get("/api/visit-summaries/history", response_model=List[VisitSummary])
async def get_visit_summaries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    request: Request = None
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
                    (uid, limit, skip)
                )
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    # Handle JSONB fields
                    for field in ['files', 'tests']:
                        if isinstance(row.get(field), str):
                            try:
                                row[field] = json.loads(row[field])
                            except:
                                row[field] = []
                        elif row.get(field) is None:
                            row[field] = []
                    results.append(VisitSummary(**row))
                return results
    except Exception as e:
        logger.error(f"获取就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/visit-summaries/create", response_model=VisitSummary)
async def create_visit_summary(summary: VisitSummaryCreate, user_id: Optional[str] = Query(None), request: Request = None):
    """创建新的就诊摘要"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
             raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查是否存在同名摘要
                if summary.summary_id:
                     cursor.execute("SELECT id FROM visit_summaries WHERE summary_id = %s", (summary.summary_id,))
                     if cursor.fetchone():
                         raise HTTPException(status_code=400, detail="摘要ID已存在")
                
                new_summary_id = summary.summary_id or generate_id()
                now = datetime.now()

                cursor.execute(
                    """
                    INSERT INTO visit_summaries (
                        user_id, summary_id, title, visit_date, doctor, hospital, department,
                        chief_complaint, symptoms, examination, diagnosis, treatment,
                        prescription, follow_up, notes, files, tests, summary_content,
                        generated_by, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s
                    ) RETURNING id
                    """,
                    (
                        uid, new_summary_id, summary.title, summary.visit_date, summary.doctor, summary.hospital, summary.department,
                        summary.chief_complaint, summary.symptoms, summary.examination, summary.diagnosis, summary.treatment,
                        summary.prescription, summary.follow_up, summary.notes, Json(summary.files), Json(summary.tests), summary.summary_content,
                        summary.generated_by, now
                    )
                )
                new_id = cursor.fetchone()['id']
                conn.commit()

                # Fetch back the created record
                cursor.execute("SELECT * FROM visit_summaries WHERE id = %s", (new_id,))
                row = cursor.fetchone()
                
                # Handle JSONB fields
                for field in ['files', 'tests']:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []
                
                return VisitSummary(**row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/consultations/history", response_model=List[Consultation])
async def get_consultation_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    request: Request = None
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
                    (uid, limit, skip)
                )
                rows = cursor.fetchall()
                # Handle JSONB tags field
                results = []
                for row in rows:
                    if isinstance(row.get('tags'), str):
                        try:
                            row['tags'] = json.loads(row['tags'])
                        except:
                            row['tags'] = []
                    elif row.get('tags') is None:
                         row['tags'] = []
                    results.append(Consultation(**row))
                return results
    except Exception as e:
        logger.error(f"获取咨询历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/visit-summaries/update/{summary_id}", response_model=VisitSummary)
async def update_visit_summary(
    summary_id: int, 
    summary: VisitSummaryCreate, 
    user_id: Optional[str] = Query(None), 
    request: Request = None
):
    """更新就诊摘要"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
             raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查是否存在
                cursor.execute("SELECT * FROM visit_summaries WHERE id = %s AND user_id = %s", (summary_id, uid))
                existing = cursor.fetchone()
                if not existing:
                    raise HTTPException(status_code=404, detail="就诊摘要不存在或无权修改")
                
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
                    for field in ['files', 'tests']:
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
                for field in ['files', 'tests']:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []
                
                return VisitSummary(**row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新就诊摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/visit-summaries/delete/{summary_id}")
async def delete_visit_summary(
    summary_id: int, 
    user_id: Optional[str] = Query(None), 
    request: Request = None
):
    """删除就诊摘要"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
             raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM visit_summaries WHERE id = %s AND user_id = %s RETURNING id", (summary_id, uid))
                deleted = cursor.fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail="就诊摘要不存在或无权删除")
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
    request: Request = None
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
                     cursor.execute("SELECT id FROM consultations WHERE consultation_id = %s", (consultation.consultation_id,))
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
                        uid, new_consultation_id, consultation.session_id, 
                        consultation.question, consultation.answer, 
                        Json(consultation.tags or []), now
                    )
                )
                new_id = cursor.fetchone()['id']
                conn.commit()

                # Fetch back
                cursor.execute("SELECT * FROM consultations WHERE id = %s", (new_id,))
                row = cursor.fetchone()
                
                # Handle JSONB fields
                if isinstance(row.get('tags'), str):
                    try:
                        row['tags'] = json.loads(row['tags'])
                    except:
                        row['tags'] = []
                elif row.get('tags') is None:
                        row['tags'] = []
                
                return Consultation(**row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建咨询记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/consultations/delete/{consultation_id}")
async def delete_consultation(
    consultation_id: int, 
    user_id: Optional[str] = Query(None), 
    request: Request = None
):
    """删除咨询记录"""
    try:
        uid = _resolve_user_id(request, user_id)
        if not uid:
             raise HTTPException(status_code=401, detail="未认证用户")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM consultations WHERE id = %s AND user_id = %s RETURNING id", (consultation_id, uid))
                deleted = cursor.fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail="咨询记录不存在或无权删除")
                conn.commit()
                return {"message": "删除成功", "id": consultation_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除咨询记录失败: {e}")
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
    request: Request = None
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
                    conditions.append("(title ILIKE %s OR summary ILIKE %s OR content ILIKE %s)")
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
async def get_health_record(record_id: str, user_id: Optional[str] = Query(None, description="用户ID过滤"), request: Request = None):
    """获取单个健康档案详情（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                uid = _resolve_user_id(request, user_id)
                if uid:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s AND user_id = %s", (record_id, uid))
                else:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s", (record_id,))
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="健康档案不存在或无权限访问")
                return row_to_health_record(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取健康档案详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/health-records", response_model=HealthRecord)
async def create_health_record(record: HealthRecordCreate, user_id: Optional[str] = Query(None, description="用户ID"), request: Request = None):
    """创建健康档案（按用户隔离）"""
    try:
        # 后端保护：如请求体包含文件但未提供内容，返回400，避免产生空内容记录
        try:
            has_files = False
            if record.metadata and isinstance(record.metadata, dict):
                meta_files = record.metadata.get("files") or record.metadata.get("uploaded_files")
                if isinstance(meta_files, list) and len(meta_files) > 0:
                    has_files = True
            content_empty = (record.content is None) or (isinstance(record.content, str) and record.content.strip() == "")
            if has_files and content_empty:
                raise HTTPException(
                    status_code=400,
                    detail="检测到文件ID但内容为空：请使用 /api/health-records/upload 进行上传与OCR，或在创建时提供内容"
                )
        except HTTPException:
            raise
        except Exception:
            pass

        # 基于附件ID的去重：如提交的 metadata.files 或顶层 files 包含已生成OCR的附件，则改为更新既有记录而非新增
        file_ids: list[str] = []
        try:
            if isinstance(record.metadata, dict):
                mfiles = record.metadata.get("files") or record.metadata.get("uploaded_files")
                if isinstance(mfiles, list):
                    file_ids.extend([str(x) for x in mfiles if isinstance(x, (str, int))])
            if isinstance(record.files, list):
                file_ids.extend([str(x) for x in record.files if isinstance(x, (str, int))])
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
                            tuple(file_ids)
                        )
                        existing_links = [r[0] for r in cursor.fetchall() if r and r[0]]
                        if existing_links:
                            cursor.execute("SELECT id, user_id, metadata, content FROM health_records WHERE id = %s", (existing_links[0],))
                            linked = cursor.fetchone()
                            if linked and (not user_id or str(linked[1]) == str(user_id)):
                                target_existing_id = linked[0]
                                # 进行更新而非新增，且不覆盖已有OCR content
                                # 合并metadata（以新提交为主）
                                try:
                                    old_meta = linked[2] if isinstance(linked[2], dict) else {}
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
                                    tuple(params + [target_existing_id])
                                )
                                conn.commit()
                                cursor.execute("SELECT * FROM health_records WHERE id = %s", (target_existing_id,))
                                row = cursor.fetchone()
                                return row_to_health_record(row)
                    except Exception:
                        pass

                # 正常新增
                # 追加：若提交为空内容且无文件ID，尝试与最近OCR生成的记录合并，避免重复
                try:
                    content_empty = (record.content is None) or (isinstance(record.content, str) and record.content.strip() == "")
                    summary_empty = (record.summary is None) or (isinstance(record.summary, str) and record.summary.strip() == "")
                    no_files = (not file_ids)
                    if content_empty and summary_empty and no_files:
                        cursor.execute(
                            """
                            SELECT * FROM health_records
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                            (uid,)
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
                                    if md.get("uploaded_files") or md.get("file_id") or md.get("ocr_info"):
                                        return True
                                tags_v = r.get("tags")
                                if isinstance(tags_v, str):
                                    tags_v = deserialize_tags(tags_v)
                                return isinstance(tags_v, list) and ("ocr" in tags_v or "auto_import" in tags_v)
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
                                return (datetime.now() - created_dt).total_seconds() <= minutes * 60
                            except Exception:
                                return False
                        if recent and _has_ocr_marks(recent) and _within_minutes(recent, 10):
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
                                    tuple(params + [recent.get("id")])
                                )
                                conn.commit()
                                cursor.execute("SELECT * FROM health_records WHERE id = %s", (recent.get("id"),))
                                row = cursor.fetchone()
                                logger.info(f"create dedup merged into recent id={recent.get('id')} user_id={uid}")
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
                    """
                    ,
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
                cursor.execute("SELECT * FROM health_records WHERE id = %s", (record_id,))
                row = cursor.fetchone()
                created = row_to_health_record(row)

            # 新增：写入HRM（PostgreSQL）以供Agent检索
            try:
                _save_to_hrm(
                    user_id=uid,
                    record_type=created.record_type,
                    title=created.title,
                    content=created.content or (created.summary or ""),
                    extracted_data=created.metadata or {}
                )
            except Exception as e:
                logger.warning(f"创建记录后HRM双写失败：{e}")

            try:
                if health_records_memory_service is not None:
                    if not health_records_memory_service.is_available():
                        await health_records_memory_service.initialize()
                    imp_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
                    imp_key = created.importance.value if hasattr(created.importance, "value") else str(created.importance)
                    imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                    await health_records_memory_service.store_health_record(
                        user_id=uid,
                        record_type=created.record_type,
                        record_data={
                            "id": created.id,
                            "title": created.title,
                            "content": created.content,
                            "metadata": created.metadata or {},
                            "record_date": str(created.record_date) if created.record_date else None
                        },
                        summary=created.summary or "",
                        importance=imp_val,
                        tags=created.tags or []
                    )
            except Exception as e:
                logger.warning(f"创建记录后写入记忆失败：{e}")

            return created
            
    except Exception as e:
        logger.error(f"创建健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/health-records/{record_id}", response_model=HealthRecord)
async def update_health_record(record_id: str, record_update: HealthRecordUpdate, user_id: Optional[str] = Query(None, description="用户ID"), request: Request = None):
    """更新健康档案（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查记录是否存在并属于用户
                uid = _resolve_user_id(request, user_id)
                if user_id:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s AND user_id = %s", (record_id, user_id))
                else:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s", (record_id,))
                existing_record = cursor.fetchone()
                if not existing_record:
                    raise HTTPException(status_code=404, detail="健康档案不存在或无权限访问")

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
                    cursor.execute("SELECT * FROM health_records WHERE id = %s AND user_id = %s", (record_id, user_id))
                else:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s", (record_id,))
                row = cursor.fetchone()
                updated = row_to_health_record(row)
                try:
                    _save_to_hrm(
                        user_id=uid,
                        record_type=updated.record_type,
                        title=updated.title,
                        content=updated.content or (updated.summary or ""),
                        extracted_data=updated.metadata or {}
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
                        if mem_id and getattr(health_records_memory_service, 'memory_system', None):
                            try:
                                health_records_memory_service.memory_system.update_memory(
                                    memory_id=mem_id,
                                    content={
                                        'text': f"更新健康档案: {updated.title}",
                                        'structured_data': {
                                            'record_id': updated.id,
                                            'record_type': updated.record_type,
                                            'content': updated.content,
                                            'metadata': updated.metadata or {}
                                        }
                                    }
                                )
                            except Exception:
                                imp_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
                                imp_key = updated.importance.value if hasattr(updated.importance, "value") else str(updated.importance)
                                imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                                await health_records_memory_service.store_health_record(
                                    user_id=uid,
                                    record_type=updated.record_type,
                                    record_data={
                                        "id": updated.id,
                                        "title": updated.title,
                                        "content": updated.content,
                                        "metadata": updated.metadata or {}
                                    },
                                    summary=updated.summary or "",
                                    importance=imp_val,
                                    tags=updated.tags or []
                                )
                        else:
                            imp_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
                            imp_key = updated.importance.value if hasattr(updated.importance, "value") else str(updated.importance)
                            imp_val = imp_map.get(str(imp_key).lower(), 0.5)
                            await health_records_memory_service.store_health_record(
                                user_id=uid,
                                record_type=updated.record_type,
                                record_data={
                                    "id": updated.id,
                                    "title": updated.title,
                                    "content": updated.content,
                                    "metadata": updated.metadata or {}
                                },
                                summary=updated.summary or "",
                                importance=imp_val,
                                tags=updated.tags or []
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
async def delete_health_record(record_id: str, user_id: Optional[str] = Query(None, description="用户ID"), request: Request = None):
    """删除健康档案（按用户隔离）"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 检查记录是否存在并属于用户
                uid = _resolve_user_id(request, user_id)
                if uid:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s AND user_id = %s", (record_id, uid))
                else:
                    cursor.execute("SELECT * FROM health_records WHERE id = %s", (record_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="健康档案不存在或无权限访问")

                cursor.execute("SELECT file_path FROM file_attachments WHERE record_id = %s", (record_id,))
                file_paths = cursor.fetchall()
                for file_path_row in file_paths:
                    try:
                        fp = file_path_row["file_path"] if isinstance(file_path_row, dict) else file_path_row[0]
                        if fp:
                            file_path = Path(fp)
                            if file_path.exists():
                                file_path.unlink()
                    except Exception:
                        pass

                try:
                    cursor.execute("SELECT metadata FROM health_records WHERE id = %s", (record_id,))
                    r = cursor.fetchone()
                    mem_id = None
                    try:
                        meta = deserialize_metadata(r[0]) if r and isinstance(r[0], str) else (r[0] if r else {})
                        if isinstance(meta, dict):
                            mem_id = meta.get("memory_id")
                    except Exception:
                        mem_id = None
                    if mem_id and health_records_memory_service and health_records_memory_service.is_available():
                        try:
                            health_records_memory_service.memory_system.delete_memory(mem_id)
                        except Exception:
                            pass
                except Exception:
                    pass

                cursor.execute("DELETE FROM file_attachments WHERE record_id = %s", (record_id,))
                if uid:
                    cursor.execute("DELETE FROM health_records WHERE id = %s AND user_id = %s", (record_id, uid))
                else:
                    cursor.execute("DELETE FROM health_records WHERE id = %s", (record_id,))
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
                    last_updated=last_updated
                )
            
    except Exception as e:
        logger.error(f"获取健康统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health-records/insights", response_model=HealthInsightsResponse)
async def get_health_insights(
    analysis_type: str = Query("comprehensive", description="分析类型"),
    include_recommendations: bool = Query(True, description="包含建议"),
    include_trends: bool = Query(True, description="包含趋势"),
    include_risks: bool = Query(True, description="包含风险")
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
                metrics={"平均收缩压": 120, "平均舒张压": 80}
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
                recommendations=["每周游泳2-3次", "每天快走30分钟", "定期进行力量训练"]
            )
        ]
        
        health_score = {
            "overall": 85,
            "categories": {
                "心血管健康": 88,
                "代谢健康": 82,
                "免疫系统": 90,
                "精神健康": 78
            },
            "summary": "您的整体健康状况良好，建议继续保持健康的生活方式。"
        }
        
        quick_tips = [
            {"title": "多喝水", "description": "每天至少饮用8杯水，保持身体水分平衡"},
            {"title": "规律作息", "description": "保持每天7-8小时的优质睡眠"},
            {"title": "均衡饮食", "description": "多吃蔬菜水果，减少加工食品摄入"}
        ]
        
        return HealthInsightsResponse(
            insights=insights,
            health_score=health_score,
            quick_tips=quick_tips
        )
        
    except Exception as e:
        logger.error(f"获取健康洞察失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/health-records/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Form(None), request: Request = None):
    """上传文件"""
    try:
        logger.info(f"upload start filename={getattr(file,'filename',None)} ct={getattr(file,'content_type',None)}")
        # 检查与规范化文件类型（支持 octet-stream 与扩展名推断）
        allowed_types = {
            "image/jpeg", "image/jpg", "image/png", "image/gif",
            # 扩展前端支持的图片类型，避免前端允许而后端拒绝
            "image/webp", "image/bmp",
            "application/pdf", "text/plain",
            "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
        if (not normalized_ct or normalized_ct == "application/octet-stream") and isinstance(file.filename, str):
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
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or '').suffix or ".png")
                        tmp.write(file_content)
                        tmp_path = tmp.name
                        tmp.close()
                        try:
                            ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch')
                            result = ocr_engine.ocr(tmp_path, cls=True)
                            lines = [line[1] for line in (result[0] if result else [])]
                            ocr_text = "\n".join([t[0] for t in lines])
                            confs = [float(t[1]) for t in lines if isinstance(t[1], (int, float))]
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
                                raise HTTPException(status_code=503, detail="OCR模块未加载，无法对图片进行识别与入库")
                            ocr_text = extract_text_from_image.fn(image_base64) if hasattr(extract_text_from_image, "fn") else extract_text_from_image(image_base64)
                    ocr_text = _normalize_ocr_text(ocr_text)

                    if validate_medical_document:
                        try:
                            validation_json = validate_medical_document.fn(ocr_text) if hasattr(validate_medical_document, "fn") else validate_medical_document(ocr_text)
                            val = json.loads(validation_json) if isinstance(validation_json, str) else (validation_json or {})
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
                            info_json = _extract_medical_info.fn(ocr_text) if hasattr(_extract_medical_info, "fn") else _extract_medical_info(ocr_text)
                            extracted_info = json.loads(info_json) if isinstance(info_json, str) else info_json
                        except Exception as e:
                            logger.warning(f"结构化提取失败: {e}")

                    try:
                        validation_data = json.loads(validation) if isinstance(validation, str) else validation
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
                            info_json = extract_medical_info.fn(ocr_text) if hasattr(extract_medical_info, "fn") else extract_medical_info(ocr_text)
                            extracted_info = json.loads(info_json) if isinstance(info_json, str) else (info_json or {})
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
                                        ocr_text=ocr_text if isinstance(ocr_text, str) else str(ocr_text),
                                        extracted_info=extracted_info if isinstance(extracted_info, dict) else {},
                                        confidence=confidence,
                                        file_path=str(file_path)
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
                    ocr_text_str = _normalize_ocr_text(ocr_text if isinstance(ocr_text, str) else str(ocr_text))
                    if not ocr_text_str or not ocr_text_str.strip():
                        conn.rollback()
                        raise HTTPException(status_code=422, detail="OCR识别结果为空，未入库")

                    doc_type_lower = (document_type or "").lower()
                    ext_doc_type = (extracted_info or {}).get("document_type") if isinstance(extracted_info, dict) else None
                    if isinstance(ext_doc_type, str) and ext_doc_type.strip():
                        doc_type_lower = ext_doc_type.strip().lower()

                    lab_keywords = ["血常规", "化验", "检验", "实验室", "检验报告", "化验单", "B超", "CT", "MRI", "X光", "影像"]
                    prescription_keywords = ["处方", "医嘱", "用药", "药品", "药方"]
                    surgery_keywords = ["手术", "术后", "术前", "麻醉"]
                    allergy_keywords = ["过敏", "皮试", "过敏史"]
                    vaccination_keywords = ["疫苗", "接种", "免疫"]
                    vital_keywords = ["血压", "心率", "体温", "呼吸", "身高", "体重"]

                    def has_any(text: str, kws: list[str]) -> bool:
                        return any(k in text for k in kws)

                    if doc_type_lower in {"test_report", "lab_result", "inspection_report", "检验报告", "化验单"} or has_any(ocr_text_str, lab_keywords):
                        record_type = RecordType.LAB_RESULT.value
                    elif doc_type_lower in {"prescription", "medication", "处方"} or has_any(ocr_text_str, prescription_keywords):
                        record_type = RecordType.PRESCRIPTION.value
                    elif has_any(ocr_text_str, surgery_keywords):
                        record_type = RecordType.SURGERY.value
                    elif doc_type_lower in {"medical_record", "病历", "门诊记录", "出院记录", "入院记录"}:
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
                    tags = ["ocr", "auto_import", document_type or "unknown", f"file:{file_id}"]
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
                            "text_length": len(ocr_text_str)
                        },
                        "memory_id": memory_id,
                        "extracted_info": extracted_info if isinstance(extracted_info, dict) else {},
                        "uploaded_files": [file_id],
                        **({"file_hash": file_hash} if file_hash else {})
                    }

                    # 去重：同一用户相同OCR内容或文件哈希命中则复用记录并仅关联附件
                    try:
                        cursor.execute(
                            """
                            SELECT id FROM health_records
                            WHERE user_id = %s AND (content = %s OR metadata ->> 'file_hash' = %s)
                            ORDER BY created_at DESC LIMIT 1
                            """
                            ,
                            (user_id, ocr_text_str, file_hash)
                        )
                        dup = cursor.fetchone()
                        if dup and (dup.get('id') if isinstance(dup, dict) else dup[0]):
                            dup_id = dup.get('id') if isinstance(dup, dict) else dup[0]
                            cursor.execute(
                                "UPDATE file_attachments SET record_id = %s WHERE id = %s",
                                (dup_id, file_id)
                            )
                            conn.commit()
                            logger.info(f"upload dedup merged file_id={file_id} record_id={dup_id} user_id={user_id} hash={file_hash}")
                            return {
                                "file_id": file_id,
                                "record_id": dup_id,
                                "ocr_info": {
                                    "document_type": document_type,
                                    "confidence": confidence,
                                    "text_length": len(ocr_text_str)
                                },
                                "message": "duplicate_merged"
                            }
                    except Exception:
                        pass

                    # 生成摘要：优先使用大模型；失败则回退规则摘要
                    try:
                        llm_summary = await _maybe_llm_summary(ocr_text_str, metadata.get("extracted_info") if isinstance(metadata, dict) else None)
                    except Exception as e:
                        logger.warning(f"调用 LLM 摘要失败: {e}")
                        llm_summary = None
                    if llm_summary is not None:
                        logger.info("使用 LLM 摘要")
                    else:
                        logger.info("使用规则摘要")
                    final_summary = llm_summary or _generate_ai_summary(ocr_text_str, metadata.get("extracted_info") if isinstance(metadata, dict) else None)

                    cursor.execute(
                        """
                        INSERT INTO health_records (
                            id, user_id, title, record_type, summary, content, importance,
                            tags, metadata, record_date, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        ,
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
                        "text_length": len(ocr_text_str)
                    }

                    # 成功则提交事务
                    conn.commit()
                    logger.info(f"upload insert record_id={record_id} user_id={user_id} file_id={file_id} type={record_type} summary_len={len(final_summary or '')} content_len={len(ocr_text_str or '')}")

                    # 新增：写入HRM（PostgreSQL）以供Agent检索
                    try:
                        _save_to_hrm(
                            user_id=user_id,
                            record_type=record_type,
                            title=title,
                            content=ocr_text_str,
                            extracted_data=metadata.get("extracted_info") or {}
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
async def upload_multiple_files(files: List[UploadFile] = File(...), user_id: str = Form(None), request: Request = None):
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
                results.append({
                    "filename": getattr(f, "filename", None),
                    "error": he.detail
                })
            except Exception as e:
                results.append({
                    "filename": getattr(f, "filename", None),
                    "error": str(e)
                })

        return {"files": results, "count": len(results), "message": f"已处理 {len(results)} 个文件"}
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
                cursor.execute("SELECT id, title, record_type, summary, content, metadata FROM health_records WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
                rows = cursor.fetchall()

            for row in rows:
                try:
                    rid = row["id"]
                    title = row["title"] or "记录"
                    rtype = row["record_type"] or "other"
                    content = row["content"] or (row["summary"] or "")
                    meta = deserialize_metadata(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or {})
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
                        extracted_data=extracted
                    )
                    synced += 1
                except Exception as e:
                    logger.warning(f"同步单条记录失败（已跳过）: {e}")
                    skipped += 1

        return {
            "message": "同步完成",
            "user_id": user_id,
            "synced": synced,
            "skipped": skipped
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
                cursor.execute("SELECT metadata FROM health_records WHERE id = %s", (record_id,))
                row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="健康档案不存在")
            metadata = deserialize_metadata(row[0] if isinstance(row, tuple) else row["metadata"])
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
            original_name = row[0] if isinstance(row, tuple) else row["original_filename"]
            path_str = row[1] if isinstance(row, tuple) else row["file_path"]
            mime = (row[2] if isinstance(row, tuple) else row["mime_type"]) or "application/octet-stream"
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
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this-in-production')
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')

def _resolve_user_id(request: Request, user_id: str | None) -> str:
    try:
        if user_id and str(user_id).strip():
            return str(user_id).strip()
    except Exception:
        pass
    try:
        xuid = request.headers.get('X-User-Id') or request.headers.get('x-user-id')
        if isinstance(xuid, str) and xuid.strip():
            return xuid.strip()
    except Exception:
        pass
    try:
        auth = request.headers.get('authorization') or request.headers.get('Authorization')
        if isinstance(auth, str) and auth.lower().startswith('bearer '):
            token = auth.split(' ', 1)[1].strip()
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            uid = payload.get('user_id') or payload.get('sub')
            if isinstance(uid, str) and uid.strip():
                return uid.strip()
    except Exception:
        pass
    try:
        env_uid = os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID")
        if isinstance(env_uid, str) and env_uid.strip() and env_uid.strip().lower() != "default_user":
            return env_uid.strip()
    except Exception:
        pass
    return ""
