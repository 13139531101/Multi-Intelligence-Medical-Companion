"""
Core client functionality
"""

import os
import time
import sys
import json
import asyncio
import logging
import traceback
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
import shutil
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp import ClientSession
from anyio import ClosedResourceError

from .utils import load_mcp_config_from_file
from .providers.openai import generate_with_openai
from .providers.deepseek import generate_with_deepseek
from .providers.anthropic import generate_with_anthropic
from .providers.ollama import generate_with_ollama
from .providers.dashscope import generate_with_dashscope
# 将 lmstudio 的导入改为可选，避免未安装第三方包导致整体导入失败
try:
    from .providers.lmstudio import generate_with_lmstudio
except Exception as e:  # 包括 ImportError
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    _logger.warning(f"lmstudio provider unavailable, fallback to stub: {e}")
    async def generate_with_lmstudio(conversation, model_cfg, all_functions, stream: bool = False):
        msg = "Provider 'lmstudio' is not available in this environment. Please install its dependencies or switch provider."
        if stream:
            async def err_gen():
                yield {"assistant_text": msg, "tool_calls": []}
                if False: yield
            return err_gen()
        return {"assistant_text": msg, "tool_calls": []}
from .providers.vllm import generate_with_vllm
from .providers.bytedance import generate_with_bytedance
from .providers.zhipu import generate_with_zhipu

logger = logging.getLogger(__name__)


