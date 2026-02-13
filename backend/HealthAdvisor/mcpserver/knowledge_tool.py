from mcp.server.fastmcp import FastMCP
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
_GLOBAL_KB_USER_ID = os.getenv("GLOBAL_KB_USER_ID", "__global__")

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


def _kb_user_ids(user_id: str, include_global: bool) -> List[str]:
    uid = (user_id or "").strip()
    if not uid:
        return [_GLOBAL_KB_USER_ID]
    if include_global and uid != _GLOBAL_KB_USER_ID:
        return [uid, _GLOBAL_KB_USER_ID]
    return [uid]


def _keyword_search_medical_kb(
    query: str,
    user_id: str,
    limit: int = 10,
    include_global: bool = True,
) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    limit = _coerce_limit(limit, default=10, max_limit=50)
    db = get_db_manager()
    _ensure_rag_schema(db)

    uids = _kb_user_ids(user_id, include_global=include_global)
    where_uid = " OR ".join(["user_id = %s"] * len(uids))
    params: List[Any] = []
    params.extend(uids)
    like = f"%{query}%"
    params.extend([like, like])
    params.append(limit)

    rows = db.execute_query(
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
                row_number() OVER (
                    PARTITION BY user_id, source_type, source_id
                    ORDER BY updated_at DESC, created_at DESC
                ) AS rn
            FROM rag_chunks
            WHERE ({where_uid})
              AND source_type = 'medical_kb'
              AND (COALESCE(title, '') ILIKE %s OR chunk_text ILIKE %s)
        ) t
        WHERE rn = 1
        ORDER BY updated_at DESC, created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "source": str(r.get("source_type")),
                "id": str(r.get("source_id")),
                "type": r.get("record_type"),
                "title": r.get("title"),
                "excerpt": _excerpt(r.get("chunk_text")),
                "created_at": str(r.get("created_at")),
                "score": None,
                "scope": (
                    "global"
                    if str(r.get("user_id")) == _GLOBAL_KB_USER_ID
                    else "user"
                ),
            }
        )
    return items


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
            UNIQUE (
                user_id, source_type, source_id, chunk_index, embedding_model
            )
        );
        """,
        """
        ALTER TABLE rag_chunks
        DROP CONSTRAINT IF EXISTS
            rag_chunks_source_type_source_id_chunk_index_embedding_model_key;
        """,
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
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user "
            "ON rag_chunks(user_id);"
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_user_source "
            "ON rag_chunks(user_id, source_type);"
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_source "
            "ON rag_chunks(source_type, source_id);"
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_created "
            "ON rag_chunks(created_at);"
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding "
            "ON rag_chunks "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
        ),
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
        dim = getattr(_embedding_service, "dimension", None)
        if dim is not None and int(dim) != _RAG_VECTOR_DIM:
            _embedding_service = None
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
    include_global: bool = True,
) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    user_id = (user_id or "").strip() or _GLOBAL_KB_USER_ID
    if not query:
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

    st = source_types or ["medical_kb"]
    placeholders = ",".join(["%s"] * len(st))
    qv = _vector_literal(q_emb)

    uids = _kb_user_ids(user_id, include_global=include_global)
    where_uid = "(" + " OR ".join(["user_id = %s"] * len(uids)) + ")"

    rows = db.execute_query(
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
                (embedding <=> %s::vector(384)) AS distance,
                row_number() OVER (
                    PARTITION BY user_id, source_type, source_id
                    ORDER BY (embedding <=> %s::vector(384)) ASC
                ) AS rn
            FROM rag_chunks
            WHERE {where_uid} AND source_type IN ({placeholders})
        ) t
        WHERE rn = 1
        ORDER BY distance ASC
        LIMIT %s
        """,
        tuple([qv, qv] + uids + st + [limit]),
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
                "scope": (
                    "global"
                    if str(r.get("user_id")) == _GLOBAL_KB_USER_ID
                    else "user"
                ),
            }
        )
    return items


def _kb_search(
    query: str, user_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    rag_items = _rag_search(
        query,
        user_id=user_id,
        limit=limit,
        source_types=["medical_kb"],
        include_global=True,
    )
    if rag_items:
        return rag_items[:limit]
    return _keyword_search_medical_kb(
        query, user_id=user_id, limit=limit, include_global=True
    )[:limit]


@mcp.tool()
def search_symptom_info(
    symptom: str, user_id: str = "", limit: int = 10
) -> Dict[str, Any]:
    symptom = (symptom or "").strip()
    limit = _coerce_limit(limit, default=10, max_limit=50)
    try:
        items = _kb_search(symptom, user_id=user_id, limit=limit)
        return {
            "status": "success",
            "query": symptom,
            "count": len(items),
            "items": items[:limit],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def search_medication_info(
    medication: str, user_id: str = "", limit: int = 10
) -> Dict[str, Any]:
    medication = (medication or "").strip()
    limit = _coerce_limit(limit, default=10, max_limit=50)
    try:
        items = _kb_search(medication, user_id=user_id, limit=limit)
        return {
            "status": "success",
            "query": medication,
            "count": len(items),
            "items": items[:limit],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def get_health_tips(category: str = "all") -> Dict[str, Any]:
    return {
        "status": "info",
        "message": "建议由模型生成或来源于真实数据分析，当前工具不再提供模拟建议。"
    }


@mcp.tool()
def analyze_health_concern(
    concern: str, symptoms: List[str] = None, user_id: str = ""
) -> Dict[str, Any]:
    symptoms = symptoms or []
    try:
        related = []
        for s in symptoms:
            res = search_symptom_info(s, user_id=user_id, limit=5)
            related.append(
                {
                    "symptom": s,
                    "hits": res.get("count", 0),
                    "samples": res.get("items", []),
                }
            )
        return {"status": "success", "concern": concern, "evidence": related}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    mcp.run()
