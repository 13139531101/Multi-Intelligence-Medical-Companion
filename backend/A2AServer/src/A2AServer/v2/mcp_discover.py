"""
PHA v2 MCP 工具自动发现器（阶段2-5）

**作用**：
- 扫描 `backend/<Agent>/mcpserver/*_tool.py`
- 用 `inspect.getsource` 静态分析或 `importlib` 动态加载
- 提取所有用 `@mcp.tool()` 装饰的函数
- 返回 {(module_name, func_name): (callable, name, description, sig)}

**两种发现策略**：
1. **静态扫描**（推荐）：用 ast 解析源码，不执行 module（避免 DB 连接等副作用）
2. **动态加载**（可选）：import module 后从 mcp 实例取 tool 列表

我们默认用**策略 1（AST 静态扫描）**，避免引入 `mcp.tool()` 执行带来的副作用。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# 仓库根目录（兼容不同 cwd）
_REPO_ROOT = Path(__file__).resolve().parents[5]  # .../A2AServer/src/A2AServer/v2/ -> A2AServer
if not (_REPO_ROOT / "backend").exists():
    _REPO_ROOT = Path(os.getcwd())
    if not (_REPO_ROOT / "backend").exists():
        # 继续往上找
        for parent in Path(__file__).resolve().parents:
            if (parent / "backend").exists():
                _REPO_ROOT = parent
                break


# Agent 名 -> backend 子目录名
AGENT_DIR_MAP = {
    "health_advisor": "HealthAdvisor",
    "health_records": "HealthRecordsManager",
    "medication_reminder": "MedicationReminder",
    "visit_summary": "VisitSummaryGenerator",
}


def _find_mcp_tool_files(agent_name: str) -> list[Path]:
    """找到指定 agent 下的所有 *tool.py"""
    dir_name = AGENT_DIR_MAP.get(agent_name, agent_name)
    mcpserver_dir = _REPO_ROOT / "backend" / dir_name / "mcpserver"
    if not mcpserver_dir.exists():
        logger.debug("[mcp_discover] 目录不存在: %s", mcpserver_dir)
        return []
    return sorted(mcpserver_dir.glob("*_tool.py"))


def _extract_mcp_tools_from_source(source: str) -> list[dict]:
    """
    用 AST 静态解析 Python 源码，找出所有 @mcp.tool() 装饰的函数

    返回 [{name, description, args, file, line}, ...]
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning("[mcp_discover] 解析源码失败: %s", e)
        return []

    results = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # 检查装饰器
        has_mcp_tool = False
        for dec in node.decorator_list:
            # @mcp.tool() 或 @mcp.tool
            if isinstance(dec, ast.Call):
                func = dec.func
                # mcp.tool(...)
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "tool"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "mcp"
                ):
                    has_mcp_tool = True
                    break
            elif isinstance(dec, ast.Attribute):
                if dec.attr == "tool":
                    has_mcp_tool = True
                    break

        if not has_mcp_tool:
            continue

        # 提取 docstring 作为 description
        description = ast.get_docstring(node) or ""

        # 提取参数签名
        args = []
        for arg in node.args.args:
            args.append(arg.arg)

        # 提取函数名
        results.append(
            {
                "name": node.name,
                "description": description,
                "args": args,
                "line": node.lineno,
            }
        )

    return results


def discover_mcp_tools_static(agent_name: str) -> list[dict]:
    """
    静态发现 agent 下的所有 MCP 工具（不执行 module）

    返回：[{tool_module, tool_name, description, args, file_path}, ...]
    """
    tool_files = _find_mcp_tool_files(agent_name)
    all_tools = []

    for tool_file in tool_files:
        try:
            source = tool_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("[mcp_discover] 读文件失败 %s: %s", tool_file, e)
            continue

        tools = _extract_mcp_tools_from_source(source)
        for t in tools:
            t["file_path"] = str(tool_file)
            t["agent_name"] = agent_name
            t["tool_module"] = tool_file.stem  # diagnosis_tool -> diagnosis_tool
            all_tools.append(t)

    logger.info(
        "[mcp_discover] agent=%s found %d MCP tools in %d files",
        agent_name,
        len(all_tools),
        len(tool_files),
    )
    return all_tools


def _safe_load_module(file_path: str, module_name: str, timeout_sec: float = 3.0):
    """
    动态加载模块（兼容 mcp tool 文件）

    处理：
    - 加 repo root 到 sys.path（让相对 import 工作）
    - 用 importlib.util 加载
    - 超时保护（避免某些 module 顶层连 DB / 网络卡死）
    """
    # 准备 sys.path
    file_path = Path(file_path).resolve()
    paths_to_add = [
        str(file_path.parent.parent),  # backend/HealthAdvisor
        str(file_path.parent.parent.parent),  # backend
        str(_REPO_ROOT),
        str(_REPO_ROOT / "backend"),
    ]
    for p in paths_to_add:
        if p and p not in sys.path:
            sys.path.insert(0, p)

    # 加载
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        logger.warning("[mcp_discover] 加载 spec 失败: %s", file_path)
        return None

    import threading

    result = {"module": None, "error": None}

    def _load():
        try:
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            result["module"] = m
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_load, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)

    if t.is_alive():
        logger.debug("[mcp_discover] 加载超时 (%.1fs): %s", timeout_sec, file_path.name)
        return None

    if result["error"]:
        logger.debug("[mcp_discover] 加载失败 %s: %s", file_path.name, result["error"])
        return None

    return result["module"]


def load_mcp_tool_function(agent_name: str, tool_module: str, tool_name: str) -> Callable | None:
    """
    动态加载并返回真实的 MCP tool 函数

    注意：会执行模块顶层代码（可能触发 DB 连接、模型加载等）
    """
    file_path = (
        _REPO_ROOT
        / "backend"
        / AGENT_DIR_MAP.get(agent_name, agent_name)
        / "mcpserver"
        / f"{tool_module}.py"
    )
    if not file_path.exists():
        logger.warning("[mcp_discover] 文件不存在: %s", file_path)
        return None

    full_module_name = f"v2_mcp_{agent_name}_{tool_module}"
    module = _safe_load_module(str(file_path), full_module_name)
    if module is None:
        return None

    func = getattr(module, tool_name, None)
    if func is None:
        logger.warning("[mcp_discover] 模块里找不到 %s", tool_name)
        return None

    return func
