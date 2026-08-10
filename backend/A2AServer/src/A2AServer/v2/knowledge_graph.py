"""
PHA v2 Knowledge Graph — Stage 3

从健康档案中抽取实体+关系，构建知识图谱，检索时图扩展弥补向量相似不足。

实体类型（复用 PHAEntityMemory taxonomy）：
    symptom / medication / disease / allergy / vital_sign

关系类型：
    TREATS（药物治疗） / CAUSES（引起） / MEASURES（测量）
    CO_OCCURS（共现） / PRECEDES（先于） / FOLLOWS（后于）

索引时：文档 chunk → LLM 实体关系抽取 → kg_entities + kg_relations
检索时：query → 抽取查询实体 → 图扩展1-2跳 → 向量检索扩展候选集
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
KG_ENTITY_TYPES = ["symptom", "medication", "disease", "allergy", "vital_sign"]
KG_RELATION_TYPES = ["TREATS", "CAUSES", "MEASURES", "CO_OCCURS", "PRECEDES", "FOLLOWS"]

# ============================================================
# 数据结构
# ============================================================
@dataclass
class KGEntity:
    entity_id: str
    user_id: str
    entity_type: str          # symptom / medication / disease / allergy / vital_sign
    entity_name: str          # 原始提及文本
    canonical_name: str       # 标准化名称
    aliases: List[str] = field(default_factory=list)
    mention_count: int = 1
    metadata_json: str = ""   # JSON，存额外属性（如血压的"收缩压/舒张压"数值）


@dataclass
class KGRelation:
    relation_id: str
    user_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str        # TREATS / CAUSES / MEASURES / CO_OCCURS / PRECEDES / FOLLOWS
    confidence: float = 1.0   # 0.0-1.0
    evidence: str = ""        # 支持该关系的原文片段
    created_at: str = ""


# ============================================================
# LLM 客户端
# ============================================================
def _get_llm():
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.getenv("PHA_LLM_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0,
        )
    except Exception as e:
        logger.warning("[kg] LLM 不可用: %s", e)
        return None


# ============================================================
# Schema 初始化（幂等）
# ============================================================
_ENSURE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kg_entities (
    entity_id     VARCHAR(64) PRIMARY KEY,
    user_id       VARCHAR(64) NOT NULL,
    entity_type   VARCHAR(32) NOT NULL,
    entity_name   TEXT        NOT NULL,
    canonical_name TEXT       NOT NULL,
    aliases       TEXT        DEFAULT '[]',   -- JSON list
    mention_count INTEGER     DEFAULT 1,
    first_seen    TIMESTAMPTZ DEFAULT now(),
    last_seen     TIMESTAMPTZ DEFAULT now(),
    metadata_json TEXT        DEFAULT '{}',   -- JSON
    UNIQUE(user_id, entity_type, canonical_name)
);

CREATE TABLE IF NOT EXISTS kg_relations (
    relation_id     VARCHAR(64) PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    source_entity_id VARCHAR(64) NOT NULL,
    target_entity_id VARCHAR(64) NOT NULL,
    relation_type   VARCHAR(32) NOT NULL,
    confidence      FLOAT       DEFAULT 1.0,
    evidence        TEXT        DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, source_entity_id, target_entity_id, relation_type)
);

CREATE TABLE IF NOT EXISTS kg_entity_chunks (
    entity_id    VARCHAR(64) NOT NULL,
    chunk_id     VARCHAR(64) NOT NULL,
    user_id      VARCHAR(64) NOT NULL,
    PRIMARY KEY (entity_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_entities_user_type ON kg_entities(user_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_canonical  ON kg_entities(user_id, canonical_name);
CREATE INDEX IF NOT EXISTS idx_kg_relations_user      ON kg_relations(user_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_expand    ON kg_relations(user_id, source_entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_entity_chunks_entity ON kg_entity_chunks(entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_entity_chunks_chunk  ON kg_entity_chunks(chunk_id);
"""


