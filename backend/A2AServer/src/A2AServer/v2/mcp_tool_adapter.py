"""
PHA v2 MCP 工具适配器（阶段2-5）

**作用**：
- 自动扫描 `backend/<Agent>/mcpserver/*_tool.py` 里的 `@mcp.tool()` 装饰函数
- 动态加载这些 MCP 工具函数
- 包装成 LangChain 1.x `BaseTool`

**两阶段发现**：
1. 静态扫描（不执行 module）→ 拿到工具元数据（name/description/args）
2. 动态加载（按需）→ 拿到真实可调用函数

**降级机制**：
- 如果某个 agent 目录下没有 *tool.py，自动用 stub
- 如果加载真实工具失败（缺依赖等），降级到 stub
"""
from __future__ import annotations

import logging
import inspect
from typing import Any

from .mcp_discover import (
    discover_mcp_tools_static,
    load_mcp_tool_function,
)

logger = logging.getLogger(__name__)

# 缓存：避免每次重新加载
_TOOL_CACHE: dict[str, list] = {}

# 阶段48-13: thread-local context 用来跨 async 边界传递 user_id
import contextvars as _cv
_current_user_id: _cv.ContextVar[str] = _cv.ContextVar("pha_current_user_id", default="")
_current_conversation_id: _cv.ContextVar[str] = _cv.ContextVar("pha_current_conversation_id", default="")


def set_user_context(user_id: str = "", conversation_id: str = "") -> None:
    """阶段48-13: 在 tool 调用前 set user_id/conversation_id context.

    让 BaseTool 包装器自动注入到 tool args.
    v2_agent.stream 应当在进入循环前调用一次.
    """
    _current_user_id.set(user_id or "")
    _current_conversation_id.set(conversation_id or "")


def _inject_user_id_if_needed(kwargs: dict, tool_name: str) -> dict:
    """阶段48-13: 缺 user_id 时从 context 注入. 避免 LLM 忘记传.

    只在 tool 的 args_schema 里出现 'user_id' 字段时注入.
    """
    # 工具不要求 user_id 直接放过
    sig = _TOOL_SIG_CACHE.get(tool_name)
    if sig is None:
        return kwargs
    if "user_id" not in sig.parameters:
        return kwargs

    # 已有 user_id 且非空 → 跳过
    cur = kwargs.get("user_id")
    if cur and str(cur).strip():
        return kwargs

    ctx_uid = _current_user_id.get()
    if ctx_uid:
        new_kwargs = dict(kwargs)
        new_kwargs["user_id"] = ctx_uid
        return new_kwargs
    return kwargs


# 阶段48-13: cache tool signatures so _inject_user_id_if_needed doesn't refllect
_TOOL_SIG_CACHE: dict[str, inspect.Signature] = {}


def register_tool_sig(name: str, sig: inspect.Signature) -> None:
    """_wrap_function_as_base_tool 调用注册 sig."""
    _TOOL_SIG_CACHE[name] = sig


def load_mcp_tools(agent_name: str, *, use_real: bool = True) -> list:
    """
    加载指定 agent 的 MCP 工具列表

    Args:
        agent_name: agent 标识（health_advisor / health_records / ...）
        use_real: True 用真实 MCP 工具；False 用 stub

    Returns:
        list of LangChain BaseTool
    """
    cache_key = f"{agent_name}:{use_real}"
    if cache_key in _TOOL_CACHE:
        return _TOOL_CACHE[cache_key]

    if not use_real:
        tools = _load_stub_tools(agent_name)
        _TOOL_CACHE[cache_key] = tools
        return tools

    tools = _load_real_mcp_tools(agent_name)
    if not tools:
        logger.warning(
            "[mcp_tool_adapter] agent=%s 真实工具为空，回退 stub", agent_name
        )
        tools = _load_stub_tools(agent_name)

    _TOOL_CACHE[cache_key] = tools
    logger.info(
        "[mcp_tool_adapter] agent=%s loaded %d tools",
        agent_name,
        len(tools),
    )
    return tools


def _load_real_mcp_tools(agent_name: str) -> list:
    """从 backend/<Agent>/mcpserver 加载真实 MCP 工具"""
    try:
        from langchain_core.tools import BaseTool
    except ImportError:
        return []

    # 1. 静态扫描
    tool_specs = discover_mcp_tools_static(agent_name)
    if not tool_specs:
        return []

    # 2. 过滤：跳过有副作用 / 集成类工具（避免循环依赖 / DB 连接等）
    SKIP_TOOLS = {
        # 集成类
        "a2a_integration_tool",         # 避免循环
        "memory_integration_tool",      # memory 系统独立
        # DB / 数据层（顶层会连接 DB，本地无容器会失败）
        "database_tool",
        "storage_tool",
        # 异步分析（依赖外部 worker）
        "async_analysis_tool",
    }
    tool_specs = [t for t in tool_specs if t["tool_module"] not in SKIP_TOOLS]

    # 3. 动态加载每个工具
    tools = []
    for spec in tool_specs:
        try:
            func = load_mcp_tool_function(
                agent_name, spec["tool_module"], spec["name"]
            )
            if func is None:
                continue

            tool = _wrap_function_as_base_tool(
                func=func,
                name=spec["name"],
                description=spec["description"] or f"Tool from {spec['tool_module']}",
                BaseTool=BaseTool,
            )
            if tool is not None:
                # 阶段7 性能优化：自动应用工具调用缓存
                try:
                    from .tool_cache import wrap_tool_with_cache
                    tool = wrap_tool_with_cache(tool, use_cache=True)
                except ImportError:
                    pass
                tools.append(tool)
        except Exception as e:
            logger.debug(
                "[mcp_tool_adapter] 跳过 %s.%s: %s",
                spec["tool_module"],
                spec["name"],
                e,
            )
            continue

    return tools


