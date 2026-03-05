from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    summary_content: Optional[str] = None
    notes: Optional[str] = None
    files: Optional[List[str]] = []
    tests: Optional[List[Dict[str, Any]]] = []


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


class RAGBackfillRequest(BaseModel):
    user_id: Optional[str] = None
    source_types: List[str] = Field(default_factory=lambda: ["health_records", "visit_summaries"])
    limit: int = Field(default=200, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)
    dry_run: bool = False
    include_deleted: bool = False


class MonitorTarget(BaseModel):
    name: str
    url: str
    timeout: int = 5


class MonitorCheckRequest(BaseModel):
    targets: List[MonitorTarget]


class AdminRAGDocsListRequest(BaseModel):
    user_id: Optional[str] = None
    source_type: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)
    q: Optional[str] = None


class AdminRAGChunksListRequest(BaseModel):
    user_id: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)


class AdminRAGSearchRequest(BaseModel):
    user_id: Optional[str] = None
    query: str = Field(..., min_length=1, max_length=2000)
    source_type: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=200)
    include_chunks: bool = True


class AdminRAGReindexRequest(BaseModel):
    user_id: Optional[str] = None
    source_type: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    record_type: Optional[str] = None
    title: Optional[str] = None
    text: str = Field(..., min_length=1)


class AdminRAGReindexBulkRequest(BaseModel):
    user_id: Optional[str] = None
    items: List[AdminRAGReindexRequest] = Field(default_factory=list)


class MedicalKBDocUpsertRequest(BaseModel):
    doc_id: Optional[str] = None
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    tags: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    global_kb: bool = True


class MedicalKBDocBulkUpsertRequest(BaseModel):
    docs: List[MedicalKBDocUpsertRequest] = Field(default_factory=list)


class AdminMedicalKBImportDoc(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AdminMedicalKBImportRequest(BaseModel):
    docs: List[AdminMedicalKBImportDoc] = Field(default_factory=list)


class VisitSummaryBatchCompleteRequest(BaseModel):
    batch_id: str = Field(..., min_length=4)
    visit_date: Optional[str] = None


class ConsultationCreate(BaseModel):
    question: str
    answer: Optional[str] = None
    consultation_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Optional[List[str]] = []


class ChatMessageCreate(BaseModel):
    consultation_id: str
    role: str
    content: str
    files: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