def ensure_kg_schema(conn) -> None:
    """确保知识图谱表存在（幂等）"""
    with conn.cursor() as cur:
        cur.execute(_ENSURE_SCHEMA_SQL)
    conn.commit()


# ============================================================
# 实体抽取（LLM-based）
# ============================================================
async def extract_entities_and_relations(
    text: str,
    user_id: str,
    chunk_id: str,
) -> tuple[List[KGEntity], List[KGRelation]]:
    """
    用 LLM 从文本中抽取实体和关系。

    Returns:
        (entities, relations) 列表
    """
    llm = _get_llm()
    if llm is None:
        return [], []

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个医学实体关系抽取专家。从给定文本中抽取实体和关系。

文本：
{text[:1000]}

实体类型定义：
- symptom: 症状描述（头晕、胸闷、呼吸困难、疲劳）
- medication: 药物名称（苯磺酸氨氯地平、阿司匹林、二甲双胍）
- disease: 疾病名称（高血压、糖尿病、冠心病）
- allergy: 过敏原（青霉素、花粉、虾）
- vital_sign: 生命体征指标（血压、血糖、心率、体温）

关系类型定义：
- TREATS: 药物治疗疾病/症状（"氨氯地平治疗高血压"）
- CAUSES: 引起（"高血压引起头晕"）
- MEASURES: 测量（"测量血压"中的血压是 vital_sign）
- CO_OCCURS: 共现（"高血压患者常伴有糖尿病"）
- PRECEDES: 时间先于（"用药后血压下降"）
- FOLLOWS: 时间后于

输出 JSON 格式（无其他内容）：
{{
  "entities": [
    {{"entity_type": "medication", "entity_name": "苯磺酸氨氯地平", "canonical_name": "氨氯地平", "aliases": ["络活喜"], "metadata": {{}}}}
  ],
  "relations": [
    {{"source": "苯磺酸氨氯地平", "target": "高血压", "relation_type": "TREATS", "confidence": 0.9, "evidence": "氨氯地平治疗高血压"}}
  ]
}}"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (result.content or "").strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())
        entities = []
        relations = []

        import uuid
        entity_id_map: Dict[str, str] = {}  # canonical_name → entity_id

        for e in parsed.get("entities", []):
            eid = str(uuid.uuid4())[:16]
            entity_id_map[e.get("canonical_name", "")] = eid
            entities.append(KGEntity(
                entity_id=eid,
                user_id=user_id,
                entity_type=e.get("entity_type", ""),
                entity_name=e.get("entity_name", ""),
                canonical_name=e.get("canonical_name", ""),
                aliases=e.get("aliases", []),
                mention_count=1,
                metadata_json=json.dumps(e.get("metadata", {})),
            ))

        for r in parsed.get("relations", []):
            src = r.get("source", "")
            tgt = r.get("target", "")
            src_id = entity_id_map.get(src)
            tgt_id = entity_id_map.get(tgt)
            if src_id and tgt_id:
                relations.append(KGRelation(
                    relation_id=str(uuid.uuid4())[:16],
                    user_id=user_id,
                    source_entity_id=src_id,
                    target_entity_id=tgt_id,
                    relation_type=r.get("relation_type", ""),
                    confidence=r.get("confidence", 1.0),
                    evidence=r.get("evidence", ""),
                ))

        return entities, relations

    except Exception as e:
        logger.warning("[kg] extract_entities_and_relations 失败: %s", e)
        return [], []


