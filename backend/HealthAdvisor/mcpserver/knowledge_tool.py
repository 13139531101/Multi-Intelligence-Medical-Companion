from mcp.server.fastmcp import FastMCP
from typing import Dict, List, Any, Optional
import re
import sys
import os
import uuid
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


def _resolve_user_id(user_id: str) -> str:
    uid = (user_id or "").strip()
    if uid:
        return uid
    env_uid = os.getenv("A2A_CURRENT_USER_ID") or os.getenv("A2A_USER_ID") or ""
    return (env_uid or "").strip()


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


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _chunk_mode() -> str:
    v = (os.getenv("RAG_CHUNK_MODE", "") or "").strip().lower()
    if v in ("sliding", "window"):
        return "sliding"
    return "paragraph"


def _chunk_text_sliding(text: str, chunk_size: int, overlap: int) -> List[str]:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    chunk_size = max(50, int(chunk_size))
    overlap = max(0, int(overlap))
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)
    chunks: List[str] = []
    start = 0
    n = len(t)
    while start < n:
        end = min(n, start + chunk_size)
        chunk = t[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = end - overlap
        if start < 0:
            start = 0
        if chunks and start <= 0:
            start = end
    return chunks


def _chunk_text_paragraph(text: str, chunk_size: int, overlap: int) -> List[str]:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return []
    chunk_size = max(50, int(chunk_size))
    overlap = max(0, int(overlap))
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)

    paragraphs: List[str] = []
    buf: List[str] = []
    for line in s.split("\n"):
        if line.strip():
            buf.append(line.rstrip())
            continue
        if buf:
            paragraphs.append("\n".join(buf).strip())
            buf = []
    if buf:
        paragraphs.append("\n".join(buf).strip())

    chunks: List[str] = []
    prefix = ""
    current = ""

    def flush_current() -> None:
        nonlocal prefix, current
        c = (current or "").strip()
        if not c:
            current = prefix
            return
        chunks.append(c)
        prefix = c[-overlap:] if overlap else ""
        current = prefix

    for p in paragraphs:
        para = (p or "").strip()
        if not para:
            continue

        if len(para) > chunk_size:
            if (current or "").strip() and (current or "").strip() != (prefix or "").strip():
                flush_current()

            slices = _chunk_text_sliding(para, chunk_size=chunk_size, overlap=overlap)
            for idx, sl in enumerate(slices):
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
        chunks.append(tail)
    return chunks


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    if _chunk_mode() == "sliding":
        return _chunk_text_sliding(text, chunk_size=chunk_size, overlap=overlap)
    return _chunk_text_paragraph(text, chunk_size=chunk_size, overlap=overlap)


