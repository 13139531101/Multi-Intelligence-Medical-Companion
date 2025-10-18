import collections
import copy
import logging
import os
import traceback
import json
import base64
from dotenv import load_dotenv
from typing import AsyncIterable, Any, Literal
from pydantic import BaseModel
from datetime import datetime

from A2AServer.mcp_client.client import *

logger = logging.getLogger(__name__)


def base64_to_dict(base64_str: str) -> dict:
    """将 Base64 字符串还原为 Python 字典"""
    try:
        json_bytes = base64.b64decode(base64_str)
        json_str = json_bytes.decode('utf-8')
        data = json.loads(json_str)
    except Exception as e:
          print(f"Error decoding Base64: {e}")
          return {}
    return data

class BasicAgent:
    """Agent to access Deep Search"""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, config_path="mcp_config.json", model_name="deepseek-chat",prompt_file="prompt.txt", provider="deepseek",
                 quiet_mode=False, log_messages_path=None):
        """
        Synchronous initialization.
        Loads config and sets up basic attributes.
        Asynchronous setup (starting servers, listing tools) is done in the 'setup' method.
        """
        self.config_path = config_path
        self.model_name = model_name
        self.quiet_mode = quiet_mode
        self.log_messages_path = log_messages_path

        self.file = load_mcp_config_from_file(config_path)
        config = self.file
        self.servers_cfg = config.get("mcpServers", {})
        self.models_cfg = config.get("models", [])
        assert os.path.exists(prompt_file), f"Agent prompt file 必须存在，请检查: {prompt_file}"
        # Choose a model (synchronous)
        self.chosen_model = {"model": model_name, "provider": provider, "prompt_file": prompt_file}
        self.is_ready = True

        # 可选启用记忆系统（支持 ENABLE_AGENT_MEMORY=false 与 SKIP_MEMORY_INIT=1 两种关闭方式）
        self.memory_system = None
        try:
            enable_memory_flag = os.getenv("ENABLE_AGENT_MEMORY", "true").lower()
            skip_memory_init = os.getenv("SKIP_MEMORY_INIT", "0") == "1"
            enable_memory = (enable_memory_flag == "true" or enable_memory_flag == "1") and not skip_memory_init
            if enable_memory:
                try:
                    from AgentMemorySystem.memory_system import AgentMemorySystem as AMS
                except Exception:
                    from memory_system import AgentMemorySystem as AMS
                self.memory_system = AMS()
                logger.info("Agent 记忆系统已启用")
            else:
                logger.info("Agent 记忆系统未启用（通过环境开关/跳过初始化）")
        except Exception as e:
            logger.warning(f"记忆系统初始化失败，将不启用：{e}")

        # Initialize attributes that will be populated asynchronously in setup()
        self.servers = {}
        self.all_functions = []
        self.session_conversations = collections.defaultdict(list) # Initial conversation might be built later in run() or here
        self.tool_ready = False
        # 只能做同步的事情，不能直接“等”异步的初始化完成，不能在这里初始化
        # loop = asyncio.get_event_loop()
        # try:
        #     self.tool_ready = loop.run_until_complete(self.setup_tools())
        # except RuntimeError:
        #     self.tool_ready = asyncio.run(self.setup_tools())


    async def setup_tools(self):
        """
        Asynchronous setup method.
        Starts servers and gathers tools.
        Returns True if setup was successful, False otherwise.
        """
        # 防止重复初始化：如果已预加载过并且服务器实例存在，则直接返回
        if self.tool_ready and self.servers:
            logger.info("MCP 工具已预加载，跳过重复初始化")
            return True
        if not self.is_ready:
             print("Agent cannot be set up: Model not found.")
             return False

        logger.info("Starting MCP servers...")
        successful_servers = {}
        all_functions = []
        # 初始化MCP的server
        for server_name, conf in self.servers_cfg.items():
            client = None
            if "url" in conf:  # SSE server
                client = SSEMCPClient(server_name, conf["url"])
            elif "command" in conf:  # Local process-based server
                 # 处理 cwd：如果未提供或是相对路径，尽量解析为可用的绝对路径；否则回退到配置目录
                 config_dir = os.path.dirname(os.path.abspath(self.config_path))
                 _cwd = conf.get("cwd")
                 if _cwd and not os.path.isabs(_cwd):
                     candidate1 = os.path.abspath(os.path.join(config_dir, _cwd))
                     candidate2 = os.path.abspath(_cwd)
                     if os.path.isdir(candidate1):
                         _cwd = candidate1
                     elif os.path.isdir(candidate2):
                         _cwd = candidate2
                     else:
                         logger.warning(f"[MCP] cwd 相对路径未能解析为存在的目录：{_cwd}，将使用配置目录作为工作目录。")
                         _cwd = config_dir
                 if not _cwd:
                     # 未提供 cwd，则默认使用配置目录，保证相对路径的 mcpserver/* 可被找到
                     _cwd = config_dir
                     logger.info(f"[MCP] 未提供 cwd，默认使用配置目录: {_cwd}")
                 client = MCPClient(
                      server_name=server_name,
                      command=conf.get("command"),
                      args=conf.get("args", []),
                      env=conf.get("env", {}),
                      cwd=_cwd
                 )
            else:
                 if not self.quiet_mode:
                     print(f"[WARN] Skipping server {server_name}: No 'url' or 'command' specified.")
                 continue

            try:
                # 启动 MCP 服务器，增加一次重试以提升稳定性（如 OCRTool）
                attempts = 0
                ok = False
                while attempts < 2 and not ok:
                    ok = await client.start()  # <-- AWAIT is valid here (inside async def)
                    if not ok:
                        attempts += 1
                        if not self.quiet_mode:
                            print(f"[WARN] Could not start server {server_name}, retry {attempts}/2")
                        await asyncio.sleep(0.8)
                if not ok:
                    if not self.quiet_mode:
                        print(f"[WARN] Could not start server {server_name}")
                    # Ensure client is stopped even if start failed
                    if client: await client.stop()
                    continue
                else:
                    logger.info(f"[MCP Tool OK] {server_name}")
                    successful_servers[server_name] = client

                    # gather tools
                    try:
                         tools = await client.list_tools() # <-- AWAIT is valid here
                         for t in tools:
                             input_schema = t.input_schema or {"type": "object", "properties": {}}
                             fn_def = {
                                 "name": f"{server_name}_{t.name}",
                                 "description": t.description,
                                 "parameters": input_schema
                             }
                             all_functions.append(fn_def)
                    except Exception as e:
                        if not self.quiet_mode:
                            print(f"[WARN] Error listing tools for {server_name}: {e}")
                        # Consider if failing to list tools should stop processing for this server


            except Exception as e: # Catch potential errors during client creation or start
                if not self.quiet_mode:
                    print(f"[WARN] Exception starting server {server_name}: {e}")
                # Ensure client is stopped if created before exception
                if 'client' in locals() and client:
                    await client.stop()


        self.servers = successful_servers
        self.all_functions = all_functions

        if not self.servers:
            error_msg = "No MCP servers could be started."
            logger.error(error_msg)
            self.tool_ready = False # Cannot run without servers
            return False

        logger.info(f"Found {len(self.all_functions)} tools: {json.dumps(self.all_functions, ensure_ascii=False)}")
        self.tool_ready = True # Setup was successful
        return True

    async def run_inference(self, user_query, sessionId, stream=True):
        """
        推理和工具的设置
        """
        if not self.tool_ready:
            #  如果没设置过相关的MCP工具
            await self.setup_tools()
        if not self.is_ready:
             print("Agent is not ready. Setup failed or model not found.")
             # Depending on requirements, you might return an error or raise an exception
             if stream:
                  async def error_gen(): yield "Agent setup failed."
                  return error_gen()
             return "Agent setup failed."


        # Build initial conversation (system message + user query)
        self._build_initial_conversation(sessionId, user_query) # This helper can be synchronous


        # try:
        if stream:
            return self._stream_response_generator(sessionId) # Returns an async generator
        else:
            return await self._non_stream_response(sessionId) # Returns the final text
        # finally:
        #     # Ensure cleanup is called when run() finishes or an exception occurs
        #     await self.cleanup() # <-- AWAIT is valid here

    def _build_initial_conversation(self, sessionId, user_query):
         # Helper method to build the initial conversation list (synchronous)
         self.conversation = []
         # 默认的prompt
         agent_prompt = "You are a helpful assistant."
         try:
             with open(self.chosen_model["prompt_file"], "r", encoding="utf-8") as f:
                 agent_prompt = f.read()
             self.session_conversations[sessionId].append({"role": "system", "content": agent_prompt})
         except Exception as e:
             logger.warning(f"Failed to read Agent prompt file: {e}")
             self.session_conversations[sessionId].append({"role": "system", "content": agent_prompt})
        # 加上当前的时间
         self.session_conversations[sessionId][0]['content'] = f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}。" + self.session_conversations[sessionId][0]['content']
         # 注入记忆上下文（若启用记忆系统）
         try:
             if self.memory_system:
                 agent_id = os.environ.get("AGENT_ID", "A2AAgent")
                 user_id = os.environ.get("USER_ID", sessionId)
                 memories = self.memory_system.search_memories(
                     query=user_query,
                     agent_id=agent_id,
                     user_id=user_id,
                     memory_types=["long_term", "working"],
                     limit=5,
                     min_similarity=0.5,
                 )
                 if memories:
                     summary_lines = []
                     for m in memories:
                         text = (m.get("content", {}) or {}).get("text") or m.get("text") or ""
                         if text:
                             summary_lines.append(f"- {text}")
                     if summary_lines:
                         memory_block = "\n".join(["相关历史记忆："] + summary_lines)
                         self.session_conversations[sessionId][0]['content'] = (
                             self.session_conversations[sessionId][0]['content'] + "\n" + memory_block
                         )
         except Exception as e:
             logger.warning(f"注入记忆上下文失败：{e}")
         self.session_conversations[sessionId].append({"role": "user", "content": user_query})
         print(f"发起的conversation: {self.session_conversations[sessionId]}")

    async def _stream_response_generator(self, sessionId):
         """Handles the streaming response logic (async generator)."""
         #分5种返回类型，1. reasoning, 2. normal,  4. tool_call, 5. tool_result
         while True:
             generator = await generate_text(self.session_conversations[sessionId], self.chosen_model, self.all_functions, stream=True)
             accumulated_text = ""
             tool_calls_processed = False

             async for chunk in generator: # AWAIT is used to iterate over the async generator
                 if chunk.get("is_chunk", False):
                     if chunk.get("token", False):
                         if chunk.get("is_reasoning"):
                             yield {"text": chunk["assistant_text"], "type": "reasoning"}
                         else:
                            yield {"text": chunk["assistant_text"], "type": "normal"} # YIELD is used in a generator
                     if not chunk.get("is_reasoning"):
                        accumulated_text += chunk["assistant_text"]
                 else:
                     remaining = chunk["assistant_text"][len(accumulated_text):]
                     if remaining:
                         yield {"text": remaining, "type": "reasoning"} # YIELD here as well 剩余文本

                     tool_calls = chunk.get("tool_calls", [])
                     if tool_calls:
                         for tc in tool_calls:
                             tc["type"] = "function"
                         assistant_message = {
                             "role": "assistant",
                             "content": chunk["assistant_text"],
                             "tool_calls": tool_calls
                         }
                         self.session_conversations[sessionId].append(assistant_message)
                         yield {"text": f"{json.dumps(tool_calls, ensure_ascii=False)}", "type": "tool_call"}

                         for tc in tool_calls:
                             if tc.get("function", {}).get("name"):
                                 # 对工具进行参数的修改
                                 result = await process_tool_call(tc, self.servers, self.quiet_mode) # AWAIT valid here
                                 if result:
                                     # 这里是工具的调用结果，那么只需要部分数据添加到LLM的会话中
                                     new_res = copy.deepcopy(result)
                                     if "data" in result:
                                         result.pop("data")
                                     self.session_conversations[sessionId].append(result)
                                     tool_calls_processed = True
                                     yield {"text": f"{json.dumps(new_res)}", "type": "tool_result"}
             if not tool_calls_processed:
                 break


    async def _non_stream_response(self, sessionId):
         """Handles the non-streaming response logic."""
         # Move the non-stream logic from original init here
         final_text = ""
         while True:
             gen_result = await generate_text(self.session_conversations[sessionId], self.chosen_model, self.all_functions, stream=False) # AWAIT valid here

             assistant_text = gen_result["assistant_text"]
             final_text = assistant_text
             tool_calls = gen_result.get("tool_calls", [])

             assistant_message = {"role": "assistant", "content": assistant_text}
             if tool_calls:
                 for tc in tool_calls:
                     tc["type"] = "function"
                 assistant_message["tool_calls"] = tool_calls
             self.session_conversations[sessionId].append(assistant_message)
             logger.info(f"Added assistant message: {json.dumps(assistant_message, indent=2)}")

             if not tool_calls:
                 break

             for tc in tool_calls:
                 result = await process_tool_call(tc, self.servers, self.quiet_mode) # AWAIT valid here
                 if result:
                     self.session_conversations[sessionId].append(result)
                     logger.info(f"Added tool result: {json.dumps(result, indent=2)}")
                     # 可选：将工具结果写入记忆
                     try:
                         if self.memory_system:
                             agent_id = os.environ.get("AGENT_ID", "A2AAgent")
                             user_id = os.environ.get("USER_ID", sessionId)
                             # 简化写入：以文本形式存储工具结果摘要
                             tool_text = json.dumps(result, ensure_ascii=False)
                             self.memory_system.store_memory(
                                 agent_id=agent_id,
                                 user_id=user_id,
                                 content={"text": tool_text, "metadata": {"sessionId": sessionId, "source": "tool_result"}},
                                 memory_type="working",
                                 importance=0.5,
                             )
                     except Exception as e:
                         logger.warning(f"写入工具结果记忆失败：{e}")

         # 将最终回答写入记忆（若启用记忆系统）
         try:
             if self.memory_system and final_text:
                 agent_id = os.environ.get("AGENT_ID", "A2AAgent")
                 user_id = os.environ.get("USER_ID", sessionId)
                 self.memory_system.store_memory(
                     agent_id=agent_id,
                     user_id=user_id,
                     content={"text": final_text, "metadata": {"sessionId": sessionId}},
                     memory_type="working",
                     importance=0.6,
                 )
         except Exception as e:
             logger.warning(f"写入回答记忆失败：{e}")

         return final_text


    async def cleanup(self):
        """Clean up servers and log messages."""
        print("Cleaning up servers...")
        for cli in self.servers.values():
            try:
                await asyncio.shield(cli.stop())
            except BaseException as e:
                logger.debug(f"Ignore error during client stop: {e!r}")
        if sys.platform.startswith("win"):
            try:
                await asyncio.shield(asyncio.sleep(0.05))
            except BaseException:
                pass
        print("Cleanup complete.")

    def get_agent_response(self, response: str) -> dict[str, Any]:
        """Format agent response in a consistent structure."""
        try:
            # All final responses should be treated as complete
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response
            }
        except Exception as e:
            # Log but continue with best-effort fallback
            logger.error(f"Error parsing response: {e}, response: {response}")

            # Default to treating it as a completed response
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response
            }

    async def stream(self, query: str, sessionId: str) -> AsyncIterable[dict[str, Any]]:
        """Stream updates from the MCP agent.
        """
        print(f"问题: {query}的sessionId为： {sessionId}")
        try:
            # Initial response to acknowledge the query
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "updates": "Processing request..."
            }

            logger.info(f"Processing query: {query[:50]}...")

            try:

                response_generator = await self.run_inference(
                    user_query=query,
                    sessionId=sessionId,
                    stream=True,
                )
                # Iterate through the chunks yielded by the response_generator
                async for chunk in response_generator:
                    # Yield each chunk as it arrives.
                    yield {
                        "is_task_complete": False,  # Indicate it's an intermediate part
                        "require_user_input": False,
                        "content": chunk["text"],  # Yield the actual content chunk
                        "type":chunk["type"],
                    }
                yield {
                    "is_task_complete": True,  # Indicate it's an intermediate part
                    "require_user_input": False,
                    "content": " ",
                    "type": "normal" # 参照 AgentTaskManager._stream_generator 条件判断逻辑修改，让 lastchunk 能够为true
                }
            except Exception as e:
                logger.error(f"Error during processing: {traceback.format_exc()}")
                yield {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "updates": f"Error processing request: {str(e)}"
                }
        except Exception as e:
            logger.error(f"Error in streaming agent: {traceback.format_exc()}")
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "updates": f"Error processing request: {str(e)}"
            }

    def invoke(self, query: str, sessionId: str) -> dict[str, Any]:
        """Synchronous invocation of the MCP agent."""
        raise NotImplementedError(
            "Synchronous invocation is not supported by this agent. Use the streaming endpoint (tasks/sendSubscribe) instead."
        )
