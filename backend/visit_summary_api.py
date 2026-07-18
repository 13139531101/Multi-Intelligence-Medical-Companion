import logging
import os
import sys
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

import anyio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from contextlib import contextmanager
from psycopg.rows import dict_row

# Ensure backend is in path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

try:
    from HealthRecordsManager.mcpserver.ocr_tool import call_local_ocr, call_aliyun_ocr
except ImportError:
    # Fallback if imports fail due to path issues
    logging.warning("Could not import ocr_tool directly, using mock.")

    def call_local_ocr(img):
        return "Mock OCR Result: 无法加载本地OCR工具"

    def call_aliyun_ocr(img):
        return "Mock OCR Result: 无法加载阿里云OCR工具"

try:
    from HealthRecordsManager.mcpserver.data_extraction_tool import extract_test_results
except Exception:
    extract_test_results = None

try:
    # Try to import database manager from health_records_api or similar
    from health_records_api import get_db_connection
except ImportError:
    # Define a simple DB manager if not found
    import psycopg
    from psycopg_pool import ConnectionPool

    _db_pool: ConnectionPool | None = None
    _db_pool_init_attempted = False

    def _get_pool() -> ConnectionPool | None:
        global _db_pool, _db_pool_init_attempted
        if _db_pool is not None:
            return _db_pool
        if _db_pool_init_attempted:
            return None
        _db_pool_init_attempted = True
        try:
            dsn = os.environ.get(
                "DATABASE_URL"
            ) or os.environ.get("PG_DSN"
            ) or (
                "postgresql://"
                + (os.environ.get("MEMORY_DB_USER") or os.environ.get("DB_USER") or "pha")
                + ":"
                + (os.environ.get("MEMORY_DB_PASSWORD") or os.environ.get("DB_PASSWORD") or "pha_pass")
                + "@"
                + (os.environ.get("MEMORY_DB_HOST") or os.environ.get("DB_HOST") or "localhost")
                + ":"
                + (os.environ.get("DB_PORT", "5432"))
                + "/"
                + (os.environ.get("MEMORY_DB_NAME") or os.environ.get("DB_NAME") or "personal_health_assistant")
            )
            _db_pool = ConnectionPool(dsn, max_size=max(int(os.getenv("DB_POOL_MAX_SIZE", "20")), 1))
            return _db_pool
        except Exception:
            _db_pool = None
            return None

    @contextmanager
    def get_db_connection():
        pool = _get_pool()
        if pool is not None:
            with pool.connection() as conn:
                try:
                    conn.autocommit = False
                except Exception:
                    pass
                yield conn
            return
        conn = psycopg.connect(
            os.environ.get("DATABASE_URL") or os.environ.get("PG_DSN") or (
                "postgresql://"
                + (os.environ.get("MEMORY_DB_USER") or os.environ.get("DB_USER") or "pha")
                + ":"
                + (os.environ.get("MEMORY_DB_PASSWORD") or os.environ.get("DB_PASSWORD") or "pha_pass")
                + "@"
                + (os.environ.get("MEMORY_DB_HOST") or os.environ.get("DB_HOST") or "localhost")
                + ":"
                + (os.environ.get("DB_PORT", "5432"))
                + "/"
                + (os.environ.get("MEMORY_DB_NAME") or os.environ.get("DB_NAME") or "personal_health_assistant")
            ),
            row_factory=dict_row,
        )
        try:
            yield conn
        finally:
            conn.close()

router = APIRouter(prefix="/visit-summary", tags=["Visit Summary"])
logger = logging.getLogger(__name__)

_upload_limiter: anyio.CapacityLimiter | None = None


def _get_upload_limiter() -> anyio.CapacityLimiter:
    global _upload_limiter
    if _upload_limiter is None:
        try:
            n = int(os.getenv("VISIT_SUMMARY_UPLOAD_MAX_CONCURRENCY", "8"))
        except Exception:
            n = 8
        _upload_limiter = anyio.CapacityLimiter(max(n, 1))
    return _upload_limiter


class VisitSummaryResponse(BaseModel):
    summary_id: str
    visit_date: str
    hospital: str
    diagnosis: str
    prescription: List[str]
    advice: str
    original_text: str


