from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from enum import Enum
import sqlite3
import json
import os
import uuid
import hashlib
from pathlib import Path
import logging
from contextlib import contextmanager
import base64
import mimetypes

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

# 数据库与上传目录配置（改为以本文件为基准的绝对路径）
MODULE_DIR = Path(__file__).resolve().parent
DB_PATH = str(MODULE_DIR / "health_records.db")
UPLOAD_DIR = MODULE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

@contextmanager
def get_db_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """初始化数据库表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 创建健康档案表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_records (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                record_type TEXT NOT NULL,
                summary TEXT,
                content TEXT,
                importance TEXT NOT NULL DEFAULT 'medium',
                tags TEXT,
                metadata TEXT,
                record_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_attachments TEXT
            )
        """)
        
        # 创建文件附件表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_attachments (
                id TEXT PRIMARY KEY,
                record_id TEXT,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                mime_type TEXT,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES health_records (id)
            )
        """)
        
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

def row_to_health_record(row) -> HealthRecord:
    """将数据库行转换为HealthRecord对象"""
    return HealthRecord(
        id=row["id"],
        title=row["title"],
        record_type=row["record_type"],
        summary=row["summary"],
        content=row["content"],
        importance=row["importance"],
        tags=deserialize_tags(row["tags"]),
        metadata=deserialize_metadata(row["metadata"]),
        record_date=datetime.strptime(row["record_date"], "%Y-%m-%d").date() if row["record_date"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        file_attachments=deserialize_tags(row["file_attachments"])
    )

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

@app.get("/api/health-records", response_model=List[HealthRecord])
async def get_health_records(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    record_type: Optional[RecordType] = Query(None, description="记录类型筛选"),
    importance: Optional[ImportanceLevel] = Query(None, description="重要性筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期")
):
    """获取健康档案列表"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 构建查询条件
            conditions = []
            params = []
            
            if record_type:
                conditions.append("record_type = ?")
                params.append(record_type.value)
            
            if importance:
                conditions.append("importance = ?")
                params.append(importance.value)
            
            if search:
                conditions.append("(title LIKE ? OR summary LIKE ? OR content LIKE ?)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param])
            
            if start_date:
                conditions.append("record_date >= ?")
                params.append(start_date.isoformat())
            
            if end_date:
                conditions.append("record_date <= ?")
                params.append(end_date.isoformat())
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT * FROM health_records 
                WHERE {where_clause}
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """
            
            params.extend([limit, skip])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [row_to_health_record(row) for row in rows]
            
    except Exception as e:
        logger.error(f"获取健康档案列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health-records/{record_id}", response_model=HealthRecord)
async def get_health_record(record_id: str):
    """获取单个健康档案详情"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="健康档案不存在")
            
            return row_to_health_record(row)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取健康档案详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/health-records", response_model=HealthRecord)
async def create_health_record(record: HealthRecordCreate):
    """创建健康档案"""
    try:
        # 后端保护：如请求体包含文件但未提供内容，返回400，避免产生空内容记录
        try:
            has_files = False
            if record.metadata and isinstance(record.metadata, dict):
                meta_files = record.metadata.get("files") or record.metadata.get("uploaded_files")
                if isinstance(meta_files, list) and len(meta_files) > 0:
                    has_files = True
            # 顶层 files 由网关可能转换为 metadata.uploaded_files，但也兼容直接传递
            # Pydantic 模型中未定义顶层 files，此处仅基于 metadata 判断
            content_empty = (record.content is None) or (isinstance(record.content, str) and record.content.strip() == "")
            if has_files and content_empty:
                raise HTTPException(
                    status_code=400,
                    detail="检测到文件ID但内容为空：请使用 /api/health-records/upload 进行上传与OCR，或在创建时提供内容"
                )
        except HTTPException:
            raise
        except Exception:
            # 不影响正常创建流程，保护逻辑失败时忽略
            pass

        record_id = generate_id()
        now = datetime.now()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO health_records (
                    id, title, record_type, summary, content, importance,
                    tags, metadata, record_date, created_at, updated_at, file_attachments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id,
                record.title,
                record.record_type.value,
                record.summary,
                record.content,
                record.importance.value,
                serialize_tags(record.tags),
                serialize_metadata(record.metadata),
                record.record_date.isoformat() if record.record_date else None,
                now.isoformat(),
                now.isoformat(),
                serialize_tags([])
            ))
            conn.commit()
            
            # 返回创建的记录
            cursor.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            return row_to_health_record(row)
            
    except Exception as e:
        logger.error(f"创建健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/health-records/{record_id}", response_model=HealthRecord)
