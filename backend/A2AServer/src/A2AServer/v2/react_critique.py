"""
ReAct 反思模式 — response self-critique + optional revision

原理：
- Agent 生成初始回答
- 独立 critique 节点审视回答质量
- 若发现问题，触发 revision 生成修正版
- 最终回答可能是修订版或原版

Critique 维度（医疗场景）：
1. 准确性 - 诊断建议是否有依据
2. 完整性 - 是否覆盖用户所有问题
3. 安全性 - 是否有潜在危害（用药建议等）
4. 可操作性 - 建议是否具体可执行

Modern prompt injection:
- 模板字符串通过 .format() 注入变量，兼容 langchain 1.3.14
- SystemMessage + HumanMessage 直接构造，绕过 LCEL invoke 在该版本的兼容性问题
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

# ---- LangChain 探测 ----
_LANGCHAIN_OK = False
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
    _LANGCHAIN_OK = True
except ImportError as e:
    logger.warning("[react_critique] LangChain 不可用: %s", e)


# ============================================================
# Critique 结果
# ============================================================
class CritiqueResult:
    """Critique 结论"""
    def __init__(
        self,
        is_adequate: bool,
        issues: list[str],
        suggested_revision: str | None = None,
        reasoning: str = "",
    ):
        self.is_adequate = is_adequate  # True = 无需 revision
        self.issues = issues              # 发现的问题列表
        self.suggested_revision = suggested_revision  # 修订建议（如果需要）
        self.reasoning = reasoning        # 批判理由


# ============================================================
# Critique Prompt Template（纯字符串版本，避免 LCEL invoke 在 langchain 1.3.14 的兼容问题）
# ============================================================
CRITIQUE_SYSTEM_PROMPT = """你是一位严谨的医学内容审核员，负责审查 AI 健康助手的回答质量。

## 审核维度

1. **准确性** — 诊断/建议是否有充分依据，不臆测、不夸大
2. **完整性** — 是否覆盖用户所有子问题，无遗漏
3. **安全性** — 用药建议剂量是否明确，禁忌是否提醒，是否注明"请咨询医生"
4. **可操作性** — 建议是否具体可执行（时间/剂量/行为明确）
5. **透明度** — 不确定的地方是否主动说明局限性

## 输出格式

先给出 1-2 句总体评价，再逐维度分析。
最后结论：
- 若存在 1 个以上"安全性"或"准确性"问题 → **需要修订**
- 若仅为"可操作性"小建议 → **可接受**（无需强制修订）
- 若全部满足 → **优秀，无需修订**

注意：你的职责是把关，不是挑剔。对于有依据的回答应予以肯定。"""

CRITIQUE_HUMAN_TEMPLATE = """## 用户问题
{query}

## AI 回答
{response}

## 工具调用记录
{tool_calls}

请按审核维度逐项分析，并给出最终结论（是否需要修订）。"""

REVISION_SYSTEM_PROMPT = """你是一位资深的医学健康顾问 AI。你需要根据审核意见修订回答。

## 修订原则

1. **保留原意** — 不改变用户的核心问题
2. **修正错误** — 修正审核发现的准确性问题
3. **补充遗漏** — 补充用户问过但未覆盖的点
4. **加强安全** — 增加禁忌提示、剂量说明、"请咨询医生"等
5. **保持风格** — 语言风格应与原回答一致，专业但亲切

## 格式要求

直接输出修订后的完整回答（不需要标注哪里改了）。
如果原回答质量已经很好，可以原样返回。"""

REVISION_HUMAN_TEMPLATE = """## 用户问题
{query}

## 原回答
{original_response}

## 审核意见
{critique_issues}