def _extract_numeric_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    import re
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _extract_feature_value(feature: str, tests: Any) -> Optional[float]:
    key = (feature or "").strip().lower()
    if not key:
        return None
    alias_map = {
        "blood_pressure": ["血压", "收缩压", "舒张压", "bp", "blood pressure"],
        "blood_sugar": ["血糖", "葡萄糖", "glu", "glucose"],
        "heart_rate": ["心率", "脉搏", "hr", "heart rate"],
        "temperature": ["体温", "temp", "temperature"],
        "weight": ["体重", "weight"],
        "spo2": ["血氧", "spo2", "氧饱和度"],
    }
    aliases = alias_map.get(key, [key])
    if isinstance(tests, dict):
        for name, detail in tests.items():
            name_key = str(name or "").lower()
            if not any(alias.lower() in name_key for alias in aliases):
                continue
            if isinstance(detail, dict):
                value = detail.get("value")
            else:
                value = detail
            value_text = str(value or "").strip()
            if "/" in value_text and key == "blood_pressure":
                parts = [p.strip() for p in value_text.split("/") if p.strip()]
                if "舒张压" in name_key and len(parts) > 1:
                    return _extract_numeric_value(parts[1])
                return _extract_numeric_value(parts[0])
            return _extract_numeric_value(value)
    if isinstance(tests, list):
        for item in tests:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("test_name") or "").strip()
            if not name:
                continue
            name_key = name.lower()
            if not any(alias.lower() in name_key for alias in aliases):
                continue
            value = item.get("value")
            value_text = str(value or "").strip()
            if "/" in value_text and key == "blood_pressure":
                parts = [p.strip() for p in value_text.split("/") if p.strip()]
                if "舒张压" in name_key and len(parts) > 1:
                    return _extract_numeric_value(parts[1])
                return _extract_numeric_value(parts[0])
            return _extract_numeric_value(value)
    return None


def _structure_text_with_llm(text: str) -> Dict[str, Any]:
    """
    Use LLM (or rule-based fallback) to structure the OCR text.
    """
    # TODO: Integrate with A2AServer.mcp_client for real LLM calls.
    # For now, use a heuristic parser.

    result = {
        "visit_date": datetime.now().strftime("%Y-%m-%d"),
        "hospital": "未识别医院",
        "diagnosis": "未识别诊断",
        "prescription": [],
        "advice": ""
    }

    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if "医院" in line:
            result["hospital"] = line
        if "诊断" in line or "印象" in line:
            result["diagnosis"] = line
        if "药" in line or "片" in line or "胶囊" in line:
            result["prescription"].append(line)
        if "建议" in line or "医嘱" in line:
            result["advice"] += line + "; "

    return result