async def update_health_record(record_id: str, record_update: HealthRecordUpdate):
    """更新健康档案"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 检查记录是否存在
            cursor.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
            existing_record = cursor.fetchone()
            if not existing_record:
                raise HTTPException(status_code=404, detail="健康档案不存在")
            
            # 构建更新字段
            update_fields = []
            params = []
            
            if record_update.title is not None:
                update_fields.append("title = ?")
                params.append(record_update.title)
            
            if record_update.record_type is not None:
                update_fields.append("record_type = ?")
                params.append(record_update.record_type.value)
            
            if record_update.summary is not None:
                update_fields.append("summary = ?")
                params.append(record_update.summary)
            
            if record_update.content is not None:
                update_fields.append("content = ?")
                params.append(record_update.content)
            
            if record_update.importance is not None:
                update_fields.append("importance = ?")
                params.append(record_update.importance.value)
            
            if record_update.tags is not None:
                update_fields.append("tags = ?")
                params.append(serialize_tags(record_update.tags))
            
            if record_update.metadata is not None:
                update_fields.append("metadata = ?")
                params.append(serialize_metadata(record_update.metadata))
            
            if record_update.record_date is not None:
                update_fields.append("record_date = ?")
                params.append(record_update.record_date.isoformat())
            
            if not update_fields:
                # 没有字段需要更新，直接返回现有记录
                return row_to_health_record(existing_record)
            
            # 添加更新时间
            update_fields.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(record_id)
            
            query = f"UPDATE health_records SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            
            # 返回更新后的记录
            cursor.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            return row_to_health_record(row)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新健康档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/health-records/{record_id}")
async def delete_health_record(record_id: str):
    """删除健康档案"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 检查记录是否存在
            cursor.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="健康档案不存在")
            
            # 删除相关文件附件
            cursor.execute("SELECT file_path FROM file_attachments WHERE record_id = ?", (record_id,))
            file_paths = cursor.fetchall()
            for file_path_row in file_paths:
                file_path = Path(file_path_row[0])
                if file_path.exists():
                    file_path.unlink()
            
            # 删除数据库记录
            cursor.execute("DELETE FROM file_attachments WHERE record_id = ?", (record_id,))
            cursor.execute("DELETE FROM health_records WHERE id = ?", (record_id,))
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
            cursor = conn.cursor()
            
            # 总记录数
            cursor.execute("SELECT COUNT(*) FROM health_records")
            total_records = cursor.fetchone()[0]
            
            # 按类型统计
            cursor.execute("""
                SELECT record_type, COUNT(*) 
                FROM health_records 
                GROUP BY record_type
            """)
            records_by_type = dict(cursor.fetchall())
            
            # 按重要性统计
            cursor.execute("""
                SELECT importance, COUNT(*) 
                FROM health_records 
                GROUP BY importance
            """)
            records_by_importance = dict(cursor.fetchall())
            
            # 最近7天的记录数
            cursor.execute("""
                SELECT COUNT(*) 
                FROM health_records 
                WHERE created_at >= datetime('now', '-7 days')
            """)
            recent_records_count = cursor.fetchone()[0]
            
            # 最后更新时间
            cursor.execute("""
                SELECT MAX(updated_at) 
                FROM health_records
            """)
            last_updated_str = cursor.fetchone()[0]
            last_updated = datetime.fromisoformat(last_updated_str) if last_updated_str else None
            
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
async def upload_file(file: UploadFile = File(...), user_id: str = Form("default_user")):
    """上传文件"""
    try:
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
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO file_attachments (
                    id, filename, original_filename, file_path,
                    file_size, mime_type, upload_time, record_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    filename,
                    file.filename,
                    str(file_path),
                    len(file_content),
                    normalized_ct,
                    datetime.now().isoformat(),
                    None,
                ),
            )

            # 尝试进行OCR与记忆入库（仅针对图片类型；图片必须经过OCR并成功入库）
            ocr_info = None
            memory_id = None
            record_id = None

            if normalized_ct.startswith("image/"):
                # 新增：优先使用 PaddleOCR（若可用）；否则回退到内置OCR工具
                try:
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
                    # 回退：若未用Paddle或识别为空，尝试内置OCR
                    if not ocr_text:
                        if not extract_text_from_image:
                            conn.rollback()
                            raise HTTPException(status_code=503, detail="OCR模块未加载，无法对图片进行识别与入库")
                        ocr_text = extract_text_from_image.fn(image_base64) if hasattr(extract_text_from_image, "fn") else extract_text_from_image(image_base64)
                    # 文档类型与置信度：若验证器可用则融合其置信度
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
                    # 验证医疗文档属性
                    validation = validate_medical_document.fn(ocr_text) if hasattr(validate_medical_document, "fn") else validate_medical_document(ocr_text)

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
                            memory_id = await health_records_memory_service.store_ocr_result(
                                user_id=user_id,
                                document_type=document_type,
                                ocr_text=ocr_text if isinstance(ocr_text, str) else str(ocr_text),
                                extracted_info=extracted_info if isinstance(extracted_info, dict) else {},
                                confidence=confidence,
                                file_path=str(file_path)
                            )
                        except Exception as e:
                            logger.warning(f"存储OCR结果到记忆失败: {e}")

                    # —— 将OCR识别结果入库到健康档案，并关联附件 ——
                    # 若OCR文本为空则视为失败
                    ocr_text_str = ocr_text if isinstance(ocr_text, str) else str(ocr_text)
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
                        "extracted_info": extracted_info if isinstance(extracted_info, dict) else {}
                    }

                    cursor.execute(
                        """
                        INSERT INTO health_records (
                            id, title, record_type, summary, content, importance,
                            tags, metadata, record_date, created_at, updated_at, file_attachments
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record_id,
                            title,
                            record_type,
                            ocr_text_str[:300] if ocr_text_str else None,
                            ocr_text_str,
                            ImportanceLevel.MEDIUM.value,
                            serialize_tags(tags),
                            serialize_metadata(metadata),
                            None,
                            now.isoformat(),
                            now.isoformat(),
                            serialize_tags([file_id]),
                        ),
                    )
                    cursor.execute(
                        "UPDATE file_attachments SET record_id = ? WHERE id = ?",
                        (record_id, file_id),
                    )

                    ocr_info = {
                        "document_type": document_type,
                        "confidence": confidence,
                        "text_length": len(ocr_text_str)
                    }

                    # 成功则提交事务
                    conn.commit()
                except HTTPException:
                    # 已经rollback并抛出
                    raise
                except Exception as e:
                    conn.rollback()
                    logger.error(f"OCR处理或入库失败: {e}")
                    raise HTTPException(status_code=422, detail=f"OCR处理或入库失败: {str(e)}")
            else:
                # 非图片：仅保存附件记录
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
async def upload_multiple_files(files: List[UploadFile] = File(...), user_id: str = Form("default_user")):
    try:
        if not files:
            raise HTTPException(status_code=400, detail="未提供文件")

        results = []
        for f in files:
            try:
                # 复用单文件上传的完整逻辑（含OCR与入库）
                res = await upload_file(file=f, user_id=user_id)
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

# 新增：获取指定记录的结构化与OCR信息（上移到启动语句之前）
@app.get("/api/health-records/{record_id}/extracted")
async def get_record_extracted_info(record_id: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT metadata FROM health_records WHERE id = ?", (record_id,))
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
            cursor = conn.cursor()
            cursor.execute(
                "SELECT original_filename, file_path, mime_type FROM file_attachments WHERE id = ?",
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