# ============================================================
# 图扩展检索
# ============================================================
async def graph_expand_entities(
    query: str,
    user_id: str,
    top_k: int = 5,
    max_hops: int = 2,
) -> Set[str]:
    """
    从查询文本中抽取实体，然后在知识图谱中扩展，返回相关 entity_id 集合。

    Args:
        query: 用户问题
        user_id: 用户 ID
        top_k: 扩展返回的实体数量上限
        max_hops: 扩展跳数（1 或 2）

    Returns:
        扩展后的 entity_id 集合（包含查询实体 + 邻居实体）
    """
    llm = _get_llm()
    if llm is None:
        return set()

    try:
        from langchain_core.messages import HumanMessage
        from .rag import get_rag_store

        # Step 1: 从 query 抽取实体名称
        prompt = f"""从以下用户问题中抽取医学实体名称（仅返回实体名称，每行一个，不要解释）：

可用实体类型：symptom, medication, disease, allergy, vital_sign

问题：{query}

示例输出：
氨氯地平
高血压
头晕"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        entity_names = [
            line.strip() for line in (result.content or "").split("\n")
            if line.strip()
        ]

        if not entity_names:
            return set()

        logger.info("[kg] query entities: %s", entity_names)

        # Step 2: 在 kg_entities 表中查找这些实体
        rag_store = get_rag_store()
        with rag_store.get_connection() as conn:
            ensure_kg_schema(conn)
            with conn.cursor() as cur:
                # 查找匹配的实体（按 canonical_name 或 aliases 模糊匹配）
                placeholders = ",".join(["%s"] * len(entity_names))
                cur.execute(f"""
                    SELECT entity_id, canonical_name, entity_type
                    FROM kg_entities
                    WHERE user_id = %s
                      AND (canonical_name IN ({placeholders})
                           OR aliases::text ILIKE ANY (ARRAY[%s] || '%'))
                    LIMIT 20
                """, [user_id] + entity_names + ["%s"] * len(entity_names))
                rows = cur.fetchall()

        seed_entity_ids = [str(r[0]) for r in rows]
        if not seed_entity_ids:
            return set()

        # Step 3: 图扩展（max_hops 跳）
        all_entity_ids: Set[str] = set(seed_entity_ids)
        current_ids = set(seed_entity_ids)

        for hop in range(max_hops):
            if not current_ids:
                break
            placeholders2 = ",".join(["%s"] * len(current_ids))
            with rag_store.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        SELECT DISTINCT target_entity_id
                        FROM kg_relations
                        WHERE user_id = %s
                          AND source_entity_id IN ({placeholders2})
                        UNION
                        SELECT DISTINCT source_entity_id
                        FROM kg_relations
                        WHERE user_id = %s
                          AND target_entity_id IN ({placeholders2})
                    """, [user_id] + list(current_ids) + [user_id] + list(current_ids))
                    next_ids = set(str(r[0]) for r in cur.fetchall())

            new_ids = next_ids - all_entity_ids
            all_entity_ids.update(new_ids)
            current_ids = new_ids
            logger.info("[kg] hop %d: +%d new entities (total %d)", hop + 1, len(new_ids), len(all_entity_ids))

        # 限制数量
        return set(list(all_entity_ids)[:top_k * 3])

    except Exception as e:
        logger.warning("[kg] graph_expand_entities 失败: %s", e)
        return set()


