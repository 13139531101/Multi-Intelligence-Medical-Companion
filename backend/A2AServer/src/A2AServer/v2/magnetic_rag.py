"""
PHA v2 Magentic RAG (Self-RAG 风格) — Stage 1 + Stage 2

Stage 1 (单轮检索):
  should_retrieve → retrieve → evaluate → 可选 rewrite 重试

Stage 2 (多跳检索):
  detect_record_types → Hop1 并行按类型检索 → Hop2 跨类型增强检索 → merge

默认导出 search() 走 Stage 2 多跳，效果优于单跳。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
DEFAULT_TOP_K = int(os.getenv("PHA_RAG_TOP_K", "5"))
MIN_SCORE_THRESHOLD = float(os.getenv("PHA_RAG_MIN_SIM", "0.5"))
MAX_REWRITE_COUNT = int(os.getenv("PHA_RAG_MAX_REWRITE", "1"))

# 关于"用 rerank 分数短路 evaluate_chunks"（阶段48-perf，已实测放弃）
# ----------------------------------------------------------------------
# 动机：evaluate_chunks 是一次完整 LLM 往返（1.4~2.6s），落在检索热路径末尾，
# 前面的并发优化都省不掉它；而 rerank 也是为"query-doc 相关性"训练的，看似
# 可以用它的高分直接判定 is_relevant=True，跳过这次 LLM 调用。
#
# 实测结论：**不可行**。gte-rerank-v2 的 relevance_score 与 LLM 评估不在同一
# 量纲上：
#     手工构造的"最相关"文档            -> 0.55
#     真实候选集 top1（血压问题）        -> 0.35   LLM 判定 True / 0.95
#     真实候选集 top1（血糖用药问题）    -> 0.18   LLM 判定 True / 0.95
#     真实候选集 top1（检查记录问题）    -> 0.16
#     完全无关的文档（天气）             -> 0.006
# 阈值取 0.4 → 永不触发（死代码）；取 0.15 → 连 0.16 那条也短路，而它是否
# 真的相关无从验证，no_answer 组的误报率会失去约束。即"既常触发又不误报"
# 的阈值不存在，硬调只是拿几个样本过拟合。
#
# 所以这里**保留** evaluate_chunks 的 LLM 评估，不引入这个常量。
# 若要再压这段延迟，正确方向是换更快的评估模型或缩短 prompt，而不是改判定来源。


# ============================================================
# 数据结构
# ============================================================
@dataclass
class RetrievalResult:
    """
    Magentic RAG 检索结果（包含评估信息）

    fields:
    - chunks: RAGStore 返回的 chunks 列表
    - score: 平均相关性评分 (0.0-1.0)
    - is_relevant: 评估是否通过
    - reason: 评估理由
    - rewrite_count: 已重写次数（防死循环）
    - query: 最终用于检索的 query（可能经过改写）
    - retrieval_needed: should_retrieve 判断结果
    """
    chunks: List[Any]
    score: float = 0.0
    is_relevant: bool = False
    reason: str = ""
    rewrite_count: int = 0
    query: str = ""
    retrieval_needed: bool = True


# ============================================================
# LLM 客户端（复用 deepseek）
# ============================================================
def _get_llm():
    """获取 LLM 客户端（DeepSeek）"""
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.getenv("PHA_LLM_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0,
        )
    except Exception as e:
        logger.warning("[magnetic_rag] LLM 不可用: %s", e)
        return None


# ============================================================
# 1. should_retrieve — 判断是否需要检索
# ============================================================
async def should_retrieve(query: str, target_agent: str = "health_advisor") -> bool:
    """
    用 LLM 判断用户问题是否需要检索健康知识库。

    判断逻辑：
    - 闲聊/问候/明确不需要检索 → False
    - 涉及个人健康档案、症状分析、用药建议 → True
    - 通用健康知识（与个人档案无关）→ True

    Args:
        query: 用户原始问题
        target_agent: 目标 agent（用于判断是否与该领域相关）

    Returns:
        True = 需要检索，False = 不需要
    """
    llm = _get_llm()
    if llm is None:
        # LLM 不可用时，默认需要检索（保守策略）
        return True

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个智能路由决策器。

用户问题：{query}
目标助手类型：{target_agent}

判断这个问题是否需要检索用户的个人健康档案/知识库来回答。

需要检索的情况（回答 YES）：
- 询问个人健康状况、症状分析、用药指导
- 涉及具体检查报告、检验结果解读
- 需要结合用户历史健康数据才能回答
- 询问某种疾病/症状的注意事项

不需要检索的情况（回答 NO）：
- 纯粹的闲聊、问候、问候语
- 通用健康科普（不涉及个人数据）
- 明确说"不用查档案"
- 系统操作类问题（如"帮我设置提醒"）

只回答 YES 或 NO，不要解释。"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        decision = (result.content or "").strip().upper()
        needed = decision == "YES"
        logger.info("[magnetic_rag] should_retrieve=%s query=%s", needed, query[:30])
        return needed

    except Exception as e:
        logger.warning("[magnetic_rag] should_retrieve LLM 调用失败: %s", e)
        return True  # 失败时保守返回需要检索


# ============================================================
# 2. rewrite_query — 改写 query 提升检索效果
# ============================================================
async def rewrite_query(query: str, target_agent: str = "health_advisor") -> str:
    """
    将用户问题改写成更适合检索的形式。

    改写策略：
    - 添加领域限定词（"健康顾问"相关的症状描述）
    - 翻译中文关键术语到英文（embedding 模型可能支持中英双语）
    - 分解复合问题为多个简单查询

    Args:
        query: 原始问题
        target_agent: 目标 agent

    Returns:
        改写后的问题
    """
    llm = _get_llm()
    if llm is None:
        return query

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个查询改写专家。

原始问题：{query}
目标领域：{target_agent}

请将这个问题改写成更适合语义检索的形式：
1. 添加领域相关的限定词
2. 将模糊表述具体化
3. 保留核心查询意图

直接输出改写后的问题，不要解释。"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        rewritten = (result.content or "").strip()
        logger.info("[magnetic_rag] rewrite: %s -> %s", query[:30], rewritten[:30])
        return rewritten or query

    except Exception as e:
        logger.warning("[magnetic_rag] rewrite_query LLM 调用失败: %s", e)
        return query


# ============================================================
# 3. retrieve_chunks — 调用 RAGStore 检索
# ============================================================
async def retrieve_chunks(
    query: str,
    user_id: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_SCORE_THRESHOLD,
) -> List[Any]:
    """
    调用 RAGStore.search() 检索相关 chunks。

    Args:
        query: 检索 query（可能已改写）
        user_id: 用户 ID
        top_k: 返回数量
        min_score: 最小相似度阈值

    Returns:
        RAGStore.SearchResult 列表
    """
    try:
        from .rag import get_rag_store
        rag_store = get_rag_store()
        results = await rag_store.search(
            user_id=user_id,
            query=query,
            top_k=top_k,
            min_score=min_score,
        )
        logger.info("[magnetic_rag] retrieve: query=%s top_k=%d got=%d", query[:30], top_k, len(results))
        return results
    except Exception as e:
        logger.warning("[magnetic_rag] retrieve_chunks 失败: %s", e)
        return []


# ============================================================
# 4. evaluate_chunks — LLM 评估检索结果相关性
# ============================================================
async def evaluate_chunks(query: str, chunks: List[Any]) -> Dict[str, Any]:
    """
    用 LLM 评估检索到的 chunks 是否能回答用户问题。

    返回格式：
    {
        "is_relevant": bool,   # 是否相关
        "score": float,        # 0.0-1.0
        "reason": str,          # 评估理由
    }

    Args:
        query: 用户原始问题
        chunks: RAGStore 返回的 SearchResult 列表

    Returns:
        评估结果 dict

    注：曾尝试用 rerank 的分数短路这次 LLM 调用（省 1.4~2.6s），**实测不可行**：
    gte-rerank-v2 在真实候选集上的最高分只有 0.16~0.35，而 LLM 对同一批候选
    判的是 is_relevant=True / score=0.95 —— 两者是不同量纲，没有能同时"常触发"
    又"不误报"的阈值。详见本文件 MIN_SCORE_THRESHOLD 下方的说明。
    """
    llm = _get_llm()
    if llm is None:
        # LLM 不可用时，用简单评分
        if not chunks:
            return {"is_relevant": False, "score": 0.0, "reason": "无检索结果"}
        avg_score = sum(c.score for c in chunks) / len(chunks)
        return {
            "is_relevant": avg_score >= MIN_SCORE_THRESHOLD,
            "score": avg_score,
            "reason": f"阈值评分 {avg_score:.2f}",
        }

    if not chunks:
        return {"is_relevant": False, "score": 0.0, "reason": "检索结果为空"}

    # 构建 chunks 描述文本
    chunks_text = []
    for i, chunk in enumerate(chunks[:5], 1):  # 最多评估前5个
        chunk_text = getattr(chunk, "chunk_text", str(chunk))
        source = f"{getattr(chunk, 'source_type', '')}/{getattr(chunk, 'source_id', '')}"
        chunks_text.append(f"{i}. [来源: {source}] {chunk_text[:300]}")

    chunks_str = "\n".join(chunks_text)

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个检索质量评估员。

用户问题：{query}

检索到的片段：
{chunks_str}

请评估这些片段是否足够回答用户问题。

评分标准：
- 完全相关，能回答问题：is_relevant=true, score=0.85-1.0
- 部分相关，需要补充：is_relevant=true, score=0.60-0.84
- 勉强相关：is_relevant=true, score=0.50-0.59
- 不相关或错误：is_relevant=false, score=0.0-0.49

注意：如果检索结果与用户问题无关（如用户问血压但检索到糖尿病内容），应该判定为不相关。

只输出 JSON 格式，不要其他内容：
{{"is_relevant": true/false, "score": 0.0-1.0, "reason": "简短理由（10字以内）"}}"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (result.content or "").strip()

        # 尝试解析 JSON
        try:
            # 提取 JSON（可能在 ```json ... ``` 中）
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            parsed = json.loads(content.strip())
            evaluation = {
                "is_relevant": bool(parsed.get("is_relevant", False)),
                "score": float(parsed.get("score", 0.0)),
                "reason": str(parsed.get("reason", ""))[:50],
            }
        except json.JSONDecodeError:
            # 解析失败，用启发式
            logger.warning("[magnetic_rag] evaluate JSON 解析失败: %s", content[:100])
            avg_score = sum(c.score for c in chunks) / len(chunks)
            evaluation = {
                "is_relevant": avg_score >= MIN_SCORE_THRESHOLD,
                "score": avg_score,
                "reason": "解析失败，使用阈值评分",
            }

        logger.info(
            "[magnetic_rag] evaluate: is_relevant=%s score=%.2f reason=%s query=%s",
            evaluation["is_relevant"], evaluation["score"], evaluation["reason"], query[:30]
        )
        return evaluation

    except Exception as e:
        logger.warning("[magnetic_rag] evaluate_chunks LLM 调用失败: %s", e)
        avg_score = sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        return {
            "is_relevant": avg_score >= MIN_SCORE_THRESHOLD,
            "score": avg_score,
            "reason": f"评估异常: {str(e)[:30]}",
        }


# ============================================================
# 5. magnetic_rag_search — 主入口
# ============================================================
async def magnetic_rag_search(
    query: str,
    user_id: str,
    target_agent: str = "health_advisor",
    max_rewrite: int = MAX_REWRITE_COUNT,
    top_k: int = DEFAULT_TOP_K,
) -> RetrievalResult:
    """
    Magentic RAG 主入口：should_retrieve → 可选 rewrite → retrieve → evaluate → 重试

    流程：
    1. should_retrieve 判断是否需要检索
       - 不需要 → 直接返回空结果
    2. 检索（第一轮）
    3. evaluate_chunks 评估
       - 通过 → 返回结果
       - 不通过且还有重试次数 → rewrite_query → 重新检索 → 再评估
       - 不通过且无重试次数 → 返回（带低评分）
    4. 返回 RetrievalResult

    Args:
        query: 用户问题
        user_id: 用户 ID
        target_agent: 目标 agent
        max_rewrite: 最多重写次数
        top_k: 检索返回数量

    Returns:
        RetrievalResult
    """
    # Step 1: 判断是否需要检索
    needed = await should_retrieve(query, target_agent)
    if not needed:
        logger.info("[magnetic_rag] should_retrieve=False，跳过检索: %s", query[:30])
        return RetrievalResult(
            chunks=[],
            score=0.0,
            is_relevant=False,
            reason="不需要检索",
            rewrite_count=0,
            query=query,
            retrieval_needed=False,
        )

    # Step 2: 第一轮检索
    current_query = query
    rewrite_count = 0

    # 多取一倍候选给 rerank 挑（纯向量序的前 top_k 未必是真正最相关的）
    chunks = await retrieve_chunks(current_query, user_id, top_k * 2)

    # Step 2.5: rerank（阶段48-p3）— 送进 evaluate 之前先重排，让 LLM 评估
    # 看到的是真正的 top 候选，而不是纯向量序
    chunks = await _rerank_chunks(current_query, chunks, top_k)

    # Step 3: 评估
    evaluation = await evaluate_chunks(query, chunks)

    # Step 4: 不通过时重试
    while not evaluation["is_relevant"] and rewrite_count < max_rewrite:
        rewrite_count += 1

        # 改写 query
        current_query = await rewrite_query(query, target_agent)
        if current_query == query:
            # query 没变化，不再重试
            break

        logger.info("[magnetic_rag] rewrite #%d: %s -> %s", rewrite_count, query[:30], current_query[:30])

        # 重新检索
        chunks = await retrieve_chunks(current_query, user_id, top_k * 2)
        chunks = await _rerank_chunks(current_query, chunks, top_k)

        # 重新评估
        evaluation = await evaluate_chunks(query, chunks)

    return RetrievalResult(
        chunks=chunks,
        score=evaluation["score"],
        is_relevant=evaluation["is_relevant"],
        reason=evaluation["reason"],
        rewrite_count=rewrite_count,
        query=current_query,
        retrieval_needed=True,
    )


# ============================================================
# 工具函数：格式化检索结果为文本
# ============================================================
def format_rag_context(chunks: List[Any], max_chars: int = 1500) -> str:
    """
    将检索结果格式化为字符串，用于注入到 system_prompt 或显示给用户。

    Args:
        chunks: RetrievalResult.chunks 或 SearchResult 列表
        max_chars: 最大字符数

    Returns:
        格式化后的字符串
    """
    if not chunks:
        return "（未检索到相关健康档案）"

    lines = []
    total_chars = 0

    for i, chunk in enumerate(chunks, 1):
        chunk_text = getattr(chunk, "chunk_text", str(chunk))
        source_type = getattr(chunk, "source_type", "")
        source_id = getattr(chunk, "source_id", "")
        score = getattr(chunk, "score", 0.0)
        title = getattr(chunk, "title", "")

        # 截断过长片段
        if len(chunk_text) > 300:
            chunk_text = chunk_text[:300] + "..."

        line = f"[{i}] {chunk_text}"
        if title:
            line = f"[{i}] 【{title}】{chunk_text}"

        total_chars += len(line) + 1
        if total_chars > max_chars:
            # 估算还能放多少
            remaining = max_chars - total_chars + len(line)
            if remaining > 50:
                lines.append(line[:remaining] + "...(截断)")
            break

        lines.append(line)

    if not lines:
        return "（检索结果过于分散，无法整理）"

    header = f"【参考健康档案】（共 {len(chunks)} 条相关记录）\n"
    return header + "\n".join(lines)


# ============================================================
# Stage 2: 多跳检索 — detect → parallel_hop1 → synthesize_hop2 → merge
# ============================================================

# PHA 健康档案类型枚举（LLM 分类时用的逻辑类型）
RECORD_TYPES = [
    "blood_pressure",   # 血压记录
    "blood_sugar",      # 血糖记录
    "medication",       # 用药记录
    "lab_result",       # 检验报告
    "visit_summary",    # 就诊摘要
    "health_record",    # 健康档案（通用）
    "symptom",          # 症状记录
]

# RECORD_TYPES → rag_chunks.record_type 列的真实值映射
# 解决 Stage 2 多跳检索因类型名不匹配导致返回空的问题
RECORD_TYPE_TO_DB_TYPE = {
    "blood_pressure": "vital_signs",   # 血压 → vital_signs
    "blood_sugar":    "vital_signs",   # 血糖 → vital_signs
    "medication":     "prescription",  # 用药 → prescription
    "lab_result":     "lab_result",    # 检验报告（直接映射）
    "visit_summary":  "other",         # 就诊摘要 → other（无对应枚举，用 other）
    "health_record":  "medical_report",# 健康档案 → medical_report
    "symptom":        "symptom",       # 症状（直接映射）
}


async def detect_record_types(query: str) -> List[str]:
    """
    LLM 判断 query 涉及哪些档案类型。

    Args:
        query: 用户问题

    Returns:
        档案类型列表，如 ["blood_pressure", "medication"]
    """
    llm = _get_llm()
    if llm is None:
        # LLM 不可用时，搜全部类型
        return list(RECORD_TYPES)

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个健康档案类型分类器。

用户问题：{query}

可用档案类型：
- blood_pressure: 血压记录
- blood_sugar: 血糖记录
- medication: 用药记录、服药历史
- lab_result: 检验报告（血常规、生化等）
- visit_summary: 就诊摘要、出院小结
- health_record: 综合健康档案、体检报告
- symptom: 症状描述、不适记录

判断这个问题需要查询哪些档案类型来回答。
只要可能相关的都列出来，但不要列不相关的。

输出 JSON 格式，不要其他内容：
{{"types": ["type1", "type2"]}}"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (result.content or "").strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())
        types = parsed.get("types", [])
        # 过滤，只保留已知的类型
        valid = [t for t in types if t in RECORD_TYPES]
        logger.info("[multi_hop] detect types: %s query=%s", valid, query[:30])
        return valid or list(RECORD_TYPES)

    except Exception as e:
        logger.warning("[multi_hop] detect_record_types 失败: %s", e)
        return list(RECORD_TYPES)


async def _kg_expand_safe(query: str, user_id: str, top_k: int) -> set:
    """并发版 KG 实体扩展：任何失败都吞掉并返回空集。

    单独包一层是因为它要被 asyncio.create_task 提前发起 —— 如果直接抛异常，
    会变成一个"无人 await 的失败 Task"，只在 GC 时打印一条噪音日志，而且到
    Step 5.5 取结果时才会炸。这里就地兜住，让调用方永远拿到一个 set。
    """
    try:
        from .knowledge_graph import graph_expand_entities
        return await graph_expand_entities(query, user_id, top_k=top_k, max_hops=2)
    except Exception as e:  # noqa: BLE001
        logger.debug("[multi_hop] kg expansion skipped: %s", e)
        return set()


async def plan_retrieval(query: str, target_agent: str = "health_advisor") -> Dict[str, Any]:
    """一次 LLM 调用同时回答两个问题：要不要检索 + 检索哪些档案类型。

    阶段48-perf: 原来 `should_retrieve` 和 `detect_record_types` 是两次独立的
    LLM 往返，但它们**读的是同一个 query、判的是同一件事的两个侧面**，串行跑等于
    白白多花一次网络往返（DeepSeek 上实测 0.6~1.2s）。合并成一次调用。

    Returns:
        {"needed": bool, "types": [...]}
        LLM 不可用/解析失败时保守返回 {"needed": True, "types": 全部类型}。
    """
    llm = _get_llm()
    if llm is None:
        return {"needed": True, "types": list(RECORD_TYPES)}

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个健康助手的检索规划器，需要一次性回答两件事。

用户问题：{query}
目标助手类型：{target_agent}

【问题一】是否需要检索用户的个人健康档案/知识库？
- 需要（needed=true）：询问个人健康状况、症状分析、用药指导、检查报告解读，
  或需要结合用户历史数据、需要疾病/症状的注意事项。
- 不需要（needed=false）：纯粹闲聊问候、与个人数据无关的通用科普、
  用户明确说"不用查档案"、系统操作类问题（如"帮我设置提醒"）。

【问题二】需要查询哪些档案类型？（只要可能相关就列，不要列不相关的）
- blood_pressure: 血压记录
- blood_sugar: 血糖记录
- medication: 用药记录、服药历史
- lab_result: 检验报告（血常规、生化等）
- visit_summary: 就诊摘要、出院小结
- health_record: 综合健康档案、体检报告
- symptom: 症状描述、不适记录

只输出 JSON，不要任何解释或代码块标记：
{{"needed": true, "types": ["blood_pressure", "medication"]}}"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (result.content or "").strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())
        needed = bool(parsed.get("needed", True))
        types = [t for t in (parsed.get("types") or []) if t in RECORD_TYPES]
        plan = {"needed": needed, "types": types or list(RECORD_TYPES)}
        logger.info(
            "[multi_hop] plan: needed=%s types=%s query=%s",
            plan["needed"], plan["types"], query[:30],
        )
        return plan

    except Exception as e:
        logger.warning("[multi_hop] plan_retrieval 失败, 退回保守策略: %s", e)
        return {"needed": True, "types": list(RECORD_TYPES)}


async def retrieve_chunks_by_type(
    query: str,
    user_id: str,
    record_type: str,
    top_k: int = DEFAULT_TOP_K,
) -> List[Any]:
    """按 rag_chunks.record_type 列过滤检索（解决 source_type 值不匹配问题）"""
    try:
        from .rag import get_rag_store
        rag_store = get_rag_store()
        results = await rag_store.search(
            user_id=user_id,
            query=query,
            top_k=top_k,
            record_type=record_type,
        )
        return results
    except Exception as e:
        logger.warning("[multi_hop] retrieve by type %s failed: %s", record_type, e)
        return []


def _chunks_to_text(chunks: List[Any], max_per_type: int = 3) -> str:
    """把 chunks 转成摘要文本，用于拼入下一跳 query"""
    lines = []
    for c in chunks[:max_per_type]:
        text = getattr(c, "chunk_text", str(c))
        stype = getattr(c, "source_type", "")
        if len(text) > 200:
            text = text[:200] + "..."
        lines.append(f"[{stype}] {text}")
    return "\n".join(lines) if lines else ""


async def _rerank_chunks(query: str, chunks: List[Any], top_k: int) -> List[Any]:
    """阶段48-p3: 用 DashScope gte-rerank-v2 对合并后的候选重排。

    向量检索是 bi-encoder（query 与 doc 各自编码再算 cosine），对"措辞不同但
    语义相关"的档案召回不足；rerank 是 cross-encoder（query+doc 一起进模型），
    精度显著更高。栈 B 实测 MRR 0.6167 → 1.0。

    全程可降级：没配 key / 超时 / 报错 → 原样返回，绝不影响主链路。
    """
    if len(chunks) < 2:
        # 候选不够就没得排。这里也要记一笔 skipped, 否则 /metrics 上 rerank
        # 指标整族缺失, 无法区分"没接上"和"没轮到"。
        try:
            from .rerank import note_skipped

            note_skipped()
        except Exception:  # noqa: BLE001 — 指标不能影响检索
            pass
        return chunks
    try:
        from .rerank import rerank
        docs = [getattr(c, "chunk_text", "") or "" for c in chunks]
        pairs = await rerank(query, docs, top_n=top_k)
        if not pairs:
            return chunks
        reordered = [chunks[i] for i, _ in pairs if 0 <= i < len(chunks)]
        # 落选但仍未超过 top_k 的按原顺序补回，保证数量不缩水
        if len(reordered) < top_k:
            chosen = {i for i, _ in pairs}
            for i, c in enumerate(chunks):
                if i not in chosen:
                    reordered.append(c)
                if len(reordered) >= top_k:
                    break
        return reordered[: max(top_k, len(reordered))]
    except Exception as e:  # noqa: BLE001
        logger.warning("[multi_hop] rerank 跳过(降级为向量序): %s", e)
        return chunks


async def multi_hop_rag_search(
    query: str,
    user_id: str,
    target_agent: str = "health_advisor",
    top_k: int = DEFAULT_TOP_K,
) -> RetrievalResult:
    """
    Stage 2 多跳检索：

    Hop 1 — detect_record_types 识别档案类型 → 并行检索每类
    Hop 2 — 对每类，用其他类的结果文本补充 query → 再检索
    Merge  — 合并所有 chunks，按 score 排序

    效果优于单跳的关键：
    - 避免单一类型检索遗漏相关档案
    - 跨类型结果相互补充（如"血压高+最近吃了什么药"）
    """
    # Step 1+2: 一次 LLM 调用同时决定「要不要检索」和「检索哪些类型」。
    #
    # 阶段48-perf: 这里原来是 should_retrieve → detect_record_types 两次串行 LLM
    # 往返。同时，KG 实体抽取（graph_expand_entities 内部其实是一次 LLM 调用，
    # 名字看不出来）只依赖 query，却排在**全部检索完成之后**才跑 —— 白白串在
    # 关键路径上。现在把它和规划调用一起并发发起，结果等到 Step 5.5 再 await。
    plan_task = asyncio.create_task(plan_retrieval(query, target_agent))
    kg_task = asyncio.create_task(_kg_expand_safe(query, user_id, top_k))

    plan = await plan_task
    if not plan["needed"]:
        # cancel() 只是"请求取消"，不 await 的话这个 Task 会变成悬空任务，
        # 在事件循环关闭时打印 "Task was destroyed but it is pending"。
        kg_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await kg_task
        return RetrievalResult(
            chunks=[], score=0.0, is_relevant=False,
            reason="不需要检索", rewrite_count=0, query=query,
            retrieval_needed=False,
        )

    types = plan["types"]
    logger.info("[multi_hop] detected types: %s for query=%s", types, query[:30])

    # Step 3: Hop 1 — 并行检索每个类型（逻辑类型 → DB类型映射）
    #
    # 阶段48-perf: 原注释写着"并行"，实现却是 for + await —— 每个类型一次
    # embedding API 往返，7 个类型就是 7 次串行。改成 gather 真正并发。
    async def _hop1(rtype: str):
        db_type = RECORD_TYPE_TO_DB_TYPE.get(rtype, rtype)
        chunks = await retrieve_chunks_by_type(query, user_id, db_type, top_k)
        logger.info("[multi_hop] hop1 %s -> %s: got %d chunks", rtype, db_type, len(chunks))
        return rtype, chunks

    hop1_pairs = await asyncio.gather(*(_hop1(t) for t in types)) if types else []
    all_chunks: Dict[str, List[Any]] = {t: c for t, c in hop1_pairs}
    hop1_results = dict(all_chunks)

    # Step 4: Hop 2 — 对每个类型，用其他类型结果丰富 query 再检索
    # 构建跨类型上下文文本
    cross_context = _chunks_to_text(sum(all_chunks.values(), []), max_per_type=2)

    # 阶段48-perf: 同样是 gather 真并发（原来注释说并行、实现是串行 await）
    async def _hop2(rtype: str):
        # 构造增强 query：原 query + 其他类型上下文
        other_context = "\n".join(
            _chunks_to_text(chunks, max_per_type=2)
            for other_type, chunks in all_chunks.items()
            if other_type != rtype and chunks
        )
        if other_context:
            enhanced_query = (
                f"原始问题：{query}\n\n"
                f"相关档案信息：\n{other_context}\n\n"
                f"请根据上述信息，进一步查找与【{rtype}】相关的具体内容："
            )
        else:
            enhanced_query = query

        db_type = RECORD_TYPE_TO_DB_TYPE.get(rtype, rtype)
        chunks = await retrieve_chunks_by_type(enhanced_query, user_id, db_type, top_k)
        logger.info("[multi_hop] hop2 %s -> %s: got %d chunks (enhanced)", rtype, db_type, len(chunks))
        return rtype, chunks

    hop2_pairs = await asyncio.gather(*(_hop2(t) for t in types)) if types else []
    hop2_chunks_by_type: Dict[str, List[Any]] = {t: c for t, c in hop2_pairs}

    # Step 5: 合并所有 chunks，去重（按 chunk_id）
    seen_ids = set()
    merged: List[Any] = []
    for rtype in types:
        # hop2 优先级更高，先加 hop2
        for c in hop2_chunks_by_type.get(rtype, []):
            cid = getattr(c, "chunk_id", id(c))
            if cid not in seen_ids:
                seen_ids.add(cid)
                merged.append(c)
        # 再加 hop1 里没有的
        for c in hop1_results.get(rtype, []):
            cid = getattr(c, "chunk_id", id(c))
            if cid not in seen_ids:
                seen_ids.add(cid)
                merged.append(c)

    # 按 score 降序
    merged.sort(key=lambda x: getattr(x, "score", 0.0), reverse=True)
    final_chunks = merged[: top_k * 2]  # 多取一些让 evaluate 充分

    # Step 5.5: 知识图谱扩展 — 实体抽取在 Step 1 就已并发发起，这里只是取回结果。
    try:
        kg_entity_ids = await kg_task
        if kg_entity_ids:
            from .knowledge_graph import get_chunks_for_entities
            kg_chunks = await get_chunks_for_entities(kg_entity_ids, user_id, top_k=top_k)
            # 合并到 final_chunks（去重）
            seen_ids = {getattr(c, "chunk_id", id(c)) for c in final_chunks}
            for c in kg_chunks:
                cid = getattr(c, "chunk_id", id(c))
                if cid not in seen_ids:
                    final_chunks.append(c)
                    seen_ids.add(cid)
            final_chunks.sort(key=lambda x: getattr(x, "score", 0.0), reverse=True)
            final_chunks = final_chunks[: top_k * 2]
            logger.info("[multi_hop] kg expanded: +%d chunks from %d entities", len(kg_chunks), len(kg_entity_ids))
        else:
            logger.info("[multi_hop] kg: no entities found in query, skipping expansion")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug("[multi_hop] kg expansion skipped: %s", e)

    # Step 5.6: rerank — 多路召回（hop1/hop2/KG 扩展）合并后的候选里，向量分数
    # 已经不可比（来自不同 query、不同路），必须在送进 evaluate 之前统一重排，
    # 否则 LLM 看到的是"混杂排序"的候选，评估与最终答案都受影响。
    final_chunks = await _rerank_chunks(query, final_chunks, top_k)

    # Step 6: 评估合并结果
    evaluation = await evaluate_chunks(query, final_chunks)

    logger.info(
        "[multi_hop] done: types=%s hop1_total=%d hop2_total=%d merged=%d "
        "is_relevant=%s score=%.2f query=%s",
        types,
        sum(len(v) for v in hop1_results.values()),
        sum(len(v) for v in hop2_chunks_by_type.values()),
        len(final_chunks),
        evaluation["is_relevant"], evaluation["score"], query[:30]
    )

    # Step 7: 若评估不通过，rewrite query 后重试完整多跳（Stage 1 重试逻辑嫁接）
    current_query = query
    rewrite_count = 0
    final_chunks_list = final_chunks

    while not evaluation["is_relevant"] and rewrite_count < MAX_REWRITE_COUNT:
        rewrite_count += 1
        current_query = await rewrite_query(query, target_agent)
        if current_query == query:
            break

        logger.info("[multi_hop] rewrite #%d: %s -> %s", rewrite_count, query[:30], current_query[:30])

        # 重跑完整多跳流程（阶段48-perf: 同 Step 3/4，改成真并发）
        db_types = [RECORD_TYPE_TO_DB_TYPE.get(t, t) for t in types]

        async def _retry_hop1(db_type: str):
            return db_type, await retrieve_chunks_by_type(current_query, user_id, db_type, top_k)

        hop1_chunks = dict(await asyncio.gather(*(_retry_hop1(d) for d in db_types)))

        async def _retry_hop2(db_type: str):
            other_ctx = "\n".join(
                _chunks_to_text(c, max_per_type=2)
                for other_db, c in hop1_chunks.items()
                if other_db != db_type and c
            )
            eq = (f"原始问题：{current_query}\n\n相关档案信息：\n{other_ctx}\n\n"
                  f"请根据上述信息，进一步查找与【{db_type}】相关的具体内容：") if other_ctx else current_query
            return db_type, await retrieve_chunks_by_type(eq, user_id, db_type, top_k)

        hop2_chunks = dict(await asyncio.gather(*(_retry_hop2(d) for d in db_types)))

        seen_ids2 = set()
        merged2 = []
        for db_type in db_types:
            for c in hop2_chunks.get(db_type, []):
                cid = getattr(c, "chunk_id", id(c))
                if cid not in seen_ids2:
                    seen_ids2.add(cid)
                    merged2.append(c)
            for c in hop1_chunks.get(db_type, []):
                cid = getattr(c, "chunk_id", id(c))
                if cid not in seen_ids2:
                    seen_ids2.add(cid)
                    merged2.append(c)
        merged2.sort(key=lambda x: getattr(x, "score", 0.0), reverse=True)
        final_chunks_list = merged2[: top_k * 2]

        # 重写后的候选同样先 rerank 再评估
        final_chunks_list = await _rerank_chunks(current_query, final_chunks_list, top_k)

        evaluation = await evaluate_chunks(query, final_chunks_list)

    logger.info(
        "[multi_hop] final: is_relevant=%s score=%.2f rewrite_count=%d query=%s",
        evaluation["is_relevant"], evaluation["score"], rewrite_count, current_query[:30]
    )

    return RetrievalResult(
        chunks=final_chunks_list,
        score=evaluation["score"],
        is_relevant=evaluation["is_relevant"],
        reason=evaluation["reason"],
        rewrite_count=rewrite_count,
        query=current_query,
        retrieval_needed=True,
    )


# ============================================================
# 单例快捷调用（默认走多跳 Stage 2）
# ============================================================
async def search(
    query: str,
    user_id: str = "default",
    target_agent: str = "health_advisor",
) -> RetrievalResult:
    """
    快捷调用：默认走 Stage 2 多跳检索

    用法示例：
        result = await magnetic_rag.search("血压和用药有什么关系", user_id="user123")
        if result.is_relevant:
            context = magnetic_rag.format_rag_context(result.chunks)
    """
    return await multi_hop_rag_search(query=query, user_id=user_id, target_agent=target_agent)
