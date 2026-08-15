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
    discover_phacore_tools,        # 阶段48-19
    load_mcp_tool_function,
)

logger = logging.getLogger(__name__)

# 缓存：避免每次重新加载
_TOOL_CACHE: dict[str, list] = {}

# 阶段48-13: 进程级设置 (跨 asyncio task)
import os

# 阶段48-13: thread-local context 用来跨 async 边界传递 user_id
import contextvars as _cv
_current_user_id: _cv.ContextVar[str] = _cv.ContextVar("pha_current_user_id", default="")
_current_conversation_id: _cv.ContextVar[str] = _cv.ContextVar("pha_current_conversation_id", default="")


def set_user_context(user_id: str = "", conversation_id: str = "") -> None:
    """阶段48-13: 在 tool 调用前 set user_id/conversation_id context.

    让 BaseTool 包装器自动注入到 tool args.
    v2_agent.stream 应当在进入循环前调用一次.

    双向设置:
    1. ContextVar (同 task 内)
    2. Module-level fallback (跨 task / LangGraph tool_node)
    """
    global _MODULE_LEVEL_USER_ID
    _current_user_id.set(user_id or "")
    _current_conversation_id.set(conversation_id or "")
    _MODULE_LEVEL_USER_ID = user_id or ""


def _inject_user_id_if_needed(kwargs: dict, tool_name: str) -> dict:
    """阶段48-13: 缺 user_id 时从 context 注入. 避免 LLM 忘记传.

    优先级:
    1. kwargs 已有 user_id (LLM 自己传了)
    2. ContextVar (在同一个 asyncio task 内的 tool_node 调用)
    3. 全局 fallback (LangGraph 跨 task 调用的情况)

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

    # 阶段48-13: 优先用 ContextVar (同 task 内)
    ctx_uid = _current_user_id.get()
    if not ctx_uid:
        # 阶段48-13 fallback: LangGraph tool_node 在 worker task 里跑,
        # ContextVar 可能没传到. 退化到 module-level
        ctx_uid = _MODULE_LEVEL_USER_ID or ""
    if not ctx_uid:
        # 阶段48-13 fallback2: 进程级 (同 Python 进程内全局)
        ctx_uid = os.environ.get("PHA_USER_ID", "")

    if ctx_uid:
        new_kwargs = dict(kwargs)
        new_kwargs["user_id"] = ctx_uid
        return new_kwargs
    return kwargs


# 阶段48-13 fallback: 模块级变量, 用来跨 ContextVar 失效场景 (如 LangGraph tool_node)
_MODULE_LEVEL_USER_ID: str = ""


# 阶段48-13: cache tool signatures so _inject_user_id_if_needed doesn't refllect
_TOOL_SIG_CACHE: dict[str, inspect.Signature] = {}


def register_tool_sig(name: str, sig: inspect.Signature) -> None:
    """_wrap_function_as_base_tool 调用注册 sig."""
    _TOOL_SIG_CACHE[name] = sig


def load_mcp_tools(agent_name: str, *, use_real: bool = True, transport: str = "streamable_http") -> list:
    """
    加载指定 agent 的 MCP 工具列表

    Args:
        agent_name: agent 标识（health_advisor / health_records / ...）
        use_real: True 用真实 MCP 工具；False 用 stub
        transport: 阶段48-15: 'streamable_http' (默认) / 'stdio' / 'inprocess'

    Returns:
        list of LangChain BaseTool
    """
    cache_key = f"{agent_name}:{use_real}:{transport}"
    if cache_key in _TOOL_CACHE:
        return _TOOL_CACHE[cache_key]

    if not use_real:
        tools = _load_stub_tools(agent_name)
        _TOOL_CACHE[cache_key] = tools
        return tools

    tools = _load_real_mcp_tools(agent_name, transport=transport)
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


# 阶段48-19: PhaCore 共享工具加载
# PhaCore 不是独立 agent, 它的工具是被 4 个 agent re-export 的.
def load_phacore_tools(
    modules: tuple = ("ocr",),          # ("ocr", "reminder", "storage", ...)
) -> list:
    """加载 PhaCore 共享工具集中指定模块的工具.

    Args:
        modules: PhaCore 子模块名 tuple, e.g. ("ocr",) 或 ("ocr", "reminder")

    Returns:
        list of LangChain BaseTool

    用法 (在 sub_agents.py):
        class HealthRecordsV2(V2Agent):
            def get_tools(self):
                return (
                    load_mcp_tools("health_records", ...) +
                    load_phacore_tools(("ocr",))
                )
    """
    cache_key = f"phacore:{','.join(modules)}"
    if cache_key in _TOOL_CACHE:
        return _TOOL_CACHE[cache_key]

    try:
        # 阶段48-19: 动态 import (按需), 避免 hardcoded 全部不存在
        import importlib
        module_map = {}
        for mod_name in modules:
            try:
                mod = importlib.import_module(f"PhaCore.mcpserver.shared_{mod_name}")
                module_map[mod_name] = mod
            except ImportError as e:
                logger.warning("[PhaCore] module shared_%s 不可用: %s", mod_name, e)
        if not module_map:
            logger.warning("[PhaCore] 没 load 任何模块, modules=%s", modules)
            return []
        loaded_tools = []
        for mod_name, mod in module_map.items():
            try:
                # 阶段48-19: 通过 AST 知 tool 列表, 用 _extract_mcp_tools_from_source
                # 现在直接 enumerate module 的所有 @mcp.tool() 装饰函数
                for tool_name in _list_phacore_tool_names(mod):
                    tool_func = getattr(mod, tool_name, None)
                    if tool_func is None:
                        continue
                    lc_tool = _wrap_phacore_func_as_lc_tool(tool_func, tool_name)
                    loaded_tools.append(lc_tool)
            except Exception as e:
                logger.warning("[PhaCore] %s 加载失败: %s", mod_name, e)

        _TOOL_CACHE[cache_key] = loaded_tools
        logger.info(
            "[PhaCore] loaded %d tools from modules=%s",
            len(loaded_tools), modules,
        )
        return loaded_tools
    except Exception as e:
        logger.warning("[PhaCore] PhaCore 包不可用: %s", e)
        return []


def _list_phacore_tool_names(mod) -> list[str]:
    """list PhaCore module 里的所有 tool 函数 (mcp.tool 装饰的).

    通过 introspection: 函数对象有 __wrapped__ / location hint.
    Phase 1 简化为: 直接拿 @mcp.tool() 下的函数, fallback dir().
    """
    import inspect
    # 拿到模块源代码
    try:
        src_file = inspect.getsourcefile(mod)
        if not src_file:
            return [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None)) and n not in ("get_mcp_server", "mcp") and n in ("extract_text_from_image", "validate_medical_document")]
        src = open(src_file, encoding="utf-8").read()
        # Reuse _extract_mcp_tools_from_source
        tools = _extract_mcp_tools_from_source(src)
        return [t["name"] for t in tools]
    except Exception:
        # Hardcoded fallback
        return ["extract_text_from_image", "validate_medical_document"] if "shared_ocr" in str(mod) else []


def _wrap_phacore_func_as_lc_tool(func, func_name: str):
    """包装 PhaCore 函数成 LangChain BaseTool (轻量, 不依赖 fastmcp runtime)."""
    from langchain_core.tools import tool as langchain_tool

    desc = (func.__doc__ or "").strip() or f"PhaCore tool: {func_name}"

    @langchain_tool
    def wrapped(**kwargs):
        """PhaCore {func_name} wrapper."""
        return func(**kwargs)

    wrapped.name = func_name
    wrapped.description = desc
    return wrapped


def _load_real_mcp_tools(agent_name: str, *, transport: str = "stdio") -> list:
    """从 backend/<Agent>/mcpserver 加载真实 MCP 工具.

    阶段48-15: 支持 3 种 transport.
      - transport='stdio': spawn 子进程 + JSON-RPC over stdio
      - transport='streamable_http': HTTP/SSE (MCP 协议)
      - transport='inprocess': legacy in-process import

    默认 'stdio'. HTTP 失败时 fallback stdio, 再失败 fallback in-process.
    """
    if transport == "stdio":
        stdio_tools = _load_stdio_mcp_tools(agent_name)
        if stdio_tools:
            return stdio_tools
        logger.warning(
            "[mcp_tool_adapter] agent=%s stdio 返回 0 tool, 退到 in-process",
            agent_name,
        )
    elif transport == "streamable_http":
        http_tools = _load_http_mcp_tools(agent_name)
        if http_tools:
            return http_tools
        logger.warning(
            "[mcp_tool_adapter] agent=%s http 返回 0 tool, 退到 stdio",
            agent_name,
        )
        stdio_tools = _load_stdio_mcp_tools(agent_name)
        if stdio_tools:
            return stdio_tools

    return _load_inprocess_mcp_tools(agent_name)


def _load_stdio_mcp_tools(agent_name: str) -> list:
    """阶段48-15: 真正的 MCP stdio transport.

    每个 agent 自动跑 1 个 sub-process, 一次性 import 所有 *_tool.py,
    JSON-RPC over stdio 通讯. LangChain 侧用 MultiServerMCPClient / load_mcp_tools.
    """
    try:
        import os
        from .mcp_discover import AGENT_DIR_MAP
        dir_name = AGENT_DIR_MAP.get(agent_name, agent_name)
        # 容器内固定路径; host 上用 repo_root + backend
        backend_dir = "/app/backend"

        mcpserver_dir = os.path.join(backend_dir, dir_name, "mcpserver")
        if not os.path.isdir(mcpserver_dir):
            logger.warning("[mcp_tool_adapter:stdio] dir not found: %s", mcpserver_dir)
            return []

        tool_files = sorted(
            f for f in os.listdir(mcpserver_dir)
            if f.endswith("_tool.py") and not f.startswith("_")
        )
        if not tool_files:
            return []

        # spawn 1 个整合 stdio server, 该 server 接受 agent_name 然后动态导入
        # 用一个统一的入口: backend.<Agent>.mcpserver._stdio_starter
        starter_pkg = f"{dir_name}.mcpserver._stdio_starter"
        starter_path = os.path.join(mcpserver_dir, "_stdio_starter.py")
        _ensure_stdio_starter(starter_path, dir_name, tool_files, mcpserver_dir)

        # 启动子进程 (stdin/stdout 通讯)
        from mcp import StdioServerParameters, stdio_client
        from mcp.client.session import ClientSession
        from langchain_mcp_adapters.tools import load_mcp_tools as lc_load_tools

        async def _init():
            # 把 DB / API 等关键 env vars 透传给 subprocess
            child_env = {"PYTHONPATH": backend_dir, "PATH": os.environ.get("PATH", "")}
            for key in (
                "MEMORY_DB_HOST", "MEMORY_DB_PORT", "MEMORY_DB_USER",
                "MEMORY_DB_PASSWORD", "MEMORY_DB_NAME", "MEMORY_DB_SSLMODE",
                "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_BASE_URL",
                "OPENAI_API_BASE", "OPENAI_BASE_URL",
            ):
                v = os.environ.get(key)
                if v is not None:
                    child_env[key] = v
            params = StdioServerParameters(
                command="python",
                args=["-m", starter_pkg],
                env=child_env,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    lc_tools = await lc_load_tools(session=session)
                    return lc_tools

        # FastAPI 是同步 thread, asyncio.run 不能在已有 loop 里跑, 用 ThreadPoolExecutor
        import asyncio, concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            tools = pool.submit(asyncio.run, _init()).result(timeout=60)

        # 阶段48-15: 给 tool 加 user_id 注入包装器
        wrapped = []
        for t in tools:
            try:
                wrapped.append(_wrap_mcp_tool_with_userid(t))
            except Exception as e:
                logger.debug("[mcp_tool_adapter:stdio] wrap %s fail: %s", t.name, e)
                wrapped.append(t)
        logger.info(
            "[mcp_tool_adapter:stdio] agent=%s loaded %d tools via stdio",
            agent_name, len(wrapped),
        )
        return wrapped

    except Exception as e:
        logger.warning(
            "[mcp_tool_adapter:stdio] agent=%s 加载失败: %s", agent_name, e,
        )
        return []


# 阶段48-15: HTTP transport port 分配 (每个 agent 1 个)
_AGENT_HTTP_PORT = {
    "health_advisor": 9101,
    "health_records": 9102,
    "medication_reminder": 9103,
    "visit_summary": 9104,
}

# 阶段48-15: 当前进程里已启动的 HTTP server (避免重复 spawn)
_HTTP_SERVER_PROCS: dict[str, "subprocess.Popen"] = {}


def _load_http_mcp_tools(agent_name: str) -> list:
    """阶段48-15: 通过 Streamable HTTP 调 MCP server.

    1) spawn 一个 sub-process 跑 `_http_starter.py` (它跑 mcp.run('streamable-http'))
    2) 等 service up
    3) 用 load_mcp_tools(connection={'transport': 'streamable_http', 'url': ...})
    """
    port = _AGENT_HTTP_PORT.get(agent_name)
    if port is None:
        logger.warning("[mcp_tool_adapter:http] agent=%s 没分配 port", agent_name)
        return []

    import os
    from .mcp_discover import AGENT_DIR_MAP
    dir_name = AGENT_DIR_MAP.get(agent_name, agent_name)
    backend_dir = "/app/backend"
    mcpserver_dir = os.path.join(backend_dir, dir_name, "mcpserver")
    if not os.path.isdir(mcpserver_dir):
        return []
    tool_files = sorted(
        f for f in os.listdir(mcpserver_dir)
        if f.endswith("_tool.py") and not f.startswith("_")
    )
    if not tool_files:
        return []

    starter_path = os.path.join(mcpserver_dir, "_http_starter.py")
    _ensure_http_starter(starter_path, dir_name, tool_files, mcpserver_dir, port)

    # 确保 server 启动
    starter_pkg = f"{dir_name}.mcpserver._http_starter"
    if agent_name not in _HTTP_SERVER_PROCS:
        _spawn_http_server(agent_name, starter_pkg, port, backend_dir)
    base_url = f"http://127.0.0.1:{port}/mcp"

    # 调 load_mcp_tools via HTTP
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools as lc_load_tools

        async def _init():
            from langchain_mcp_adapters.sessions import StreamableHttpConnection
            conn = StreamableHttpConnection(
                transport="streamable_http",
                url=base_url,
            )
            # session= 是 positional, 必须显式 key
            tools = await lc_load_tools(None, connection=conn)
            return tools

        import asyncio, concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            tools = pool.submit(asyncio.run, _init()).result(timeout=60)

        # 阶段48-15: 给 tools 包一层: 缺 user_id 时自动从 PHA_USER_ID / ContextVar 注入
        # 这样 LLM 调 {}(空 args) 时, tool 拿到 current user_id
        wrapped = []
        for t in tools:
            try:
                wrapped.append(_wrap_mcp_tool_with_userid(t))
            except Exception as e:
                logger.debug("[mcp_tool_adapter:http] wrap %s fail: %s", t.name, e)
                wrapped.append(t)

        logger.info(
            "[mcp_tool_adapter:http] agent=%s loaded %d tools via http://127.0.0.1:%d",
            agent_name, len(wrapped), port,
        )
        return wrapped

    except Exception as e:
        logger.warning(
            "[mcp_tool_adapter:http] agent=%s load失败: %s", agent_name, e,
        )
        return []


def _wrap_mcp_tool_with_userid(t):
    """阶段48-15: 给 langchain_mcp_adapters 返的 BaseTool 注入 user_id.

    2 step fix:
      1. 修改 args_schema: user_id 字段 default="" 让 Pydantic 允许空 args
         (因为 LC-MCP 用 dynamic model 创建, user_id 没有 default)
      2. _run 时注入 PHA_USER_ID (LLM 不会传 user_id, 我们从 context 拿)
    """
    sig = None
    try:
        underlying = None
        if hasattr(t, "_run"):
            underlying = t._run
            if hasattr(underlying, "__wrapped__"):
                underlying = underlying.__wrapped__
            import inspect as _inspect
            try:
                sig = _inspect.signature(underlying)
            except Exception:
                sig = None
    except Exception:
        pass

    # 2 sources: (a) args_schema 里 user_id, (b) tool 本身 user_id in signature
    schema = getattr(t, "args_schema", None)
    has_user_id = False
    if schema is None:
        has_user_id = False
    elif isinstance(schema, dict):
        has_user_id = "user_id" in schema.get("properties", {})
    elif hasattr(schema, "model_fields"):
        has_user_id = "user_id" in schema.model_fields

    # If sig-based detection failed (LC-MCP wrapping), use schema-based
    if not has_user_id and not (sig and "user_id" in sig.parameters):
        return t

    # Step 1: 改 args_schema 让 user_id optional
    # LC-MCP 工具的 args_schema 是 dict (JSON Schema) 而不是 Pydantic Model
    try:
        if schema is None:
            return t
        # case A: dict (JSON Schema)
        if isinstance(schema, dict):
            if "user_id" in schema.get("properties", {}):
                required = schema.get("required", [])
                if "user_id" in required:
                    schema["required"] = [r for r in required if r != "user_id"]
                # Set default value too
                if "default" not in schema["properties"]["user_id"]:
                    schema["properties"]["user_id"].setdefault("default", "")
        # case B: Pydantic model
        elif hasattr(schema, "model_fields"):
            if "user_id" in schema.model_fields:
                from pydantic import Field, create_model
                fields = {}
                for name, field in schema.model_fields.items():
                    if name == "user_id":
                        fields[name] = (str, Field(default=""))
                    else:
                        fields[name] = (str, Field(default=field.default if field.default is not None else ...))
                new_schema = create_model(f"Wrapped_{t.name}_args", **fields)
                t.args_schema = new_schema
                if hasattr(t, "args"):
                    t.args = new_schema
        # 强制 invalidate Pydantic cached memo
        if hasattr(t, "_tool_call_schema_memo"):
            try:
                t._tool_call_schema_memo = None
            except Exception:
                pass
    except Exception as e:
        logger.debug("[userid-wrap] schema modify failed: %s", e)

    # Step 2: wrap _run + arun (LangChain LC-MCP StructuredTool uses arun for async)
    # Get both sync _run and async coroutine for full coverage
    original_run = getattr(t, "_run", None)
    original_arun = getattr(t, "coroutine", None) or getattr(t, "_arun", None)

    def _resolve_user_id(kwargs):
        """从 kwargs / ContextVar / module-level / env 取 user_id (优先级)."""
        return (
            (kwargs.get("user_id") or "").strip()
            or _current_user_id.get()
            or _MODULE_LEVEL_USER_ID
            or os.environ.get("PHA_USER_ID", "")
        )

    def wrapped_run(**kwargs):
        cur = _resolve_user_id(kwargs)
        if cur:
            kwargs["user_id"] = cur
        return original_run(**kwargs)

    # Wrap both sync + async
    t._run = wrapped_run
    if original_arun is not None:
        async def wrapped_arun(**kwargs):
            cur = _resolve_user_id(kwargs)
            if cur:
                kwargs["user_id"] = cur
            return await original_arun(**kwargs)

        try:
            t.coroutine = wrapped_arun
        except Exception:
            pass
        try:
            t._arun = wrapped_arun
        except Exception:
            pass
    return t


def _ensure_http_starter(starter_path: str, dir_name: str, tool_files: list, mcpserver_dir: str, port: int) -> None:
    """生成 `_http_starter.py` 类似 stdio 但 transport='streamable-http'."""
    # 复用 _ensure_stdio_starter 的 AST 扫描逻辑
    import ast
    tool_func_names = []
    for tf in tool_files:
        tf_path = os.path.join(mcpserver_dir, tf)
        try:
            src = open(tf_path, "r", encoding="utf-8").read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                has_mcp_tool = False
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        fn = dec.func
                        if (isinstance(fn, ast.Attribute) and fn.attr == "tool"
                                and isinstance(fn.value, ast.Name) and fn.value.id == "mcp"):
                            has_mcp_tool = True
                            break
                    elif isinstance(dec, ast.Attribute):
                        if dec.attr == "tool":
                            has_mcp_tool = True
                            break
                if has_mcp_tool:
                    tool_func_names.append((tf.removesuffix(".py"), node.name))
        except Exception:
            pass

    body_lines = [
        '"""Auto-generated HTTP MCP starter (阶段48-15).',
        "Streamable HTTP transport on port given by agent_name mapping.",
        '"""',
        'import sys',
        'import os',
        'import importlib',
        'sys.path.insert(0, "/app/backend")  # noqa: E402',
        'from mcp.server.fastmcp import FastMCP',
        '',
        '_mcp = FastMCP("PHA-Agent-HTTP")',
        f'_AGENT_DIR = "{dir_name}"',
        f'_TOOL_FUNCS = {tool_func_names!r}',
        '_PORT = int(os.environ.get("PHA_MCP_PORT", "0"))',
        '',
        '_imported = []',
        'for _mod_name, _func_name in _TOOL_FUNCS:',
        '    try:',
        '        _mod = importlib.import_module(f"{_AGENT_DIR}.mcpserver.{_mod_name}")',
        '        _fn = getattr(_mod, _func_name)',
        '        _mcp.add_tool(_fn, name=_func_name, description=(_fn.__doc__ or "").split(chr(10))[0])',
        '    except Exception as e:',
        '        print(f"[http_starter] fail {_mod_name}.{_func_name}: {e!r}", file=sys.stderr)',
        '',
        'if __name__ == "__main__":',
        '    _mcp.settings.port = _PORT',
        '    _mcp.run(transport="streamable-http")',
    ]
    body = "\n".join(body_lines) + "\n"
    if os.path.isfile(starter_path):
        existing = open(starter_path, "r", encoding="utf-8").read()
        if existing == body:
            return
    with open(starter_path, "w", encoding="utf-8") as f:
        f.write(body)


