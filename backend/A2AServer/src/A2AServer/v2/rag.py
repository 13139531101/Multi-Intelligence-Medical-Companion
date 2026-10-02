"""
PHA v2 RAG 索引 / 检索 / 反馈（阶段21）

架构（3 表）：
  rag_documents    - 文档元信息（user_id + source_type + source_id + text + chunk_count）
  rag_chunks       - 文档切片（chunk_text + embedding vector(384) + ivfflat 索引）
  memory_embeddings - 用户级长期记忆（memory_id + jsonb vector）

功能：
  - index_document()  把文档分块 → Embedding → 写 rag_chunks
  - search()         语义检索（cosine 距离 top-K）
  - add_feedback()   用户反馈（点赞/点踩 → 调整 retrieval 权重）
  - recall_for_user() 拿用户相关的文档 + 长期记忆
  - chunk_text()     简单段落切分（按句号 / 长度）

依赖：
  - pgvector（rag_chunks.embedding vector(384)）
  - Embedding model：DASHSCOPE text-embedding-v4（已有，dim=384）
  - psycopg 直接连 postgres
"""
import os
import re
import time
import json
import hashlib
import logging
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "dashscope")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
DASHSCOPE_API_KEY = os.getenv("EMBEDDING_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))

# Postgres（每次读取 env，避免 import 时固定导致测试错位 host）
def _db_host():
    return os.getenv("DB_HOST", "localhost")
def _db_port():
    return int(os.getenv("DB_PORT", "5432"))
def _db_user():
    return os.getenv("DB_USER", "pha")
def _db_password():
    return os.getenv("DB_PASSWORD", "")
def _db_name():
    return os.getenv("DB_NAME", "personal_health_assistant")

# RAG 参数
DEFAULT_CHUNK_SIZE = int(os.getenv("PHA_RAG_CHUNK_SIZE", "200"))  # 字符
DEFAULT_CHUNK_OVERLAP = int(os.getenv("PHA_RAG_CHUNK_OVERLAP", "30"))
DEFAULT_TOP_K = int(os.getenv("PHA_RAG_TOP_K", "5"))
MIN_SIM_THRESHOLD = float(os.getenv("PHA_RAG_MIN_SIM", "0.5"))  # cosine 相似度阈值


# ============================================================
# 数据结构
# ============================================================
@dataclass
class Chunk:
    """一个文档切片"""
    index: int
    text: str
    embedding: List[float] = field(default_factory=list)


@dataclass
class SearchResult:
    """一个检索结果"""
    chunk_id: str
    user_id: str
    source_type: str
    source_id: str
    record_type: str
    title: str
    chunk_index: int
    chunk_text: str
    score: float  # 1 - distance
    feedback_score: float = 0.0  # 用户反馈加权


@dataclass
class FeedbackEntry:
    """用户反馈"""
    user_id: str
    chunk_id: str
    query: str
    score_delta: float  # +1 点赞 / -1 点踩


# ============================================================
# 文本分块（简单段落切分）
# ============================================================
def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    """
    简单段落切分：
    1. 先按句号/分号/换行切分
    2. 太短就合并
    3. 太长就按字符切
    """
    if not text or not text.strip():
        return []
    # 第一遍：按自然边界切（中英文标点 + 换行）
    pieces = re.split(r"[。！？；\.\!\?\;]+|\n+", text.strip())
    pieces = [p.strip() for p in pieces if p and p.strip()]
    # 第二遍：合并 + 切
    chunks: List[str] = []
    buf = ""
    for p in pieces:
        if len(buf) + len(p) <= chunk_size:
            buf = (buf + " " + p).strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
            # p 本身太长就按字符切
            if len(p) > chunk_size:
                for i in range(0, len(p), chunk_size - overlap):
                    chunks.append(p[i:i + chunk_size])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


# ============================================================
# Embedding 客户端
# ============================================================
class EmbeddingClient:
    """DashScope text-embedding-v4 客户端"""

    def __init__(self):
        self._api_base = EMBEDDING_API_BASE
        self._api_key = DASHSCOPE_API_KEY
        self._model = EMBEDDING_MODEL
        self._dim = EMBEDDING_DIM

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """批量 embed"""
        if not texts:
            return []
        if not self._api_key:
            raise ValueError("DASHSCOPE_API_KEY not set")
        # DashScope 兼容 OpenAI 格式
        # text-embedding-v3/v4 支持 dimensions 参数，可输出 384
        body = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }
        if "v3" in self._model or "v4" in self._model:
            body["dimensions"] = self._dim
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self._api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            return [item["embedding"] for item in data["data"]]

    async def embed_one(self, text: str) -> List[float]:
        """单条 embed"""
        result = await self.embed([text])
        return result[0] if result else []


