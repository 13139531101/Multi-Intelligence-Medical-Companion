import collections
import copy
import logging
import os
import traceback
import json
import base64
import asyncio
import sys
import re
import hashlib
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
        self.session_rollups = collections.defaultdict(str)
        self._memory_hash_by_session = {}
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
        if os.getenv("SKIP_MCP_TOOLS", "0") == "1":
            self.servers = {}
            self.all_functions = []
            self.tool_ready = True
            return True

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
                 if _cwd and os.path.isabs(_cwd) and not os.path.isdir(_cwd):
                     logger.warning(f"[MCP] cwd 目录不存在：{_cwd}，将使用配置目录作为工作目录。")
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

    def _clip_text(self, value: Any, limit: int = 500) -> str:
        text = "" if value is None else str(value)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)] + "..."

    def _sanitize_memory_text(self, text: str) -> str:
        if not text:
            return ""
        s = str(text)
        s = re.sub(r"(?i)\b(bearer|token|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+", r"\1:[REDACTED]", s)
        s = re.sub(r"\b1[3-9]\d{9}\b", "[PHONE]", s)
        s = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", s)
        s = re.sub(r"\b\d{17}[\dXx]\b", "[IDCARD]", s)
        return s.strip()

    def _should_store_memory_text(self, session_id: str, text: str) -> bool:
        normalized = self._sanitize_memory_text(text)
        if not normalized:
            return False
        if len(normalized) < 8:
            return False
        if normalized in ("{}", "[]", "null", "None"):
            return False
        digest = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()
        if self._memory_hash_by_session.get(session_id) == digest:
            return False
        self._memory_hash_by_session[session_id] = digest
        return True

    def _store_memory_async(self, session_id: str, user_id: str, text: str, source: str, importance: float = 0.6):
        if not self.memory_system:
            return
        sanitized = self._sanitize_memory_text(text)
        if not self._should_store_memory_text(session_id, sanitized):
            return
        agent_id = os.environ.get("AGENT_ID", "A2AAgent")
        payload = {
            "text": self._clip_text(sanitized, int(os.getenv("MEMORY_WRITE_MAX_CHARS", "1800"))),
            "metadata": {"sessionId": session_id, "source": source},
        }

        async def _store():
            try:
                await asyncio.to_thread(
                    self.memory_system.store_memory,
                    agent_id=agent_id,
                    user_id=user_id,
                    content=payload,
                    memory_type="working",
                    importance=importance,
                )
            except Exception as e:
                logger.warning(f"写入记忆失败：{e}")

        try:
            asyncio.create_task(asyncio.wait_for(_store(), timeout=2.0))
        except Exception:
            pass

    def _memory_item_text(self, item: dict) -> str:
        if not isinstance(item, dict):
            return ""
        content = item.get("content") or {}
        text = ""
        if isinstance(content, dict):
            text = content.get("text") or ""
        if not text:
            text = item.get("text") or ""
        return self._clip_text(self._sanitize_memory_text(text), 220)

    def _format_memory_block(self, memories: list[dict]) -> str:
        lines = []
        for idx, m in enumerate(memories or [], start=1):
            text = self._memory_item_text(m)
            if not text:
                continue
            mid = m.get("id") or m.get("memory_id") or f"mem_{idx}"
            lines.append(f"[E{idx}|{mid}] {text}")
        if not lines:
            return ""
        return "可参考历史证据：\n" + "\n".join(lines[:8]) + "\n回答时优先引用 E 编号。"

    def _rollup_text_from_messages(self, messages: list[dict]) -> str:
        if not messages:
            return ""
        max_items = int(os.getenv("A2A_ROLLUP_MAX_ITEMS", "20"))
        lines = []
        for m in messages[-max_items:]:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "")
            if role not in ("user", "assistant", "tool"):
                continue
            content = m.get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, dict):
                text = json.dumps(content, ensure_ascii=False)
            if role == "assistant" and m.get("tool_calls"):
                names = []
                for tc in m.get("tool_calls") or []:
                    fn_name = ((tc or {}).get("function") or {}).get("name")
                    if fn_name:
                        names.append(fn_name)
                if names:
                    text = (text + " " + f"tools:{','.join(names[:4])}").strip()
            text = self._clip_text(self._sanitize_memory_text(text), 180)
            if not text:
                continue
            prefix = "用户" if role == "user" else ("助手" if role == "assistant" else "工具")
            lines.append(f"{prefix}:{text}")
        merged = "；".join(lines)
        return self._clip_text(merged, int(os.getenv("A2A_ROLLUP_MAX_CHARS", "1200")))

    def _compact_session_context(self, session_id: str):
        conv = self.session_conversations[session_id]
        if len(conv) <= 2:
            return
        non_system = conv[1:]
        dialog_indexes = [
            i for i, m in enumerate(non_system)
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        keep_rounds = max(1, int(os.getenv("A2A_KEEP_RECENT_ROUNDS", "2")))
        keep_dialog_count = keep_rounds * 2
        if len(dialog_indexes) <= keep_dialog_count:
            return
        cut_index = dialog_indexes[-keep_dialog_count]
        old_messages = non_system[:cut_index]
        recent_messages = non_system[cut_index:]
        new_rollup = self._rollup_text_from_messages(old_messages)
        if new_rollup:
            old_rollup = self.session_rollups.get(session_id, "")
            merged = (old_rollup + "；" + new_rollup).strip("；")
            self.session_rollups[session_id] = self._clip_text(
                merged, int(os.getenv("A2A_ROLLUP_STORE_MAX_CHARS", "1800"))
            )
        self.session_conversations[session_id] = [conv[0]] + recent_messages

    async def run_inference(self, user_query, sessionId, stream=True, user_id=None, user_parts=None):
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

        try:
            sid = str(sessionId) if sessionId is not None else ""
            if sid:
                os.environ["A2A_CURRENT_SESSION_ID"] = sid
                os.environ["A2A_CURRENT_CONVERSATION_ID"] = sid
        except Exception:
            pass


        # Build initial conversation (system message + user query)
        self._build_initial_conversation(sessionId, user_query, user_id=user_id, user_parts=user_parts) # This helper can be synchronous


        # try:
        if stream:
            return self._stream_response_generator(sessionId) # Returns an async generator
        else:
            return await self._non_stream_response(sessionId) # Returns the final text
        # finally:
        #     # Ensure cleanup is called when run() finishes or an exception occurs
        #     await self.cleanup() # <-- AWAIT is valid here

    def _build_initial_conversation(self, sessionId, user_query, user_id=None, user_parts=None):
         # Helper method to build the initial conversation list (synchronous)
         self.conversation = []
         # 默认的prompt
         agent_prompt = "You are a helpful assistant."
         try:
             with open(self.chosen_model["prompt_file"], "r", encoding="utf-8") as f:
                 agent_prompt = f.read()
         except Exception as e:
             logger.warning(f"Failed to read Agent prompt file: {e}")

         # 确定用户ID (优先使用传入的user_id，其次环境变量，最后是sessionId)
         final_user_id = str(user_id) if user_id else (os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID") or str(sessionId))

         # 加上当前的时间和用户ID信息到System Prompt
         header_info = f"当前用户ID: {final_user_id}。\n当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}。"
         system_content = header_info + "\n" + agent_prompt

         rollup = self.session_rollups.get(sessionId, "")
         if rollup:
             system_content = system_content + "\n对话历史滚动总结：" + self._clip_text(rollup, 1800)

         attachment_text = ""
         attachment_briefs = []
         for p in user_parts or []:
             if not isinstance(p, dict):
                 continue
             if p.get("type") == "file":
                 f = p.get("file") or {}
                 name = self._clip_text(f.get("name") or "附件", 60)
                 mime = self._clip_text(f.get("mimeType") or "application/octet-stream", 80)
                 uri = self._clip_text(f.get("uri") or "", 120)
                 has_bytes = bool(f.get("bytes"))
                 attachment_briefs.append(f"name={name},mime={mime},uri={uri},has_bytes={has_bytes}")
         if attachment_briefs:
             attachment_text = "用户本轮附带文件：" + " | ".join(attachment_briefs[:3])

         # 注入记忆上下文（若启用记忆系统）
         try:
             if self.memory_system:
                 agent_id = os.environ.get("AGENT_ID", "A2AAgent")
                 # 使用确定的用户ID进行记忆检索
                 memory_query = user_query if not attachment_text else f"{user_query}\n{attachment_text}"
                 memories = self.memory_system.search_memories(
                     query=memory_query,
                     agent_id=agent_id,
                     user_id=final_user_id,
                     memory_types=["long_term", "working"],
                     limit=max(5, int(os.getenv("A2A_MEMORY_RETRIEVAL_LIMIT", "8"))),
                     min_similarity=0.5,
                 )
                 if memories:
                     memory_block = self._format_memory_block(memories)
                     if memory_block:
                         system_content = system_content + "\n" + memory_block
         except Exception as e:
             logger.warning(f"注入记忆上下文失败：{e}")

         try:
             conv = self.session_conversations[sessionId]
             while conv and conv[-1].get("role") == "assistant" and conv[-1].get("tool_calls"):
                 conv.pop()
         except Exception:
             pass

         if not self.session_conversations[sessionId]:
             self.session_conversations[sessionId].append({"role": "system", "content": system_content})
         else:
             if self.session_conversations[sessionId][0].get("role") == "system":
                 self.session_conversations[sessionId][0]["content"] = system_content
             else:
                 self.session_conversations[sessionId].insert(0, {"role": "system", "content": system_content})
         self.session_conversations[sessionId].append({"role": "user", "content": user_query})
         self._compact_session_context(sessionId)
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
                    # 修复：先计算新增部分，再累加
                    current_text = chunk.get("assistant_text", "")
                    remaining = current_text[len(accumulated_text):] if accumulated_text else current_text
                    if remaining:
                        yield {"text": remaining, "type": "reasoning"} # YIELD here as well 剩余文本
                    accumulated_text += remaining  # 只累加新增部分

                    tool_calls = chunk.get("tool_calls", [])
                    if tool_calls:
                        for tc in tool_calls:
                            tc["type"] = "function"
                        assistant_message = {
                            "role": "assistant",
                            "content": chunk["assistant_text"],
                            "tool_calls": tool_calls
                        }
                        yield {"text": f"{json.dumps(tool_calls, ensure_ascii=False)}", "type": "tool_call"}

                        tool_results_to_append = []
                        for tc in tool_calls:
                            if tc.get("function", {}).get("name"):
                                result = await process_tool_call(tc, self.servers, self.quiet_mode)
                                if result:
                                    new_res = copy.deepcopy(result)
                                    if "data" in result:
                                        result.pop("data")
                                    tool_results_to_append.append(result)
                                    tool_calls_processed = True
                                    yield {"text": f"{json.dumps(new_res)}", "type": "tool_result"}
                        if not tool_results_to_append:
                            for tc in tool_calls:
                                tool_call_id = tc.get("id")
                                if tool_call_id:
                                    tool_results_to_append.append(
                                        {
                                            "role": "tool",
                                            "tool_call_id": tool_call_id,
                                            "content": json.dumps({"error": "Tool call was not executed"}, ensure_ascii=False),
                                        }
                                    )
                            tool_calls_processed = True
                        if tool_calls_processed:
                            self.session_conversations[sessionId].append(assistant_message)
                            self.session_conversations[sessionId].extend(tool_results_to_append)
                    else:
                        assistant_message = {
                            "role": "assistant",
                            "content": chunk.get("assistant_text") or "",
                        }
                        self.session_conversations[sessionId].append(assistant_message)
                        if self.memory_system:
                            user_id = os.environ.get("USER_ID", sessionId)
                            self._store_memory_async(
                                str(sessionId),
                                str(user_id),
                                chunk.get("assistant_text") or "",
                                source="assistant_stream_final",
                                importance=0.6,
                            )
            if not tool_calls_processed:
                break


    async def _non_stream_response(self, sessionId):
        """Handles the non-streaming response logic."""
        final_text = ""
        while True:
            gen_result = await generate_text(self.session_conversations[sessionId], self.chosen_model, self.all_functions, stream=False)

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
                result = await process_tool_call(tc, self.servers, self.quiet_mode)
                if result:
                    self.session_conversations[sessionId].append(result)
                    logger.info(f"Added tool result: {json.dumps(result, indent=2)}")
                    if self.memory_system:
                        user_id = os.environ.get("USER_ID", sessionId)
                        self._store_memory_async(
                            str(sessionId),
                            str(user_id),
                            json.dumps(result, ensure_ascii=False),
                            source="tool_result",
                            importance=0.45,
                        )

        # 将最终回答写入记忆（若启用记忆系统）
        if self.memory_system and final_text:
            user_id = os.environ.get("USER_ID", sessionId)
            self._store_memory_async(
                str(sessionId),
                str(user_id),
                final_text,
                source="assistant_final",
                importance=0.6,
            )

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

    async def stream(self, query: str, sessionId: str, user_id: str = None, user_parts=None) -> AsyncIterable[dict[str, Any]]:
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
                    user_id=user_id,
                    user_parts=user_parts,
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
