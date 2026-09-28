"""
PHA v2 CRAG Merge — 本地 RAG + Web 搜索混合上下文组装

功能：
1. 评估 web 结果与 query 的相关性，过滤不相关结果
2. 格式化 web 结果为引用文本
3. 与本地 context_text 合并
4. 返回混合上下文 + source citations
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, List

from .web_search import WebResult

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================
@dataclass
class MergedContext:
    """混合检索结果"""
    merged_text: str           # 合并后的上下文文本（注入 agent prompt）
    web_sources: list[dict]    # web 来源列表 [{title, url, snippet}]
    confidence_level: str      # high | medium | low
    source_mix: str            # local | web | mixed | none
    web_used: bool             # 是否使用了 web 结果


# ============================================================
# LLM 客户端（复用 DeepSeek）
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
        logger.warning("[crag][merge] LLM 不可用: %s", e)
        return None


# ============================================================
# Web 结果相关性评估
# ============================================================
async def filter_web_results(
    query: str,
    web_results: List[WebResult],
) -> List[WebResult]:
    """
    用 LLM 评估 web 结果与 query 的相关性，过滤不相关内容。

    Args:
        query: 用户原始问题
        web_results: WebSearchProvider 返回的原始结果

    Returns:
        通过相关性评估的 WebResult 列表
    """
    if not web_results:
        return []

    llm = _get_llm()
    if llm is None:
        # LLM 不可用，返回所有结果（保守策略）
        return web_results

    # 构建 web 结果文本
    results_text = []
    for i, r in enumerate(web_results, 1):
        results_text.append(
            f"[{i}] 标题: {r.title}\nURL: {r.url}\n摘要: {r.snippet[:200]}"
        )
    results_str = "\n\n".join(results_text)

    try:
        from langchain_core.messages import HumanMessage

        prompt = f"""你是一个医疗信息质量评估员。

用户问题：{query}

搜索到的网络结果：
{results_str}

请评估每个结果对回答用户问题的相关性。

评分标准：
- 完全相关，能直接帮助回答问题：保留
- 部分相关，可作为参考：保留
- 不相关或离题：移除