# ============================================================
# Postgres 连接（简单版，连接池可后续优化）
# ============================================================
def _conn_str() -> str:
    return f"postgresql://{_db_user()}:{_db_password()}@{_db_host()}:{_db_port()}/{_db_name()}"


def _to_pgvector(vec: List[float]) -> str:
    """List[float] → '[v1,v2,...]'"""
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


def _from_pgvector(s: str) -> List[float]:
    """'[v1,v2,...]' → List[float]"""
    s = s.strip("[]")
    return [float(x) for x in s.split(",")]


# ============================================================
# RAG 主类
# ============================================================
class RAGStore:
    """RAG 索引 / 检索主类（单例）"""

    def __init__(self):
        self._embed = EmbeddingClient()
        # 反馈存储（in-memory，生产可落库）
        self._feedback: Dict[str, float] = {}  # chunk_id -> cumulative score

    def get_connection(self):
        """拿一个 psycopg 连接（调用方负责 close）"""
        import psycopg
        return psycopg.connect(_conn_str())

    # ---------- 索引 ----------
    async def index_document(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        text: str,
        record_type: str = "",
        title: str = "",
        with_kg: bool = True,
    ) -> dict:
        """
        索引一个文档：
        1. 文本分块
        2. Embedding
        3. UPSERT 到 rag_documents
        4. INSERT 到 rag_chunks（先删后插）
        """
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # 检查是否已索引（正文 sha 一致**且**元数据一致才跳过）
        #
        # 阶段48-fix: 原来只比 text_sha256。但 record_type / title 是落在
        # rag_chunks 行上的, 而 magnetic_rag 的多跳检索**按 record_type 精确过滤**
        # (RECORD_TYPE_TO_DB_TYPE: blood_pressure→vital_signs 等)。
        # 用户在界面上把一条档案从"慢性病管理"改判成 vital_signs 时正文没变,
        # 若这里只看 sha 就直接 return, 该档案会永远留在旧类型下 —— 正文检索还能
        # 命中, 类型化检索则彻底隐身, 且没有任何报错。所以元数据变了必须重索引。
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT text_sha256, record_type, title FROM rag_documents WHERE user_id=%s AND source_type=%s AND source_id=%s AND embedding_model=%s",
                    (user_id, source_type, source_id, EMBEDDING_MODEL),
                )
                row = cur.fetchone()
                if row and row[0] == sha:
                    same_meta = (row[1] or "") == (record_type or "") and (
                        row[2] or ""
                    ) == (title or "")
                    if same_meta:
                        return {"skipped": True, "reason": "already indexed", "sha256": sha}
                # 删旧 chunks（只删本模型写的, 否则会把 HealthAdvisor 那套
                # all-MiniLM-L6-v2 的 chunk 一并清掉 —— 跨栈误删）
                cur.execute(
                    "DELETE FROM rag_chunks WHERE user_id=%s AND source_type=%s AND source_id=%s AND embedding_model=%s",
                    (user_id, source_type, source_id, EMBEDDING_MODEL),
                )

        # 分块
        pieces = chunk_text(text)
        if not pieces:
            return {"skipped": True, "reason": "empty text", "sha256": sha}

        # Embedding（批量）
        embeddings = await self._embed.embed(pieces)

        chunk_ids: List[str] = []

        # 写库
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # UPSERT doc
                cur.execute(
                    """
                    INSERT INTO rag_documents (user_id, source_type, source_id, record_type, title, full_text, text_sha256, embedding_model, embedding_dim, chunk_count, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                    ON CONFLICT (user_id, source_type, source_id, embedding_model)
                    DO UPDATE SET
                        record_type = EXCLUDED.record_type,
                        title = EXCLUDED.title,
                        full_text = EXCLUDED.full_text,
                        text_sha256 = EXCLUDED.text_sha256,
                        embedding_dim = EXCLUDED.embedding_dim,
                        chunk_count = EXCLUDED.chunk_count,
                        updated_at = now()
                    """,
                    (user_id, source_type, source_id, record_type, title, text, sha, EMBEDDING_MODEL, EMBEDDING_DIM, len(pieces)),
                )
                # 写 chunks（RETURNING id 供后续 KG 关联使用）
                for i, (piece, emb) in enumerate(zip(pieces, embeddings)):
                    cur.execute(
                        """
                        INSERT INTO rag_chunks (user_id, source_type, source_id, record_type, title, chunk_index, chunk_text, embedding_model, embedding_dim, embedding, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, now(), now())
                        RETURNING id
                        """,
                        (user_id, source_type, source_id, record_type, title, i, piece, EMBEDDING_MODEL, EMBEDDING_DIM, _to_pgvector(emb)),
                    )
                    _row = cur.fetchone()
                    if _row:
                        chunk_ids.append(str(_row[0]))
            conn.commit()

        # 阶段48-p3: 激活知识图谱链路。
        # index_document_with_kg 此前【没有任何调用方】→ kg_entities / kg_relations
        # 永远是空表 → magnetic_rag 的图扩展 (get_chunks_for_entities) 恒为 no-op,
        # 多跳检索退化成普通向量检索。这里在 chunk 落库后补上这一次调用。
        kg_result: dict = {"kg_indexed": False, "reason": "disabled"}
        if with_kg and chunk_ids:
            try:
                from .knowledge_graph import index_document_with_kg
                kg_result = await index_document_with_kg(
                    user_id=user_id,
                    source_type=source_type,
                    source_id=source_id,
                    chunk_ids=chunk_ids,
                    text=text,
                )
            except Exception as e:
                # KG 是增强项, 失败不能影响主索引链路
                logger.warning("[rag] KG 索引失败(已忽略): %s", e)
                kg_result = {"kg_indexed": False, "reason": str(e)}

        return {
            "indexed": True,
            "chunk_count": len(pieces),
            "sha256": sha,
            "embedding_model": EMBEDDING_MODEL,
            "kg": kg_result,
        }

    # ---------- 检索 ----------
    async def search(
        self,
        user_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_SIM_THRESHOLD,
        source_type: str = None,
        record_type: str = None,
    ) -> List[SearchResult]:
        """
        语义检索：
        1. Embedding query
        2. pgvector cosine 距离 top-K
        3. 过滤 < min_score
        4. 加 feedback 加权
        """
        if not query or not query.strip():
            return []
        q_emb = await self._embed.embed_one(query)
        if not q_emb:
            return []
        q_vec = _to_pgvector(q_emb)
        # 修复: rag_chunks 是「两套栈共写」的同一张表 —— v2 主链路写
        # text-embedding-v4, HealthAdvisor/mcpserver/knowledge_tool.py 写
        # all-MiniLM-L6-v2。此前 SQL 不按 embedding_model 过滤, 两个不同向量
        # 空间的 embedding 一起算 cosine 距离, 排序结果被随机污染。
        # 只召回与查询同模型的 chunk。
        sql = """
            SELECT id, user_id, source_type, source_id, record_type, title,
                   chunk_index, chunk_text,
                   1 - (embedding <=> %s::vector) AS score
            FROM rag_chunks
            WHERE user_id = %s
              AND embedding_model = %s
        """
        params = [q_vec, user_id, EMBEDDING_MODEL]
        if source_type:
            sql += " AND source_type = %s"
            params.append(source_type)
        if record_type:
            sql += " AND record_type = %s"
            params.append(record_type)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([q_vec, top_k * 2])  # 取 2 倍再过滤

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        # 反馈分批量从 rag_feedback 表读（阶段48-p3: 此前只读进程内 dict）
        fb_map = self._load_feedback_map(user_id, [str(r[0]) for r in rows])

        results: List[SearchResult] = []
        for r in rows:
            score = float(r[8])
            if score < min_score:
                continue
            chunk_id = str(r[0])
            fb = fb_map.get(chunk_id, 0.0)
            # 加权：score * (1 + 0.2*fb)
            final_score = score * (1.0 + 0.2 * fb)
            results.append(SearchResult(
                chunk_id=chunk_id,
                user_id=r[1],
                source_type=r[2],
                source_id=r[3],
                record_type=r[4] or "",
                title=r[5] or "",
                chunk_index=r[6],
                chunk_text=r[7],
                score=score,
                feedback_score=fb,
            ))
        # 用 final_score 重排
        results.sort(key=lambda x: x.score * (1 + 0.2 * x.feedback_score), reverse=True)
        return results[:top_k]

    # ---------- 反馈 ----------
    def add_feedback(self, user_id: str, chunk_id: str, query: str, score_delta: float) -> None:
        """加反馈（+1 点赞 / -1 点踩）

        阶段48-p3: 落库到 rag_feedback 表。此前只写进程内 dict（`self._feedback`），
        服务一重启反馈就全丢 —— 而 migrations/crag_tables.sql 早就建好了这张表。
        内存 dict 保留为写库失败时的降级缓存。
        """
        self._feedback[chunk_id] = self._feedback.get(chunk_id, 0.0) + score_delta
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO rag_feedback (user_id, chunk_id, query, score_delta, created_at)
                        VALUES (%s, %s, %s, %s, now())
                        ON CONFLICT (user_id, chunk_id, query)
                        DO UPDATE SET score_delta = rag_feedback.score_delta + EXCLUDED.score_delta
                        """,
                        (user_id, chunk_id, query, score_delta),
                    )
                conn.commit()
        except Exception as e:
            logger.warning("[rag] 反馈落库失败(已降级为内存缓存): %s", e)
        logger.info(f"[rag] feedback user={user_id} chunk={chunk_id[:8]} delta={score_delta} total={self._feedback[chunk_id]}")

    def _load_feedback_map(self, user_id: str, chunk_ids: List[str]) -> Dict[str, float]:
        """从 rag_feedback 表批量读回 chunk 的累计反馈分（失败则退回内存 dict）"""
        if not chunk_ids:
            return {}
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT chunk_id, SUM(score_delta)
                        FROM rag_feedback
                        WHERE user_id = %s AND chunk_id = ANY(%s::text[])
                        GROUP BY chunk_id
                        """,
                        (user_id, chunk_ids),
                    )
                    return {str(r[0]): float(r[1] or 0.0) for r in cur.fetchall()}
        except Exception as e:
            logger.warning("[rag] 反馈读取失败(已降级为内存缓存): %s", e)
            return {cid: self._feedback.get(cid, 0.0) for cid in chunk_ids}

    # ---------- 召回 ----------
    async def recall_for_user(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
    ) -> dict:
        """
        召回 = RAG top-K + memory 最新 N
        """
        rag_results = await self.search(user_id, query, top_k=top_k)
        # 长期记忆（暂用 rag_chunks 模拟，存 source_type='memory'）
        return {
            "query": query,
            "rag_count": len(rag_results),
            "rag_chunks": [
                {
                    "chunk_id": r.chunk_id,
                    "score": round(r.score, 4),
                    "title": r.title,
                    "source": f"{r.source_type}/{r.source_id}",
                    "text": r.chunk_text[:200],
                }
                for r in rag_results
            ],
        }

    # ---------- 统计 ----------
    def stats(self) -> dict:
        # 只统计本模型的行 —— rag_chunks 是两套栈共写的, 不加过滤会把
        # HealthAdvisor 那套 all-MiniLM-L6-v2 的数据也算进来, 数字对不上
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM rag_documents WHERE embedding_model = %s",
                    (EMBEDDING_MODEL,),
                )
                doc_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM rag_chunks WHERE embedding_model = %s",
                    (EMBEDDING_MODEL,),
                )
                chunk_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(DISTINCT user_id) FROM rag_chunks WHERE embedding_model = %s",
                    (EMBEDDING_MODEL,),
                )
                user_count = cur.fetchone()[0]
                # 阶段48-p3: 反馈已落库, 用表里的真实条数（内存 dict 只是缓存）
                try:
                    cur.execute("SELECT COUNT(*) FROM rag_feedback")
                    feedback_count = cur.fetchone()[0]
                except Exception:
                    feedback_count = len(self._feedback)
        return {
            "doc_count": doc_count,
            "chunk_count": chunk_count,
            "user_count": user_count,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
            "feedback_count": feedback_count,
            "config": {
                "chunk_size": DEFAULT_CHUNK_SIZE,
                "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
                "top_k": DEFAULT_TOP_K,
                "min_sim": MIN_SIM_THRESHOLD,
            },
        }


# ============================================================
# 单例
# ============================================================
_instance: Optional[RAGStore] = None


def get_rag_store() -> RAGStore:
    global _instance
    if _instance is None:
        _instance = RAGStore()
    return _instance