def _spawn_http_server(agent_name: str, starter_pkg: str, port: int, backend_dir: str) -> None:
    """启动 1 个 HTTP MCP server sub-process. 跨 query 复用 (singleton)."""
    import subprocess, time, os, socket, sys
    child_env = {"PYTHONPATH": backend_dir, "PHA_MCP_PORT": str(port), "PATH": os.environ.get("PATH", "")}
    for key in (
        "MEMORY_DB_HOST", "MEMORY_DB_PORT", "MEMORY_DB_USER",
        "MEMORY_DB_PASSWORD", "MEMORY_DB_NAME", "MEMORY_DB_SSLMODE",
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_BASE_URL",
        "OPENAI_API_BASE", "OPENAI_BASE_URL",
    ):
        v = os.environ.get(key)
        if v is not None:
            child_env[key] = v

    cmd = [sys.executable, "-m", starter_pkg] # type: ignore
    try:
        proc = subprocess.Popen(
            cmd,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        logger.warning("[mcp_tool_adapter:http] spawn fail %s: %s", agent_name, e)
        return

    # 等端口 up
    def _port_open() -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    deadline = time.time() + 15
    while time.time() < deadline:
        if _port_open():
            break
        if proc.poll() is not None:
            logger.warning(
                "[mcp_tool_adapter:http] agent=%s process exited code=%s stderr=%s",
                agent_name, proc.returncode, proc.stderr.read()[:200] if proc.stderr else "",
            )
            return
        time.sleep(0.3)
    else:
        logger.warning("[mcp_tool_adapter:http] agent=%s 启动 timeout", agent_name)
        return

    _HTTP_SERVER_PROCS[agent_name] = proc
    logger.info("[mcp_tool_adapter:http] agent=%s HTTP server up at port %d", agent_name, port)


def _ensure_stdio_starter(starter_path: str, dir_name: str, tool_files: list, mcpserver_dir: str) -> None:
    """生成 / 覆盖 `_stdio_starter.py`.

    关键 trick: `@mcp.tool()` 装饰不影响函数本身. 我们用静态分析 (AST) 找
    哪些函数被 `@mcp.tool()` 装饰, 然后用 `add_tool(fn, name=name)` 显式加到
    合并 mcp 实例.

    1. 创建 1 个 FastMCP 主实例
    2. import 每个 *_tool.py → 触发它们的装饰 + 自身的 `mcp.add_tool` 注册
       但我们的合并实例是独立的, 所以**副作用**到它们的 module-level mcp
       实例不会落到主 mcp. 因此我们必须手动 `add_tool`.
    3. AST 扫每个 *_tool.py 找 `@mcp.tool()` 函数名 (用同一 discover 逻辑)
    4. mcp.run(transport='stdio')

    所以 1 process 1 server = 合并主 mcp 实例有所有 agent tools.
    """
    # 静态扫找 tool 函数名
    import ast
    tool_func_names = []
    for tf in tool_files:
        tf_path = os.path.join(mcpserver_dir, tf)
        try:
            src = open(tf_path, "r", encoding="utf-8").read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                has_mcp_tool = False
                for dec in node.decorator_list:
                    # @mcp.tool() 或 @mcp.tool
                    if isinstance(dec, ast.Call):
                        fn = dec.func
                        if (isinstance(fn, ast.Attribute) and fn.attr == "tool"
                                and isinstance(fn.value, ast.Name) and fn.value.id == "mcp"):
                            has_mcp_tool = True
                            break
                    elif isinstance(dec, ast.Attribute):
                        if dec.attr == "tool":
                            has_mcp_tool = True
                            break
                if has_mcp_tool:
                    tool_func_names.append((tf.removesuffix(".py"), node.name))
        except Exception:
            pass

    body_lines = [
        '"""Auto-generated stdio MCP starter (阶段48-15).',
        "1 process = 1 FastMCP 主实例 = 包含 agent 下所有 *_tool.py 的 @mcp.tool() 函数.",
        '"""',
        'import sys',
        'import importlib',
        'sys.path.insert(0, "/app/backend")  # noqa: E402',
        'from mcp.server.fastmcp import FastMCP',
        '',
        '_mcp = FastMCP("PHA-Agent-Stdio")',
        f'_AGENT_DIR = "{dir_name}"',
        f'_TOOL_FUNCS = {tool_func_names!r}',   # [(tool_file_module, func_name), ...]
        '',
        '_imported = []',
        'for _mod_name, _func_name in _TOOL_FUNCS:',
        '    try:',
        '        if _mod_name not in _imported:',
        '            _mod = importlib.import_module(f"{_AGENT_DIR}.mcpserver.{_mod_name}")',
        '            _imported.append(_mod_name)',
        '        _mod = importlib.import_module(f"{_AGENT_DIR}.mcpserver.{_mod_name}")',
        '        _fn = getattr(_mod, _func_name)',
        '        _mcp.add_tool(_fn, name=_func_name, description=(_fn.__doc__ or "").split(chr(10))[0])',
        '    except Exception as e:',
        '        print(f"[stdio_starter] fail {_mod_name}.{_func_name}: {e!r}", file=sys.stderr)',
        '',
        'if __name__ == "__main__":',
        '    _mcp.run(transport="stdio")',
    ]
    body = "\n".join(body_lines) + "\n"

    if os.path.isfile(starter_path):
        existing = open(starter_path, "r", encoding="utf-8").read()
        if existing == body:
            return  # 没变
    with open(starter_path, "w", encoding="utf-8") as f:
        f.write(body)


def _load_inprocess_mcp_tools(agent_name: str) -> list:
    """阶段48-15 兼容: in-process import 函数路径 (fallback)."""
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
            # 阶段48-13: user_id 字段是 mcp_tool_adapter 注入的, 不是 LLM 必传的
            # 让它 default = "" 避免 Pydantic validation 拒绝空 args
            if param_name == "user_id":
                default = ""
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