def _upsert_medical_kb_chunks(
    user_id: str,
    source_id: str,
    text: str,
    title: str = "",
    record_type: str = "",
    overwrite: bool = True,
) -> Dict[str, Any]:
    uid = (user_id or "").strip() or _GLOBAL_KB_USER_ID
    sid = (source_id or "").strip()
    if not sid:
        return {"status": "error", "message": "source_id 不能为空"}
    t = (text or "").strip()
    if not t:
        return {"status": "error", "message": "text 不能为空"}

    es = _get_embedding_service()
    if es is None:
        return {"status": "error", "message": "EmbeddingService 不可用"}

    chunk_size = _coerce_int(os.getenv("RAG_CHUNK_SIZE", "800"), 800)
    overlap = _coerce_int(os.getenv("RAG_CHUNK_OVERLAP", "120"), 120)
    max_chunks = _coerce_int(os.getenv("RAG_MAX_CHUNKS", "200"), 200)

    chunks = _chunk_text(t, chunk_size=chunk_size, overlap=overlap)
    if max_chunks > 0:
        chunks = chunks[:max_chunks]
    if not chunks:
        return {"status": "error", "message": "无法分块"}

    embeddings = es.generate_batch_embeddings(chunks)
    if not embeddings:
        return {"status": "error", "message": "生成嵌入失败"}

    db = get_db_manager()
    _ensure_rag_schema(db)

    if overwrite:
        db.execute_update(
            """
            DELETE FROM rag_chunks
            WHERE user_id = %s
              AND source_type = 'medical_kb'
              AND source_id = %s
              AND embedding_model = %s
            """,
            (uid, sid, _RAG_EMBEDDING_MODEL),
        )

    inserted = 0
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        if not emb or len(emb) != _RAG_VECTOR_DIM:
            continue
        qv = _vector_literal(emb)
        rid = str(uuid.uuid4())
        db.execute_update(
            """
            INSERT INTO rag_chunks (
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
                embedding,
                created_at,
                updated_at
            )
            VALUES (
                %s,
                %s,
                'medical_kb',
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s::vector(384),
                now(),
                now()
            )
            ON CONFLICT (
                user_id,
                source_type,
                source_id,
                chunk_index,
                embedding_model
            )
            DO UPDATE SET
                record_type = EXCLUDED.record_type,
                title = EXCLUDED.title,
                chunk_text = EXCLUDED.chunk_text,
                embedding_dim = EXCLUDED.embedding_dim,
                embedding = EXCLUDED.embedding,
                updated_at = now()
            """,
            (
                rid,
                uid,
                sid,
                (record_type or "").strip() or None,
                (title or "").strip() or None,
                int(idx),
                chunk,
                _RAG_EMBEDDING_MODEL,
                int(_RAG_VECTOR_DIM),
                qv,
            ),
        )
        inserted += 1

    return {
        "status": "success",
        "user_id": uid,
        "source_id": sid,
        "chunks": len(chunks),
        "inserted": inserted,
        "embedding_model": _RAG_EMBEDDING_MODEL,
        "embedding_dim": _RAG_VECTOR_DIM,
    }


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
    uid = _resolve_user_id(user_id)
    rag_items = _rag_search(
        query,
        user_id=uid,
        limit=limit,
        source_types=["health_records", "visit_summaries", "medical_kb"],
        include_global=True,
    )
    if rag_items:
        return rag_items[:limit]
    return _keyword_search_medical_kb(
        query, user_id=uid, limit=limit, include_global=True
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


@mcp.tool()
def upsert_medical_kb_document(
    source_id: str,
    text: str,
    title: str = "",
    record_type: str = "",
    user_id: str = "",
    overwrite: bool = True,
) -> Dict[str, Any]:
    try:
        return _upsert_medical_kb_chunks(
            user_id=user_id,
            source_id=source_id,
            text=text,
            title=title,
            record_type=record_type,
            overwrite=overwrite,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def delete_medical_kb_document(
    source_id: str, user_id: str = "", embedding_model: str = ""
) -> Dict[str, Any]:
    uid = (user_id or "").strip() or _GLOBAL_KB_USER_ID
    sid = (source_id or "").strip()
    if not sid:
        return {"status": "error", "message": "source_id 不能为空"}
    model = (embedding_model or "").strip() or _RAG_EMBEDDING_MODEL
    try:
        db = get_db_manager()
        _ensure_rag_schema(db)
        affected = db.execute_update(
            """
            DELETE FROM rag_chunks
            WHERE user_id = %s
              AND source_type = 'medical_kb'
              AND source_id = %s
              AND embedding_model = %s
            """,
            (uid, sid, model),
        )
        return {
            "status": "success",
            "user_id": uid,
            "source_id": sid,
            "deleted": int(affected or 0),
            "embedding_model": model,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def list_medical_kb_documents(user_id: str = "", limit: int = 50) -> Dict[str, Any]:
    uid = (user_id or "").strip() or _GLOBAL_KB_USER_ID
    limit = _coerce_limit(limit, default=50, max_limit=200)
    try:
        db = get_db_manager()
        _ensure_rag_schema(db)
        rows = db.execute_query(
            """
            SELECT
                source_id,
                max(updated_at) AS updated_at,
                max(created_at) AS created_at,
                max(title) AS title,
                max(record_type) AS record_type,
                count(*) AS chunks
            FROM rag_chunks
            WHERE user_id = %s AND source_type = 'medical_kb'
            GROUP BY source_id
            ORDER BY max(updated_at) DESC NULLS LAST
            LIMIT %s
            """,
            (uid, limit),
        )
        items: List[Dict[str, Any]] = []
        for r in rows:
            items.append(
                {
                    "source_id": str(r.get("source_id")),
                    "title": r.get("title"),
                    "record_type": r.get("record_type"),
                    "chunks": int(r.get("chunks") or 0),
                    "updated_at": str(r.get("updated_at")),
                    "created_at": str(r.get("created_at")),
                }
            )
        return {
            "status": "success",
            "user_id": uid,
            "count": len(items),
            "items": items,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    mcp.run()