class SSEMCPClient:
    """Implementation for a SSE-based MCP server."""

    def __init__(self, server_name: str, url: str):
        self.server_name = server_name
        self.url = url
        self.tools = []
        self._streams_context = None
        self._session_context = None
        self.session = None

    async def start(self):
        try:
            self._streams_context = sse_client(url=self.url, sse_read_timeout=None)
            streams = await self._streams_context.__aenter__()

            self._session_context = ClientSession(*streams)
            self.session = await self._session_context.__aenter__()

            # Initialize
            await self.session.initialize()
            return True
        except Exception as e:
            logger.error(f"Server {self.server_name}: SSE connection error: {str(e)}")
            return False

    async def list_tools(self):
        if not self.session:
            return []
        try:
            response = await self.session.list_tools()
            # 将 pydantic 模型转换为字典格式
            self.tools = [
                Tool(tool.name, tool.description, tool.inputSchema) for tool in response.tools
            ]
            return self.tools
        except Exception as e:
            logger.error(f"Server {self.server_name}: List tools error: {str(e)}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict, retries: int = 2, delay: float = 1.0,):
        if not self.session:
            return {"error": "MCP SSE Not connected"}

        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        attempt = 0
        while attempt < retries:
            try:
                logger.info(f"开始使用SSE MCP协议调用工具，tool_name: {tool_name}, arguments: {arguments}")
                response = await self.session.call_tool(tool_name, arguments, read_timeout_seconds=timedelta(seconds=20))
                # 将 pydantic 模型转换为字典格式
                response_data = response.model_dump() if hasattr(response, 'model_dump') else response
                if response_data.get("isError"):
                    # 说明发生了错误，那么进行重试
                    logger.error("你的MCP的函数没有进行try和except封装，调用工具时，工具出现了异常，等待1秒后重试")
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue
                else:
                    return response_data
            except ClosedResourceError as e:
                logger.warning(f"Session closed: {e.__repr__()}, attempting to restart session.")
                await self.cleanup()
                status = await self.start()  # 重新建立 session
                if status:
                    logger.info("Session restarted successfully.")
                else:
                    logger.error("Failed to restart session.")
                attempt += 1
                await asyncio.sleep(delay)
            except Exception as e:
                attempt += 1
                logger.warning(
                    f"Error executing tool: {e.__repr__()}. Attempt {attempt} of {retries}."
                )
                if attempt < retries:
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error("Max retries reached. Failing.")
                    raise

    async def stop(self):
        await self.cleanup()
    async def cleanup(self):
        try:
            if self.session and self._session_context:
                try:
                    await self._session_context.__aexit__(None, None, None)
                except (ClosedResourceError, ValueError) as e:
                    logger.debug(f"SSE session context already closed: {e!r}")
            if self._streams_context:
                try:
                    await self._streams_context.__aexit__(None, None, None)
                except (ClosedResourceError, ValueError) as e:
                    logger.debug(f"SSE streams context already closed: {e!r}")
        except Exception as e:
            logger.warning(f"Error cleaning up SSE client: {e.__repr__()}")
        finally:
            # 释放引用并在 Windows 上给事件循环一点时间清理后台 I/O 任务
            self.session = None
            self._session_context = None
            self._streams_context = None
            if sys.platform.startswith("win"):
                try:
                    await asyncio.shield(asyncio.sleep(0.05))
                except BaseException:
                    pass


class MCPClient:
    """Manages MCP server connections and tool execution."""

    def __init__(self, server_name: str, command, args=None, env=None, cwd=None) -> None:
        self.name: str = server_name
        self.config: dict[str, Any] = {"command": command, "args": args, "env": env, "cwd": cwd}
        self.stdio_context: Any | None = None
        self.session: ClientSession | None = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self.tools = []

    async def start(self) -> bool:
        """Initialize the server connection."""
        if self.config["command"] == "npx":
            command = shutil.which("npx")
            if command is None:
                logger.error(f"npx命令没有安装，请先进行安装")
        elif self.config["command"] == "uv":
            command = shutil.which("uv")
            if command is None:
                logger.error(f"uv命令没有安装，请先进行安装")
        else:
            command = self.config["command"]
        if command is None:
            raise ValueError("The command must be a valid string and cannot be None.")

        server_params = StdioServerParameters(
            command=command,
            args=self.config["args"],
            env={**os.environ, **self.config["env"]}
            if self.config.get("env")
            else None,
        )
        prev_cwd = os.getcwd()
        try:
            # Respect configured working directory for launching the MCP server process
            cfg_cwd = self.config.get("cwd")
            logger.info(f"[MCP][{self.name}] Launching: command={command} args={self.config['args']} cwd={cfg_cwd}")
            # EXTRA DEBUG PRINTS FOR STARTUP DIAGNOSIS
            try:
                print(f"[MCP][{self.name}] Launching: {command} {' '.join(self.config['args'] or [])} cwd={cfg_cwd}")
            except Exception:
                pass
            if cfg_cwd:
                try:
                    os.chdir(cfg_cwd)
                except Exception as e:
                    logger.warning(f"切换到配置的cwd失败: {cfg_cwd}, 将尝试继续。错误: {e}")

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self.session = session
            return True
        except Exception as e:
            logger.exception(f"Error initializing server {self.name}: {e}")
            # EXTRA DEBUG PRINTS FOR ERROR DETAILS
            try:
                import traceback as _tb
                print(f"[MCP][{self.name}] Error initializing: {e!r}")
                print(_tb.format_exc())
            except Exception:
                pass
            await self.cleanup()
            return False
        finally:
            # Always restore previous working directory to avoid side effects on the host process
            try:
                if os.getcwd() != prev_cwd:
                    os.chdir(prev_cwd)
            except Exception as e:
                logger.warning(f"恢复工作目录失败: {e}")

    async def list_tools(self) -> list[Any]:
        """List available tools from the server.

        Returns:
            A list of available tools.

        Raises:
            RuntimeError: If the server is not initialized.
        """
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        tools_response = await self.session.list_tools()
        tools = []

        for item in tools_response:
            if isinstance(item, tuple) and item[0] == "tools":
                tools.extend(
                    Tool(tool.name, tool.description, tool.inputSchema)
                    for tool in item[1]
                )
        # 工具名称
        self.tools = tools
        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        retries: int = 2,
        delay: float = 1.0,
    ) -> Any:
        """Execute a tool with retry mechanism.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.
            retries: Number of retry attempts.
            delay: Delay between retries in seconds.

        Returns:
            Tool execution result.

        Raises:
            RuntimeError: If server is not initialized.
            Exception: If tool execution fails after all retries.
        """
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        attempt = 0
        while attempt < retries:
            try:
                try:
                    timeout_env = os.environ.get("MCP_READ_TIMEOUT_SEC", "45")
                    timeout_sec = int(timeout_env)
                    if timeout_sec < 10:
                        timeout_sec = 10
                    if timeout_sec > 120:
                        timeout_sec = 120
                except Exception:
                    timeout_sec = 45
                logger.info(f"执行工具: {tool_name}...，最多等待{timeout_sec}秒")
                response = await self.session.call_tool(tool_name, arguments, read_timeout_seconds=timedelta(seconds=timeout_sec))
                response_data = response.model_dump() if hasattr(response, 'model_dump') else response
                if response_data.get("isError"):
                    # 说明发生了错误，那么进行重试
                    logger.error("你的MCP的函数没有进行try和except封装，调用工具时，工具出现了异常，等待1秒后重试")
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue
                else:
                    return response_data
            except ClosedResourceError as e:
                logger.warning(f"Session closed: {e.__repr__()}, attempting to restart session.")
                await self.cleanup()
                status = await self.start()  # 重新建立 session
                if status:
                    logger.info("Session restarted successfully.")
                else:
                    logger.error("Failed to restart session.")
                attempt += 1
                await asyncio.sleep(delay)
            except Exception as e:
                attempt += 1
                logger.warning(
                    f"Error executing tool '{tool_name}': {e}. Attempt {attempt} of {retries}."
                )
                if attempt < retries:
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Max retries reached for tool '{tool_name}'. Error: {e}. Traceback: {traceback.format_exc()}")
                    raise

    async def stop(self):
        await self.cleanup()
    async def cleanup(self) -> None:
        """Clean up server resources."""
        async with self._cleanup_lock:
            try:
                try:
                    await self.exit_stack.aclose()
                except (ClosedResourceError, ValueError) as e:
                    # 在 Windows 上 stdio 管道已关闭时，anyio 可能抛出 ValueError/ClosedResourceError，忽略即可
                    logger.debug(f"Exit stack already closed or stdio pipe closed: {e!r}")
                self.session = None
                self.stdio_context = None
            except Exception as e:
                logger.error(f"Error during cleanup of server {self.name}: {e}")
            finally:
                if sys.platform.startswith("win"):
                    # 给事件循环一次机会清理后台 I/O 任务，避免 ValueError: I/O operation on closed pipe 警告
                    try:
                        await asyncio.shield(asyncio.sleep(0.05))
                    except BaseException:
                        pass