@router.post("/upload", response_model=VisitSummaryResponse)
async def upload_visit_record(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    visit_date: Optional[str] = Form(None)
):
    """
    Upload a visit record photo, OCR it, structure it, and save it.
    """
    limiter = _get_upload_limiter()
    await limiter.acquire()
    try:
        max_size = int(os.getenv("VISIT_SUMMARY_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        chunk_size = int(
            os.getenv("VISIT_SUMMARY_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        buf = bytearray()
        try:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_size:
                    raise HTTPException(status_code=400, detail="文件大小超过限制")
                buf.extend(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        contents = bytes(buf)
        import base64
        img_b64 = base64.b64encode(contents).decode("utf-8")

        # 2. OCR
        # Try Aliyun first if configured, else Local
        if os.environ.get("ALIYUN_ACCESS_KEY_ID"):
            ocr_text = call_aliyun_ocr(img_b64)
        else:
            ocr_text = call_local_ocr(img_b64)

        if not ocr_text or "失败" in ocr_text:
            # If OCR failed, still return what we have but mark as failed
            logger.warning(f"OCR Failed: {ocr_text}")
            # Continue with empty text or error message

        # 3. Structure Data
        structured_data = _structure_text_with_llm(ocr_text)
        if visit_date:
            structured_data["visit_date"] = visit_date

        # 4. Save to DB
        summary_id = str(uuid.uuid4())

        # Check if visit_summaries table exists, if not create it (or use health_records)
        # We will use a new table 'visit_summaries_structured' or reuse 'visit_summaries'
        # 'visit_summaries' table structure from previous search:
        # (user_id, summary_id, visit_date, summary_content, generated_by, diagnosis)

        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Ensure table exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS visit_summaries (
                        summary_id VARCHAR(64) PRIMARY KEY,
                        user_id VARCHAR(64) NOT NULL,
                        visit_date DATE,
                        summary_content TEXT,
                        diagnosis TEXT,
                        prescription JSONB,
                        hospital VARCHAR(255),
                        advice TEXT,
                        original_text TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("""
                    INSERT INTO visit_summaries
                    (summary_id, user_id, visit_date, summary_content, diagnosis, prescription, hospital, advice, original_text)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    summary_id,
                    user_id,
                    structured_data["visit_date"],
                    json.dumps(structured_data, ensure_ascii=False),  # Summary content as JSON for now
                    structured_data["diagnosis"],
                    json.dumps(structured_data["prescription"], ensure_ascii=False),
                    structured_data["hospital"],
                    structured_data["advice"],
                    ocr_text
                ))
                conn.commit()

        return VisitSummaryResponse(
            summary_id=summary_id,
            visit_date=structured_data["visit_date"],
            hospital=structured_data["hospital"],
            diagnosis=structured_data["diagnosis"],
            prescription=structured_data["prescription"],
            advice=structured_data["advice"],
            original_text=ocr_text
        )

    except Exception as e:
        logger.error(f"Error processing visit record: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        limiter.release()


@router.get("/list")
async def list_visit_summaries(user_id: str):
    """
    List all visit summaries for a user.
    """
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT summary_id, visit_date, hospital, diagnosis, prescription, advice, original_text
                FROM visit_summaries
                WHERE user_id = %s
                ORDER BY visit_date DESC
            """, (user_id,))
            rows = cur.fetchall()

            results = []
            for row in rows:
                # Handle prescription being JSONB or string
                presc = row.get("prescription")
                if isinstance(presc, str):
                    try:
                        presc = json.loads(presc)
                    except Exception:
                        presc = []
                elif not presc:
                    presc = []

                results.append({
                    "summary_id": row["summary_id"],
                    "visit_date": str(row["visit_date"]),
                    "hospital": row["hospital"],
                    "diagnosis": row["diagnosis"],
                    "prescription": presc,
                    "advice": row["advice"],
                    "original_text": row["original_text"]
                })
            return {"data": results}

# === Health Trends API ===


@router.get("/trends")
async def get_health_trends(user_id: str, feature: str, days: int = 90):
    """
    Get health trends for a specific feature (e.g., "blood_pressure", "headache").
    """
    # Import AIAnalysisTool if possible to reuse logic, but for API speed we might query DB directly
    # The existing ai_analysis_tool.py takes a list of visits.
    # We will query health_records and extract values.

    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Query health records that might contain this feature
            # This is a simplified search. In production, use vector search or structured extraction.
            cur.execute("""
                SELECT record_date, content, metadata
                FROM health_records
                WHERE user_id = %s
                AND (content LIKE %s OR metadata::text LIKE %s)
                ORDER BY record_date ASC
            """, (user_id, f"%{feature}%", f"%{feature}%"))

            rows = cur.fetchall()

            data_points = []
            for row in rows:
                date_val = row["record_date"] or row.get("created_at")
                if not date_val:
                    continue

                text = (row["content"] or "") + " " + str(row["metadata"] or "")
                metadata = row.get("metadata") or {}
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = {}
                extracted = metadata.get("extracted_info") or metadata.get("extracted_data") or {}
                if isinstance(extracted, str):
                    try:
                        extracted = json.loads(extracted)
                    except Exception:
                        extracted = {}
                tests = None
                if isinstance(extracted, dict):
                    tests = extracted.get("test_results") or extracted.get("tests")
                if not tests and extract_test_results:
                    tests = extract_test_results(text)
                value = _extract_feature_value(feature, tests)
                if value is not None:
                    data_points.append({
                        "date": str(date_val),
                        "value": value
                    })

            return {
                "feature": feature,
                "data": data_points,
                "message": f"Found {len(data_points)} records for {feature}"
            }