请输出修订后的回答。"""


# ============================================================
# 内部 LLM 构造
# ============================================================
def _build_llm():
    """构造 critique 专用的 LLM（与主 agent 相同厂商）"""
    if not _LANGCHAIN_OK:
        return None

    if os.getenv("DEEPSEEK_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("PHA_LLM_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0,
        )
    elif os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_BASE"):
        model_name = os.getenv("PHA_LLM_MODEL", "gpt-4o-mini")
        if model_name.startswith("deepseek"):
            model_name = "gpt-4o-mini"
        return ChatOpenAI(
            model=model_name,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0,
        )
    return None


# ============================================================
# Critique 节点（用于 host_graph）
# ============================================================
async def critique_node(state: dict) -> dict:
    """
    ReAct 反思节点：审查 agent_response，输出 critique_result。

    放在 invoke_agent_node 之后、aggregate_node 之前。

    Args:
        state: HostState（包含 query, agent_response, tool_calls）

    Returns:
        {"critique_result": CritiqueResult, "final_response_text": str}
    """
    query = state.get("query", "")
    agent_response = state.get("agent_response", {})
    content = agent_response.get("content", "")
    tool_calls = agent_response.get("tool_calls", []) or []

    # 无内容时跳过 critique
    if not content or len(content.strip()) < 10:
        logger.debug("[react_critique] 内容过短，跳过 critique")
        return {
            "critique_result": CritiqueResult(
                is_adequate=True,
                issues=[],
                reasoning="内容过短，跳过审核",
            ).__dict__,
            "final_response_text": content,
        }

    # 构建工具调用摘要
    tool_calls_summary = "无工具调用"
    if tool_calls:
        tc_lines = []
        for tc in tool_calls:
            name = tc.get("name", "?")
            args = tc.get("args", {})
            if isinstance(args, dict):
                args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            else:
                args_str = str(args)
            tc_lines.append(f"- {name}({args_str})")
        tool_calls_summary = "\n".join(tc_lines)

    llm = _build_llm()
    if llm is None:
        logger.warning("[react_critique] LLM 不可用，跳过 critique")
        return {
            "critique_result": CritiqueResult(
                is_adequate=True,
                issues=[],
                reasoning="LLM 不可用，跳过审核",
            ).__dict__,
            "final_response_text": content,
        }

    try:
        # Step 1: Critique（直接格式化字符串，绕过 LCEL invoke 在 langchain 1.3.14 的兼容问题）
        critique_messages = [
            SystemMessage(content=CRITIQUE_SYSTEM_PROMPT),
            HumanMessage(content=CRITIQUE_HUMAN_TEMPLATE.format(
                query=query or "(未提供)",
                response=content or "(未提供)",
                tool_calls=tool_calls_summary or "(无)",
            )),
        ]
        critique_result = await llm.ainvoke(critique_messages)
        critique_text = critique_result.content if hasattr(critique_result, "content") else str(critique_result)

        # 解析 critique 结论
        needs_revision = any(kw in critique_text for kw in [
            "需要修订", "建议修订", "请修订", "存在安全隐患", "准确性存疑"
        ])
        issues = _extract_issues(critique_text)

        logger.info(
            "[react_critique] needs_revision=%s issues=%d query=%s",
            needs_revision, len(issues), query[:30]
        )

        critique_result_obj = CritiqueResult(
            is_adequate=not needs_revision,
            issues=issues,
            suggested_revision=None,
            reasoning=critique_text,
        )

        # Step 2: 若需要 revision，调用 revision LLM（直接格式化字符串）
        final_text = content
        if needs_revision and issues:
            try:
                revision_messages = [
                    SystemMessage(content=REVISION_SYSTEM_PROMPT),
                    HumanMessage(content=REVISION_HUMAN_TEMPLATE.format(
                        query=query or "(未提供)",
                        original_response=content or "(未提供)",
                        critique_issues="\n".join([f"- {iss}" for iss in issues]),
                    )),
                ]
                revision_result = await llm.ainvoke(revision_messages)
                revised = revision_result.content if hasattr(revision_result, "content") else str(revision_result)
                if revised and len(revised.strip()) > 10:
                    final_text = revised
                    critique_result_obj.suggested_revision = revised
                    logger.info("[react_critique] revision applied, len %d -> %d", len(content), len(revised))
            except Exception as e:
                logger.warning("[react_critique] revision failed: %s", e)

        return {
            "critique_result": critique_result_obj.__dict__,
            "final_response_text": final_text,
        }

    except Exception as e:
        logger.warning("[react_critique] critique failed: %s", e)
        return {
            "critique_result": CritiqueResult(
                is_adequate=True,
                issues=[],
                reasoning=f"审核异常: {e}",
            ).__dict__,
            "final_response_text": content,
        }


def _extract_issues(critique_text: str) -> list[str]:
    """从 critique 文本提取具体问题列表"""
    issues = []
    lines = critique_text.split("\n")
    for line in lines:
        line = line.strip()
        # 识别问题行：含 "问题"、"不足"、"缺失"、"警告" 等关键词
        if any(kw in line for kw in ["问题", "不足", "缺失", "警告", "建议", "注意", "需确认"]):
            # 去掉编号/emoji 等前缀，保留核心内容
            cleaned = line.lstrip("0123456789.-●◆✅❌⚠️💡🔴 ").strip()
            if cleaned:
                issues.append(cleaned)
    return issues[:5]  # 最多 5 个


# ============================================================
# 便捷函数（直接调用）
# ============================================================
async def critique_response(
    query: str,
    response: str,
    tool_calls: list[dict] | None = None,
) -> CritiqueResult:
    """
    独立调用 critique（不需要 host_graph state）

    用法:
        result = await critique_response(
            query="硝苯地平能和阿司匹林一起吃吗？",
            response="可以一起用...",
            tool_calls=[{"name": "search_drug_info", "args": {"drug_name": "硝苯地平"}}]
        )
        print(result.is_adequate, result.issues)
    """
    fake_state = {
        "query": query,
        "agent_response": {"content": response, "tool_calls": tool_calls or []},
    }
    result = await critique_node(fake_state)
    cr = result.get("critique_result", {})
    return CritiqueResult(
        is_adequate=cr.get("is_adequate", True),
        issues=cr.get("issues", []),
        suggested_revision=cr.get("suggested_revision"),
        reasoning=cr.get("reasoning", ""),
    )


__all__ = [
    "CritiqueResult",
    "critique_node",
    "critique_response",
]
