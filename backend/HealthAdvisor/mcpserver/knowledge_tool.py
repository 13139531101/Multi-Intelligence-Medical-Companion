from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, List, Any, Optional
import re
import sys
import os
# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database_config import get_db_manager
except ImportError:
    from HealthAdvisor.database_config import get_db_manager

mcp = FastMCP("HealthKnowledgeTool")

def _excerpt(text: Optional[str], width: int = 180) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", str(text))
    return t[:width]

@mcp.tool()
def search_symptom_info(symptom: str, user_id: str = "", limit: int = 10) -> Dict[str, Any]:
    symptom = symptom.strip()
    db = get_db_manager()
    results: List[Dict[str, Any]] = []
    try:
        where_uid = " AND user_id = %s" if user_id else ""
        # 健康档案检索
        rows_hr = db.execute_query(
            f"""
            SELECT id, user_id, record_type, title, summary, content, created_at
            FROM health_records
            WHERE (summary ILIKE %s OR content ILIKE %s){where_uid}
            ORDER BY created_at DESC
            LIMIT {limit}
            """,
            tuple([f"%{symptom}%", f"%{symptom}%"] + ([user_id] if user_id else []))
        )
        for r in rows_hr:
            results.append({
                "source": "health_records",
                "id": str(r.get("id")),
                "type": r.get("record_type"),
                "title": r.get("title"),
                "excerpt": _excerpt(r.get("summary") or r.get("content")),
                "created_at": str(r.get("created_at")),
            })
        # 咨询记录检索
        rows_cs = db.execute_query(
            f"""
            SELECT consultation_id, user_id, question, answer, created_at
            FROM consultations
            WHERE (question ILIKE %s OR answer ILIKE %s){where_uid}
            ORDER BY created_at DESC
            LIMIT {limit}
            """,
            tuple([f"%{symptom}%", f"%{symptom}%"] + ([user_id] if user_id else []))
        )
        for r in rows_cs:
            results.append({
                "source": "consultations",
                "id": str(r.get("consultation_id")),
                "title": _excerpt(r.get("question")),
                "excerpt": _excerpt(r.get("answer")),
                "created_at": str(r.get("created_at")),
            })
        return {"status": "success", "query": symptom, "count": len(results), "items": results[:limit]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def search_medication_info(medication: str, user_id: str = "", limit: int = 10) -> Dict[str, Any]:
    medication = medication.strip()
    db = get_db_manager()
    results: List[Dict[str, Any]] = []
    try:
        where_uid = " AND user_id = %s" if user_id else ""
        rows_mr = db.execute_query(
            f"""
            SELECT id, user_id, medication_name, dosage, frequency, reminder_times, is_active, start_date, end_date
            FROM medication_reminders
            WHERE medication_name ILIKE %s{where_uid}
            ORDER BY start_date DESC
            LIMIT {limit}
            """,
            tuple([f"%{medication}%"] + ([user_id] if user_id else []))
        )
        for r in rows_mr:
            results.append({
                "source": "medication_reminders",
                "id": str(r.get("id")),
                "medication_name": r.get("medication_name"),
                "dosage": r.get("dosage"),
                "frequency": r.get("frequency"),
                "reminder_times": r.get("reminder_times"),
                "is_active": r.get("is_active"),
                "period": f"{r.get('start_date')} ~ {r.get('end_date')}",
            })
        rows_hr = db.execute_query(
            f"""
            SELECT id, user_id, record_type, title, summary, content, created_at
            FROM health_records
            WHERE (summary ILIKE %s OR content ILIKE %s){where_uid}
            ORDER BY created_at DESC
            LIMIT {limit}
            """,
            tuple([f"%{medication}%", f"%{medication}%"] + ([user_id] if user_id else []))
        )
        for r in rows_hr:
            results.append({
                "source": "health_records",
                "id": str(r.get("id")),
                "type": r.get("record_type"),
                "title": r.get("title"),
                "excerpt": _excerpt(r.get("summary") or r.get("content")),
                "created_at": str(r.get("created_at")),
            })
        return {"status": "success", "query": medication, "count": len(results), "items": results[:limit]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def get_health_tips(category: str = "all") -> Dict[str, Any]:
    return {
        "status": "info",
        "message": "建议由模型生成或来源于真实数据分析，当前工具不再提供模拟建议。"
    }

@mcp.tool()
def analyze_health_concern(concern: str, symptoms: List[str] = None, user_id: str = "") -> Dict[str, Any]:
    db = get_db_manager()
    symptoms = symptoms or []
    try:
        related = []
        for s in symptoms:
            res = search_symptom_info(s, user_id=user_id, limit=5)
            related.append({"symptom": s, "hits": res.get("count", 0), "samples": res.get("items", [])})
        return {"status": "success", "concern": concern, "evidence": related}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    mcp.run()