class Tool:
    """Represents a tool with its properties and formatting."""

    def __init__(
        self, name: str, description: str, input_schema: dict[str, Any]
    ) -> None:
        self.name: str = name
        self.description: str = description
        self.input_schema: dict[str, Any] = input_schema

    def format_for_llm(self) -> str:
        """Format tool information for LLM.

        Returns:
            A formatted string describing the tool.
        """
        args_desc = []
        if "properties" in self.input_schema:
            for param_name, param_info in self.input_schema["properties"].items():
                arg_desc = (
                    f"- {param_name}: {param_info.get('description', 'No description')}"
                )
                if param_name in self.input_schema.get("required", []):
                    arg_desc += " (required)"
                args_desc.append(arg_desc)

        return f"""
Tool: {self.name}
Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""


async def generate_text(conversation: List[Dict], model_cfg: Dict,
                       all_functions: List[Dict], stream: bool = False) -> Union[Dict, AsyncGenerator]:
    """
    Generate text using the specified provider.

    Args:
        conversation: The conversation history
        model_cfg: Configuration for the model
        all_functions: Available functions for the model to call
        stream: Whether to stream the response

    Returns:
        If stream=False: Dict containing assistant_text and tool_calls
        If stream=True: AsyncGenerator yielding chunks of assistant text and tool calls
    """
    provider = model_cfg.get("provider", "").lower()

    # --- Streaming Case ---
    if stream:
        if provider == "openai":
            # *** Return the generator object directly ***
            generator_coroutine = generate_with_openai(conversation, model_cfg, all_functions, stream=True)
            # If generate_with_openai itself *is* the async generator, await it to get the generator object
            # If it returns a coroutine that *needs* awaiting to get the generator, await it.
            # Let's assume the first await gets the generator object needed for async for.
            return await generator_coroutine # Return the awaitable generator object
        elif provider == "vllm":
            # *** Return the generator object directly ***
            generator_coroutine = generate_with_vllm(conversation, model_cfg, all_functions, stream=True)
            # Await the coroutine returned by the async generator function call
            # to get the actual async generator object.
            return await generator_coroutine # Return the awaitable generator object
        elif provider == "bytedance":
            # *** Return the generator object directly ***
            generator_coroutine = generate_with_bytedance(conversation, model_cfg, all_functions, stream=True)
            # Await the coroutine returned by the async generator function call
            # to get the actual async generator object.
            return await generator_coroutine # Return the awaitable generator object
        elif provider == "deepseek":
            # *** Return the generator object directly ***
            generator_coroutine = generate_with_deepseek(conversation, model_cfg, all_functions, stream=True)
            # Await the coroutine returned by the async generator function call
            # to get the actual async generator object.
            return await generator_coroutine # Return the awaitable generator object
        elif provider == "zhipu":
            # *** Return the generator object directly ***
            generator_coroutine = generate_with_zhipu(conversation, model_cfg, all_functions, stream=True)
            # Await the coroutine returned by the async generator function call
            # to get the actual async generator object.
            return await generator_coroutine # Return the awaitable generator object
        elif provider in ["anthropic", "ollama", "lmstudio"]:
             # This part needs to be an async generator that yields the *single* result
             async def wrap_response():
                 # Call the non-streaming function
                 if provider == "anthropic":
                     result = await generate_with_anthropic(conversation, model_cfg, all_functions)
                 elif provider == "ollama":
                     result = await generate_with_ollama(conversation, model_cfg, all_functions)
                 elif provider == "lmstudio":
                     result = await generate_with_lmstudio(conversation, model_cfg, all_functions)
                 else: # Should not happen based on outer check, but good practice
                     result = {"assistant_text": f"Unsupported provider '{provider}'", "tool_calls": []}
                 # Yield the complete result as a single item in the stream
                 yield result
             # *** Return the RESULT OF CALLING wrap_response() ***
             return wrap_response() # Return the async generator OBJECT
        else:
             # Fallback for unsupported streaming providers
             async def empty_gen():
                 yield {"assistant_text": f"Unsupported streaming provider '{provider}'", "tool_calls": []}
                 # The 'if False:' trick ensures this is treated as an async generator
                 if False: yield
             return empty_gen()

    # --- Non-Streaming Case ---
    else:
        if provider == "openai":
            return await generate_with_openai(conversation, model_cfg, all_functions, stream=False)
        elif provider == "deepseek":
            return await generate_with_deepseek(conversation, model_cfg, all_functions, stream=False)
        elif provider == "zhipu":
            return await generate_with_zhipu(conversation, model_cfg, all_functions, stream=False)
        elif provider == "bytedance":
            return await generate_with_bytedance(conversation, model_cfg, all_functions, stream=False)
        elif provider == "vllm":
            return await generate_with_vllm(conversation, model_cfg, all_functions, stream=False)
        elif provider == "dashscope" or provider == "qwen":
            return await generate_with_dashscope(conversation, model_cfg, all_functions, stream=False)
        elif provider == "anthropic":
            return await generate_with_anthropic(conversation, model_cfg, all_functions)
        elif provider == "ollama":
            return await generate_with_ollama(conversation, model_cfg, all_functions)
        elif provider == "lmstudio":
            try:
                from .providers.lmstudio import generate_with_lmstudio
            except Exception as e:  # 包括 ImportError
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"lmstudio provider unavailable, fallback to stub: {e}")
                async def generate_with_lmstudio(conversation, model_cfg, all_functions, stream: bool = False):
                    msg = "Provider 'lmstudio' is not available in this environment. Please install its dependencies or switch provider."
                    if stream:
                        async def err_gen():
                            yield {"assistant_text": msg, "tool_calls": []}
                            if False: yield
                        return err_gen()
                    return {"assistant_text": msg, "tool_calls": []}
        else:
            return {"assistant_text": f"Unsupported provider '{provider}'", "tool_calls": []}

async def log_messages_to_file(messages: List[Dict], functions: List[Dict], log_path: str):
    """
    Log messages and function definitions to a JSONL file.

    Args:
        messages: List of messages to log
        functions: List of function definitions
        log_path: Path to the log file
    """
    try:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Append to file
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "messages": messages,
                "functions": functions
            }) + "\n")
    except Exception as e:
        logger.error(f"Error logging messages to {log_path}: {str(e)}")

async def process_tool_call(tc: Dict, servers: Dict[str, MCPClient], quiet_mode: bool) -> Optional[Dict]:
    """Process a single tool call and return the result"""
    func_name = tc["function"]["name"]
    func_args_str = tc["function"].get("arguments", "{}")
    try:
        func_args = json.loads(func_args_str)
    except:
        func_args = {}

    # Inject user_id fallback if missing or placeholder
    try:
        uid = func_args.get("user_id")
        if (uid is None) or (isinstance(uid, str) and uid.strip() in ("", "current_user", "<当前用户>", "<用户>", "user")):
            env_uid = os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID")
            if env_uid and isinstance(env_uid, str) and env_uid.strip():
                func_args["user_id"] = env_uid.strip()
        elif isinstance(uid, str) and uid.strip().lower() == "default_user":
            env_uid = os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID")
            if env_uid and isinstance(env_uid, str):
                euid = env_uid.strip()
                if euid and euid.lower() != "default_user":
                    func_args["user_id"] = euid
    except Exception:
        pass

    parts = func_name.split("_", 1)
    if len(parts) != 2:
        return {
            "role": "tool",
            "tool_call_id": tc["id"],
            "name": func_name,
            "content": json.dumps({"error": "Invalid function name format"})
        }

    srv_name, tool_name = parts
    logger.info(f"\n调用process_tool_call开始获取运行MCP工具{tool_name} from {srv_name} {json.dumps(func_args, ensure_ascii=False)}")

    if srv_name not in servers:
        print(f"错误：注意，模型生成的服务器{srv_name}不在服务器列表中，请检查配置文件，或者查看你的mcp配置是否包含了特殊字符_")
        return {
            "role": "tool",
            "tool_call_id": tc["id"],
            "name": func_name,
            "content": json.dumps({"error": f"Unknown server: {srv_name}"})
        }

    # Get the tool's schema
    tool_schema = None
    for tool in servers[srv_name].tools:
        if tool.name == tool_name:
            tool_schema = tool.input_schema
            break

    if tool_schema:
        # Ensure required parameters are present
        required_params = tool_schema.get("required", [])
        for param in required_params:
            if param not in func_args:
                return {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": json.dumps({"error": f"Missing required parameter: {param}"})
                }
    logger.info(f"开始调用call_tool: {tool_name}")
    result = await servers[srv_name].call_tool(tool_name, func_args)
    if result is None:
        result_content = f"工具调用失败: {tool_name}"
    elif "error" in result:
        result_content = result["error"]
    else:
        result_content = "\n".join(content["text"] for content in result["content"])
    logger.info(f"工具{tool_name}运行结果: {result_content}")
    if os.environ.get("TOOL_RESULT_HANDLE"):
        # 动态加载todo
        from tool_result import tool_process_result
        tool_res = tool_process_result(tool_name, result_content)
        if isinstance(tool_res, dict):
            data = tool_res.get("data", [])
            result_content = tool_res.get("contents")
        else:
            data = tool_res
            result_content = tool_res
        return {
            "role": "tool",
            "tool_call_id": tc["id"],
            "name": func_name,
            "content": result_content,
            "data": data  #函数的结果的原始数据
        }
    return {
        "role": "tool",
        "tool_call_id": tc["id"],
        "name": func_name,
        "content": result_content,
    }
