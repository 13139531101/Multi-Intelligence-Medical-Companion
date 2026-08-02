"""
PHA v2 Magentic RAG (Self-RAG 风格) — 阶段1

核心思想：让检索"智能化"，不只是匹配关键词，而是：
1. should_retrieve  — LLM 判断是否需要检索
2. rewrite_query   — 改写 query 提升检索效果（可选）
3. retrieve_chunks — 调用 RAGStore.search()
4. evaluate_chunks — LLM 评估检索结果是否相关
5. retry / skip    — 根据评估结果决定下一步

Stage 1: 单轮检索 + 评估，不相关时重写一次 query 再检索
"""
from __future__ import annotations

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

    chunks = await retrieve_chunks(current_query, user_id, top_k)

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
        chunks = await retrieve_chunks(current_query, user_id, top_k)

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
# 单例快捷调用
# ============================================================
_async_search = magnetic_rag_search


async def search(
    query: str,
    user_id: str = "default",
    target_agent: str = "health_advisor",
) -> RetrievalResult:
    """
    快捷调用：magnetic_rag_search(user_id=..., query=..., target_agent=...)

    用法示例：
        result = await magnetic_rag.search("血压偏高吃什么好", user_id="user123")
        if result.is_relevant:
            context = magnetic_rag.format_rag_context(result.chunks)
    """
    return await _async_search(query=query, user_id=user_id, target_agent=target_agent)
