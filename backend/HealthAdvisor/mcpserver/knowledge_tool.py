from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, List, Any, Optional
import re
import sys
import os
# Add parent directory to sys.path
_ha_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ha_dir not in sys.path:
    sys.path.append(_ha_dir)
_backend_dir = os.path.dirname(_ha_dir)
if _backend_dir not in sys.path:
    sys.path.append(_backend_dir)

try:
    from database_config import get_db_manager
except ImportError:
    from HealthAdvisor.database_config import get_db_manager

try:
    from embedding_manager import EmbeddingService
except Exception:
    EmbeddingService = None  # type: ignore

mcp = FastMCP("HealthKnowledgeTool")

_RAG_VECTOR_DIM = int(os.getenv("RAG_VECTOR_DIM", "384"))
_RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL") or os.getenv(
    "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)

_embedding_service: Any = None

def _coerce_limit(value: Any, default: int = 10, max_limit: int = 50) -> int:
    try:
        n = int(value)
    except Exception:
        n = int(default)
    if n < 1:
        n = 1
    if n > max_limit:
        n = max_limit
    return n

def _excerpt(text: Optional[str], width: int = 180) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", str(text))
    return t[:width]

def _ensure_rag_schema(db) -> None:
    stmts = [
        "CREATE EXTENSION IF NOT EXISTS vector;",
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user ON rag_chunks(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user_source ON rag_chunks(user_id, source_type);",
        "CREATE INDEX IF NOT EXISTS idx_rag_chunks_source ON rag_chunks(source_type, source_id);",
        "CREATE INDEX IF NOT EXISTS idx_rag_chunks_created ON rag_chunks(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);",
    ]
    for s in stmts:
        try:
            db.execute_update(s)
        except Exception:
            pass

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

def _vector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"

def _rag_search(
    query: str,
    user_id: str,
    limit: int = 10,
    source_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    user_id = (user_id or "").strip()
    if not query or not user_id:
        return []
    limit = _coerce_limit(limit, default=10, max_limit=50)

    es = _get_embedding_service()
    if es is None:
        return []

    q_emb = es.generate_embedding(query)
    if not q_emb:
        return []
    if len(q_emb) != _RAG_VECTOR_DIM:
        return []

    db = get_db_manager()
    _ensure_rag_schema(db)

    st = source_types or ["health_records", "visit_summaries"]
    placeholders = ",".join(["%s"] * len(st))
    qv = _vector_literal(q_emb)
    rows = db.execute_query(
        f"""
        SELECT *
        FROM (
            SELECT
                source_type,
                source_id,
                record_type,
                title,
                chunk_text,
                created_at,
                (embedding <=> %s::vector(384)) AS distance,
                row_number() OVER (
                    PARTITION BY source_type, source_id
                    ORDER BY (embedding <=> %s::vector(384)) ASC
                ) AS rn
            FROM rag_chunks
            WHERE user_id = %s AND source_type IN ({placeholders})
        ) t
        WHERE rn = 1
        ORDER BY distance ASC
        LIMIT %s
        """,
        tuple([qv, qv, user_id] + st + [limit]),
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        dist = r.get("distance")
        score = None
        try:
            if dist is not None:
                score = max(0.0, min(1.0, 1.0 - float(dist)))
        except Exception:
            score = None
        items.append(
            {
                "source": str(r.get("source_type")),
                "id": str(r.get("source_id")),
                "type": r.get("record_type"),
                "title": r.get("title"),
                "excerpt": _excerpt(r.get("chunk_text")),
                "created_at": str(r.get("created_at")),
                "score": score,
            }
        )
    return items

@mcp.tool()
def search_symptom_info(symptom: str, user_id: str = "", limit: int = 10) -> Dict[str, Any]:
    symptom = (symptom or "").strip()
    limit = _coerce_limit(limit, default=10, max_limit=50)
    db = get_db_manager()
    results: List[Dict[str, Any]] = []
    try:
        rag_items = _rag_search(symptom, user_id=user_id, limit=limit)
        if rag_items:
            return {
                "status": "success",
                "query": symptom,
                "count": len(rag_items),
                "items": rag_items[:limit],
            }

        where_uid = " AND user_id = %s" if user_id else ""
        # 健康档案检索
        rows_hr = db.execute_query(
            f"""
            SELECT id, user_id, record_type, title, summary, content, created_at
            FROM health_records
            WHERE (summary ILIKE %s OR content ILIKE %s){where_uid}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(
                [f"%{symptom}%", f"%{symptom}%"]
                + ([user_id] if user_id else [])
                + [limit]
            )
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
            LIMIT %s
            """,
            tuple(
                [f"%{symptom}%", f"%{symptom}%"]
                + ([user_id] if user_id else [])
                + [limit]
            )
        )
        for r in rows_cs:
            results.append({
                "source": "consultations",
                "id": str(r.get("consultation_id")),
                "title": _excerpt(r.get("question")),
                "excerpt": _excerpt(r.get("answer")),
                "created_at": str(r.get("created_at")),
            })

        rows_vs = db.execute_query(
            f"""
            SELECT id, user_id, title, visit_date, diagnosis, summary_content, notes, created_at
            FROM visit_summaries
            WHERE (title ILIKE %s OR diagnosis ILIKE %s OR summary_content ILIKE %s OR notes ILIKE %s){where_uid}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(
                [f"%{symptom}%"] * 4 + ([user_id] if user_id else []) + [limit]
            ),
        )
        for r in rows_vs:
            results.append(
                {
                    "source": "visit_summaries",
                    "id": str(r.get("id")),
                    "title": r.get("title"),
                    "excerpt": _excerpt(r.get("summary_content") or r.get("notes") or r.get("diagnosis")),
                    "created_at": str(r.get("created_at")),
                }
            )
        return {"status": "success", "query": symptom, "count": len(results), "items": results[:limit]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def search_medication_info(medication: str, user_id: str = "", limit: int = 10) -> Dict[str, Any]:
    medication = (medication or "").strip()
    limit = _coerce_limit(limit, default=10, max_limit=50)
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
            LIMIT %s
            """,
            tuple([f"%{medication}%"] + ([user_id] if user_id else []) + [limit])
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

        rag_items = _rag_search(medication, user_id=user_id, limit=limit)
        results.extend(rag_items)

        rows_hr = db.execute_query(
            f"""
            SELECT id, user_id, record_type, title, summary, content, created_at
            FROM health_records
            WHERE (summary ILIKE %s OR content ILIKE %s){where_uid}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(
                [f"%{medication}%", f"%{medication}%"]
                + ([user_id] if user_id else [])
                + [limit]
            )
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