def _wrap_function_as_base_tool(
    func, name: str, description: str, BaseTool
) -> Any:
    """把普通函数包装成 LangChain BaseTool"""
    # 检查函数签名
    sig = inspect.signature(func)
    is_async = inspect.iscoroutinefunction(func)

    # 捕获到闭包里（避免与 inner class 字段同名）
    tool_name = name
    tool_desc = description
    tool_func = func
    tool_is_async = is_async
    tool_sig = sig

    # 阶段48-13: 注册 sig 让 _inject_user_id_if_needed 知道要不要注入 user_id
    try:
        register_tool_sig(name, sig)
    except Exception:
        pass

    try:
        from pydantic import Field, create_model

        # 用函数签名动态构建 args_schema
        fields = {}
        for param_name, param in tool_sig.parameters.items():
            annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
            default = param.default if param.default != inspect.Parameter.empty else ...
            fields[param_name] = (annotation, default)

        if fields:
            ArgsSchema = create_model(f"{tool_name}_args", **fields)  # type: ignore
        else:
            ArgsSchema = None

        class _Tool(BaseTool):
            name: str = Field(default=tool_name)
            description: str = Field(default=tool_desc)
            args_schema: type = Field(default=ArgsSchema) if ArgsSchema else None

            def _run(self, **kwargs) -> str:
                try:
                    # 过滤掉 LangChain 注入的多余字段
                    valid_kwargs = {k: v for k, v in kwargs.items() if k in tool_sig.parameters}
                    # 阶段48-13: 缺 user_id 时从 context 自动注入
                    valid_kwargs = _inject_user_id_if_needed(valid_kwargs, tool_name)
                    if not valid_kwargs and tool_sig.parameters:
                        return "Error: missing required arguments"

                    result = tool_func(**valid_kwargs)
                    if isinstance(result, (dict, list)):
                        import json
                        return json.dumps(result, ensure_ascii=False, default=str)
                    return str(result)
                except Exception as e:
                    return f"Error: {e}"

            async def _arun(self, **kwargs) -> str:
                try:
                    valid_kwargs = {k: v for k, v in kwargs.items() if k in tool_sig.parameters}
                    # 阶段48-13: 缺 user_id 时从 context 自动注入
                    valid_kwargs = _inject_user_id_if_needed(valid_kwargs, tool_name)
                    if tool_is_async:
                        result = await tool_func(**valid_kwargs)
                    else:
                        result = tool_func(**valid_kwargs)
                    if isinstance(result, (dict, list)):
                        import json
                        return json.dumps(result, ensure_ascii=False, default=str)
                    return str(result)
                except Exception as e:
                    return f"Error: {e}"

        return _Tool()
    except Exception as e:
        logger.debug("[mcp_tool_adapter] 包装失败 %s: %s", tool_name, e)
        return None


# ============================================================
# Stub 工具（真实工具加载失败时 fallback）
# ============================================================
def _load_stub_tools(agent_name: str) -> list:
    """加载 stub 工具（与原 v2 行为一致）"""
    try:
        from langchain_core.tools import BaseTool
    except ImportError:
        return []

    stub_specs = {
        "health_advisor": [
            ("symptom_lookup", "根据症状名查询可能的健康风险与建议", _stub_symptom_lookup),
            ("knowledge_search", "在医疗知识库中搜索相关信息", _stub_knowledge_search),
        ],
        "health_records": [
            ("ocr_extract", "从图片/PDF 中提取检查报告文本", _stub_ocr),
        ],
        "medication_reminder": [
            ("drug_safety_check", "检查多种药物的相互作用与禁忌", _stub_drug_check),
        ],
        "visit_summary": [
            ("summarize_visits", "汇总历史就诊记录生成摘要", _stub_summarize),
        ],
    }

    specs = stub_specs.get(agent_name, [])
    tools = []
    for name, desc, func in specs:
        try:
            from pydantic import Field

            class _Tool(BaseTool):
                name: str = Field(default=name)
                description: str = Field(default=desc)

                def _run(self, **kwargs) -> str:
                    return str(func(**kwargs))

                async def _arun(self, **kwargs) -> str:
                    return str(func(**kwargs))

            tools.append(_Tool())
        except Exception:
            pass
    return tools


def _stub_symptom_lookup(**kwargs) -> str:
    symptom = kwargs.get("symptoms", "未知")
    return (
        f"[STUB] 症状分析：{symptom} 建议多休息、多饮水"
        "（占位实现，未加载真实 MCP 工具）。"
    )


def _stub_knowledge_search(**kwargs) -> str:
    query = kwargs.get("query", "未知")
    return f"[STUB] 知识库检索：{query}（占位）。"


def _stub_ocr(**kwargs) -> str:
    return f"[STUB] OCR 提取文本（占位）"


def _stub_drug_check(**kwargs) -> str:
    return f"[STUB] 药物相互作用检查（占位）"


def _stub_summarize(**kwargs) -> str:
    return f"[STUB] 就诊摘要生成（占位）"