只输出 JSON 格式数组，不要其他内容：
{{"kept_indices": [1, 3, 5]}}  <!-- 保留的序号（从1开始）-->"""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (result.content or "").strip()

        # 解析 JSON
        import json
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            parsed = json.loads(content.strip())
            kept_indices = parsed.get("kept_indices", [])
            # 转换为 0-based 索引
            kept_0based = [i - 1 for i in kept_indices if 1 <= i <= len(web_results)]
            filtered = [web_results[i] for i in kept_0based]
            logger.info(
                "[crag][merge] filter: query=%s original=%d kept=%d",
                query[:30], len(web_results), len(filtered)
            )
            return filtered
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("[crag][merge] filter parse failed: %s, keeping all", e)
            return web_results

    except Exception as e:
        logger.warning("[crag][merge] filter_web_results LLM 调用失败: %s", e)
        return web_results  # 失败时保留所有


# ============================================================
# 格式化 web 结果为引用文本
# ============================================================
def format_web_context(
    web_results: List[WebResult],
    max_chars: int = 1000,
    max_results: int = 3,
) -> tuple[str, list[dict]]:
    """
    将 web 结果格式化为上下文字符串。

    Args:
        web_results: 通过相关性过滤的 web 结果
        max_chars: 最大字符数
        max_results: 最大结果数

    Returns:
        (formatted_text, sources_list)
    """
    if not web_results:
        return "", []

    lines = []
    sources = []
    total_chars = 0
    used = 0

    for r in web_results[:max_results]:
        snippet = r.snippet[:200] + "..." if len(r.snippet) > 200 else r.snippet
        line = f"【网络来源】{r.title}\n{snippet}\n来源: {r.url}"

        if total_chars + len(line) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 50:
                lines.append(line[:remaining] + "...(截断)")
                total_chars += remaining
            break

        lines.append(line)
        total_chars += len(line) + 1
        sources.append({"title": r.title, "url": r.url, "snippet": r.snippet[:100]})
        used += 1

    if not lines:
        return "", []

    header = f"【参考网络信息】（共 {len(web_results)} 条，选取 {used} 条）\n"
    return header + "\n\n".join(lines), sources


# ============================================================
# 主合并函数
# ============================================================
async def merge_local_web(
    local_chunks: list[Any],
    web_results: List[WebResult],
    query: str,
    local_context_text: str = "",
    action: str = "AMBIGUOUS",
) -> MergedContext:
    """
    合并本地 RAG 结果和 web 搜索结果。

    策略：
    - AMBIGUOUS: 保留本地 + 补充 web（本地结果部分可用）
    - INCORRECT: 丢弃本地，只用 web（本地结果完全不相关）

    Args:
        local_chunks: 本地 RAG 的 SearchResult 列表
        web_results: WebSearchProvider 返回的原始结果
        query: 用户原始问题
        local_context_text: 已格式化的本地上下文文本
        action: CRAG action (AMBIGUOUS | INCORRECT)

    Returns:
        MergedContext
    """
    # Step 1: 过滤 web 结果（只保留与 query 相关的）
    filtered_web = await filter_web_results(query, web_results)

    if not filtered_web:
        # Web 搜索失败或全部不相关
        if action == "INCORRECT":
            # 本地也无效，返回空上下文
            return MergedContext(
                merged_text="（未找到相关健康档案，网络搜索也未返回可用结果）",
                web_sources=[],
                confidence_level="low",
                source_mix="none",
                web_used=False,
            )
        else:
            # AMBIGUOUS 但 web 失败，退回本地
            return MergedContext(
                merged_text=local_context_text,
                web_sources=[],
                confidence_level="medium",
                source_mix="local",
                web_used=False,
            )

    # Step 2: 格式化 web 结果
    web_text, web_sources = format_web_context(filtered_web, max_chars=1000, max_results=3)

    # Step 3: 构建最终 merged_text
    if action == "INCORRECT":
        # 纯 web 模式：丢弃本地
        merged_text = web_text
        source_mix = "web"
        confidence_level = "low"  # web 来源未经个人档案验证，置信度降低
    else:
        # AMBIGUOUS: 本地 + web 混合
        parts = []
        if local_context_text:
            parts.append(f"{local_context_text}\n")
        parts.append(web_text)
        merged_text = "\n".join(parts)
        source_mix = "mixed"
        confidence_level = "medium"

    logger.info(
        "[crag][merge] action=%s local_chars=%d web_results=%d final_chars=%d",
        action, len(local_context_text), len(filtered_web), len(merged_text)
    )

    return MergedContext(
        merged_text=merged_text,
        web_sources=web_sources,
        confidence_level=confidence_level,
        source_mix=source_mix,
        web_used=True,
    )


# ============================================================
# 辅助：从 SearchResult 构建 context_text
# ============================================================
def chunks_to_context_text(chunks: list[Any], max_chars: int = 1500) -> str:
    """把本地 chunks 列表格式化为 context_text（兼容 SearchResult 对象）"""
    if not chunks:
        return "（未检索到相关健康档案）"

    lines = []
    total_chars = 0

    for i, chunk in enumerate(chunks, 1):
        chunk_text = getattr(chunk, "chunk_text", str(chunk))
        title = getattr(chunk, "title", "")
        score = getattr(chunk, "score", 0.0)

        if len(chunk_text) > 300:
            chunk_text = chunk_text[:300] + "..."

        if title:
            line = f"[{i}] 【{title}】{chunk_text} (相关度: {score:.2f})"
        else:
            line = f"[{i}] {chunk_text} (相关度: {score:.2f})"

        total_chars += len(line) + 1
        if total_chars > max_chars:
            remaining = max_chars - total_chars + len(line)
            if remaining > 50:
                lines.append(line[:remaining] + "...(截断)")
            break

        lines.append(line)

    if not lines:
        return "（检索结果过于分散，无法整理）"

    header = f"【参考健康档案】（共 {len(chunks)} 条相关记录）\n"
    return header + "\n".join(lines)