async def get_chunks_for_entities(
    entity_ids: Set[str],
    user_id: str,
    top_k: int = 5,
) -> List[Any]:
    """
    根据实体 ID 集合，从 kg_entity_chunks 找到关联的 chunks。
    """
    if not entity_ids:
        return []

    try:
        from .rag import get_rag_store
        rag_store = get_rag_store()
        placeholders = ",".join(["%s"] * len(entity_ids))

        with rag_store.get_connection() as conn:
            with conn.cursor() as cur:
                # 找所有关联的 chunk_id，按频率排序
                cur.execute(f"""
                    SELECT chunk_id, count(*) as cnt
                    FROM kg_entity_chunks
                    WHERE user_id = %s AND entity_id IN ({placeholders})
                    GROUP BY chunk_id
                    ORDER BY cnt DESC, chunk_id
                    LIMIT %s
                """, [user_id] + list(entity_ids))
                chunk_rows = cur.fetchall()

        if not chunk_rows:
            return []

        chunk_ids = [str(r[0]) for r in chunk_rows]

        # 再从 rag_chunks 表取完整的 chunk 数据
        placeholders2 = ",".join(["%s"] * len(chunk_ids))
        with rag_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, user_id, source_type, source_id, record_type, title,
                           chunk_index, chunk_text,
                           1.0 as score
                    FROM rag_chunks
                    WHERE user_id = %s AND id::text IN ({placeholders2})
                """, [user_id] + chunk_ids)
                rows = cur.fetchall()

        from .rag import SearchResult
        results = []
        for r in rows:
            results.append(SearchResult(
                chunk_id=str(r[0]),
                user_id=str(r[1]),
                source_type=str(r[2]),
                source_id=str(r[3]),
                record_type=str(r[4]),
                title=str(r[5]) if r[5] else "",
                chunk_index=int(r[6]),
                chunk_text=str(r[7]),
                score=float(r[8]),
            ))

        logger.info("[kg] get_chunks_for_entities: %d entities -> %d chunks", len(entity_ids), len(results))
        return results[:top_k]

    except Exception as e:
        logger.warning("[kg] get_chunks_for_entities 失败: %s", e)
        return []


# ============================================================
# 索引文档时顺便抽取实体关系
# ============================================================
async def index_document_with_kg(
    user_id: str,
    source_type: str,
    source_id: str,
    chunk_id: str,
    text: str,
) -> dict:
    """
    索引文档时：先抽取实体关系，再存储。
    由 rag.py 的 index_document 调用方在写入 chunks 后调用。
    """
    entities, relations = await extract_entities_and_relations(text, user_id, chunk_id)
    if not entities and not relations:
        return {"kg_indexed": False, "reason": "no entities found"}

    try:
        from .rag import get_rag_store
        rag_store = get_rag_store()
        with rag_store.get_connection() as conn:
            ensure_kg_schema(conn)
            with conn.cursor() as cur:
                # 插入实体（upsert: mention_count 累加）
                for e in entities:
                    cur.execute("""
                        INSERT INTO kg_entities (entity_id, user_id, entity_type, entity_name,
                                                 canonical_name, aliases, mention_count, metadata_json)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id, entity_type, canonical_name)
                        DO UPDATE SET
                            mention_count = kg_entities.mention_count + 1,
                            last_seen = now(),
                            entity_name = EXCLUDED.entity_name
                        RETURNING entity_id
                    """, (e.entity_id, e.user_id, e.entity_type, e.entity_name,
                          e.canonical_name, json.dumps(e.aliases), e.mention_count, e.metadata_json))
                    # 获取 upsert 后的 entity_id（可能是已存在的）
                    rows = cur.fetchall()
                    actual_eid = str(rows[0][0]) if rows else e.entity_id

                    # 关联 chunk
                    cur.execute("""
                        INSERT INTO kg_entity_chunks (entity_id, chunk_id, user_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (entity_id, chunk_id) DO NOTHING
                    """, (actual_eid, chunk_id, user_id))

                # 插入关系（需要 source_entity_id 和 target_entity_id 已存在，这里简化处理：
                # 关系在同一个文档内抽取，entity_id 映射在本函数内已处理）
                for r in relations:
                    cur.execute("""
                        INSERT INTO kg_relations (relation_id, user_id, source_entity_id,
                                                  target_entity_id, relation_type, confidence, evidence)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id, source_entity_id, target_entity_id, relation_type)
                        DO UPDATE SET confidence = EXCLUDED.confidence, evidence = EXCLUDED.evidence
                    """, (r.relation_id, r.user_id, r.source_entity_id, r.target_entity_id,
                          r.relation_type, r.confidence, r.evidence))

            conn.commit()

        logger.info("[kg] indexed: %d entities, %d relations for chunk %s", len(entities), len(relations), chunk_id)
        return {"kg_indexed": True, "entities": len(entities), "relations": len(relations)}

    except Exception as e:
        logger.warning("[kg] index_document_with_kg 失败: %s", e)
        return {"kg_indexed": False, "reason": str(e)}
