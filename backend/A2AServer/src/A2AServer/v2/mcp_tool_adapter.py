"""
PHA v2 MCP 工具适配器（阶段2-4）

**作用**：
- 把现有 `mcpserver/*_tool.py` 的函数封装成 LangChain 1.x `BaseTool`
- 阶段2-4：手动 adapter（不引入 langchain-mcp-adapters，零额外依赖）
- 阶段2-5 可选：升级为 `langchain-mcp-adapters`（官方方案）

**设计原则**：
- 失败不阻塞：tool 加载失败返回空列表
- 元数据保留：保留原有 tool 的 name / description / params
"""
from __future__ import annotations

import logging
import inspect
from typing import Any, Callable

logger = logging.getLogger(__name__)


def load_mcp_tools(agent_name: str) -> list:
    """
    加载指定 agent 的 MCP 工具列表，返回 LangChain BaseTool 实例

    Args:
        agent_name: agent 标识（health_advisor / health_records / ...）

    Returns:
        list of BaseTool（LangChain 1.x 标准）
    """
    # 延迟导入，避免循环依赖
    try:
        from langchain_core.tools import BaseTool
    except ImportError:
        logger.warning("[mcp_tool_adapter] langchain_core 不可用")
        return []

    # 工具清单（按 agent 划分，阶段2-4 手动维护）
    tool_specs = _get_tool_specs(agent_name)

    tools = []
    for spec in tool_specs:
        try:
            tool = _wrap_to_base_tool(spec, BaseTool)
            if tool is not None:
                tools.append(tool)
        except Exception as e:
            logger.warning(
                "[mcp_tool_adapter] 包装工具失败: %s -> %s", spec.get("name"), e
            )

    logger.info(
        "[mcp_tool_adapter] agent=%s loaded %d tools: %s",
        agent_name,
        len(tools),
        [t.name for t in tools],
    )
    return tools


def _get_tool_specs(agent_name: str) -> list[dict]:
    """
    返回 agent 对应的工具规格列表

    阶段2-4 暂时用占位（每个 agent 1-2 个示例工具）
    阶段2-5 会扫描 mcpserver/ 目录自动发现
    """
    # TODO 阶段2-5: 改为自动扫描 backend/<Agent>/mcpserver/*_tool.py
    if agent_name == "health_advisor":
        return [
            {
                "name": "symptom_lookup",
                "description": "根据症状名查询可能的健康风险与建议",
                "func": _stub_symptom_lookup,
            },
            {
                "name": "knowledge_search",
                "description": "在医疗知识库中搜索相关信息",
                "func": _stub_knowledge_search,
            },
        ]
    elif agent_name == "health_records":
        return [
            {
                "name": "ocr_extract",
                "description": "从图片/PDF 中提取检查报告文本",
                "func": _stub_ocr,
            },
        ]
    elif agent_name == "medication_reminder":
        return [
            {
                "name": "drug_safety_check",
                "description": "检查多种药物的相互作用与禁忌",
                "func": _stub_drug_check,
            },
        ]
    elif agent_name == "visit_summary":
        return [
            {
                "name": "summarize_visits",
                "description": "汇总历史就诊记录生成摘要",
                "func": _stub_summarize,
            },
        ]
    return []


def _wrap_to_base_tool(spec: dict, base_tool_cls) -> Any:
    """把 spec 包装成 LangChain BaseTool"""
    tool_name = spec["name"]
    tool_desc = spec["description"]
    func = spec["func"]

    # 动态创建 BaseTool 子类（Pydantic v2：name/description 用 Pydantic 字段）
    try:
        # LangChain 1.x 风格：用 pydantic Field
        from pydantic import Field

        class _Tool(base_tool_cls):
            name: str = Field(default=tool_name)
            description: str = Field(default=tool_desc)

            def _run(self, **kwargs) -> str:
                try:
                    result = func(**kwargs)
                    return str(result)
                except Exception as e:
                    return f"Error: {e}"

            async def _arun(self, **kwargs) -> str:
                try:
                    if inspect.iscoroutinefunction(func):
                        result = await func(**kwargs)
                    else:
                        result = func(**kwargs)
                    return str(result)
                except Exception as e:
                    return f"Error: {e}"

    except Exception:
        # 旧版 langchain_core 兼容
        class _Tool(base_tool_cls):
            name = tool_name
            description = tool_desc

            def _run(self, *args, **kwargs) -> str:
                try:
                    return str(func(*args, **kwargs))
                except Exception as e:
                    return f"Error: {e}"

            async def _arun(self, *args, **kwargs) -> str:
                try:
                    if inspect.iscoroutinefunction(func):
                        return str(await func(*args, **kwargs))
                    return str(func(*args, **kwargs))
                except Exception as e:
                    return f"Error: {e}"

    try:
        return _Tool()
    except Exception as e:
        # 兜底：返回 None 让上层跳过
        logger.debug("[mcp_tool_adapter] 实例化失败 %s: %s", tool_name, e)
        return None


# ============================================================
# Stub 工具实现（占位，阶段2-5 替换为真实 MCP 工具）
# ============================================================
def _stub_symptom_lookup(symptom: str) -> str:
    return (
        f"[MOCK] 症状分析：{symptom} 建议多休息、多饮水，"
        "如持续超过 3 天请就医（占位实现，需替换为真实医疗知识库）。"
    )


def _stub_knowledge_search(query: str) -> str:
    return f"[MOCK] 知识库检索：{query} 的相关结果（占位实现）。"


def _stub_ocr(image_url: str = "") -> str:
    return f"[MOCK] OCR 提取文本（占位实现）：{image_url}"


def _stub_drug_check(drugs: list = None) -> str:
    return f"[MOCK] 药物相互作用检查：{drugs or []}（占位实现）。"


def _stub_summarize(patient_id: str = "") -> str:
    return f"[MOCK] 就诊摘要生成：{patient_id}（占位实现）。"
