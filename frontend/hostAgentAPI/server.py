import asyncio
import base64
import threading
import os
import logging
logger = logging.getLogger(__name__)
import uuid
import json
import mimetypes
from typing import Any, Optional, Dict, List
import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request, Response, UploadFile, File
from fastapi.responses import FileResponse
from auth_middleware import get_current_user_optional, get_current_user_required
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'A2AServer', 'src'))
from A2AServer.common.A2Atypes import Message, Task, FilePart, FileContent
from application_manager import ApplicationManager
from adk_host_manager import ADKHostManager, get_message_id
from ServiceTypes import (
    Conversation,
    Event,
    CreateConversationResponse,
    ListConversationResponse,
    SendMessageResponse,
    MessageInfo,
    ListMessageResponse,
    PendingMessageResponse,
    ListTaskResponse,
    RegisterAgentResponse,
    ListAgentResponse,
    GetEventResponse,
    QueryEventResponse,
    QueryEventRequest
)

_upload_limiter: anyio.CapacityLimiter | None = None

def _get_upload_limiter() -> anyio.CapacityLimiter:
  global _upload_limiter
  if _upload_limiter is None:
    try:
      n = int(os.getenv("HOSTAPI_UPLOAD_MAX_CONCURRENCY", "8"))
    except Exception:
      n = 8
    _upload_limiter = anyio.CapacityLimiter(max(n, 1))
  return _upload_limiter

class ConversationServer:
  """ConversationServer is the backend to serve the agent interactions in the UI

  This defines the interface that is used by the Mesop system to interact with
  agents and provide details about the executions.
  """
  def __init__(self, router: APIRouter):
    agent_manager = os.environ.get("A2A_HOST", "ADK")
    self.manager: ApplicationManager
    
    # Get API key from environment
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    uses_vertex_ai = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
    
    self.manager = ADKHostManager(api_key=api_key, uses_vertex_ai=uses_vertex_ai)
    self._file_cache = {} # dict[str, FilePart] maps file id to message data
    self._message_to_cache = {} # dict[str, str] maps message id to cache id

    # 上传文件目录
    self._upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(self._upload_dir, exist_ok=True)

    # Load and register agents from agents.json (run in background to avoid blocking API startup)
    threading.Thread(target=self._load_and_register_agents, daemon=True).start()

    router.add_api_route(
        "/conversation/create",
        self._create_conversation,
        methods=["POST"])
    router.add_api_route(
        "/conversation/list",
        self._list_conversation,
        methods=["POST"])
    router.add_api_route(
        "/message/send",
        self._send_message,
        methods=["POST"])
    router.add_api_route(
        "/events/get",
        self._get_events,
        methods=["POST"])
    router.add_api_route(
        "/events/query",
        self._query_events,
        methods=["POST"])
    router.add_api_route(
        "/message/list",
        self._list_messages,
        methods=["POST"])
    router.add_api_route(
        "/message/pending",
        self._pending_messages,
        methods=["POST"])
    router.add_api_route(
        "/task/list",
        self._list_tasks,
        methods=["POST"])
    router.add_api_route(
        "/agent/register",
        self._register_agent,
        methods=["POST"])
    router.add_api_route(
        "/agent/list",
        self._list_agents,
        methods=["POST"])
    router.add_api_route(
        "/message/file/{file_id}",
        self._files,
        methods=["GET"])
    router.add_api_route(
        "/api_key/update",
        self._update_api_key,
        methods=["POST"])

    # 文件上传与访问
    router.add_api_route(
        "/upload",
        self._upload_file,
        methods=["POST"])
    router.add_api_route(
        "/upload/multiple",
        self._upload_multiple_files,
        methods=["POST"])
    router.add_api_route(
        "/files",
        self._list_uploaded_files,
        methods=["GET"])
    router.add_api_route(
        "/files/{file_id}",
        self._get_uploaded_file,
        methods=["GET"])
    router.add_api_route(
        "/files/{file_id}",
        self._delete_uploaded_file,
        methods=["DELETE"])

  # Background agent registration (class method, not nested in __init__)
  def _load_and_register_agents(self):
    try:
      with open('agents.json', 'r', encoding='utf-8') as f:
        agents = json.load(f)
      for agent in agents:
        url = agent.get('url')
        if not url:
          continue
        # 重试注册，解决容器刚启动端口未就绪导致的连接拒绝
        max_attempts = 12
        delay_seconds = 5
        for attempt in range(1, max_attempts + 1):
          try:
            logging.info(f"尝试注册代理 {url} (第{attempt}/{max_attempts}次)")
            self.manager.register_agent(url)
            logging.info(f"代理注册成功: {url}")
            break
          except Exception as e:
            if attempt == max_attempts:
              logging.warning(f"代理注册失败（已达最大重试次数）: {url}: {e}")
            else:
              logging.warning(f"注册失败，{delay_seconds}s后重试: {url}: {e}")
              try:
                import time
                time.sleep(delay_seconds)
              except Exception:
                pass
    except FileNotFoundError:
      logging.warning("agents.json not found, no agents registered.")
    except json.JSONDecodeError:
      logging.error("Error decoding agents.json.")
    except Exception as e:
      logging.error(f"Unexpected error while loading agents: {e}")

  # Update API key in manager
  def update_api_key(self, api_key: str):
    if isinstance(self.manager, ADKHostManager):
      self.manager.update_api_key(api_key)

  async def _create_conversation(self, request: Request, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    uid = current_user['user_id'] if current_user else None
    logging.info(f"Creating conversation. Current user: {uid}")
    c = self.manager.create_conversation(user_id=uid)
    logging.info(f"Created conversation: {c.conversation_id} for user: {uid}")
    # 如果用户已登录，将用户ID添加到会话元数据中
    if current_user:
      c.metadata = c.metadata or {}
      c.metadata['user_id'] = current_user['user_id']
      try:
        os.environ['A2A_CURRENT_USER_ID'] = str(current_user['user_id'])
        os.environ['USER_ID'] = str(current_user['user_id'])
        if 'DEFAULT_USER_ID' in os.environ:
          os.environ.pop('DEFAULT_USER_ID', None)
      except Exception:
        pass
    else:
      # 无登录状态下的兜底：从环境变量注入用户ID，避免智能体向前端索取用户ID
      try:
        env_uid = os.environ.get('A2A_CURRENT_USER_ID') or os.environ.get('USER_ID') or os.environ.get('FRONTEND_USER_ID')
        if env_uid:
          c.metadata = c.metadata or {}
          c.metadata['user_id'] = str(env_uid)
          os.environ['A2A_CURRENT_USER_ID'] = str(env_uid)
          os.environ['USER_ID'] = str(env_uid)
      except Exception:
        pass
    return CreateConversationResponse(result=c)

  async def _send_message(self, request: Request, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    message_data = await request.json()
    logging.info(f"Received /message/send params: {message_data}")
    message = Message(**message_data['params'])
    try:
      auth = request.headers.get('authorization') or request.headers.get('Authorization')
      if isinstance(auth, str) and auth.strip():
        os.environ['HOSTAPI_AUTH_TOKEN'] = auth.strip()
    except Exception:
      pass
    try:
      from urllib.parse import unquote
      tgt = request.headers.get('X-Target-Agent') or request.headers.get('x-target-agent') or ''
      if isinstance(tgt, str) and tgt.strip():
        name = unquote(tgt.strip())
        alias = {
          '就诊摘要生成器': '就诊摘要生成',
          '就诊摘要': '就诊摘要生成',
          '就诊摘要助手': '就诊摘要生成',
          '健康档案': '健康档案管理员',
          '健康档案管理': '健康档案管理员',
          '档案管理员': '健康档案管理员'
        }
        if name in alias:
          name = alias[name]
        message.metadata = message.metadata or {}
        message.metadata['selected_agent'] = name
    except Exception:
      pass
    
    # 如果用户已登录，验证会话权限
    if current_user:
      conversation_id = message.metadata.get('conversation_id')
      if conversation_id:
        conversation = self.manager.get_conversation(conversation_id)
        if conversation and conversation.metadata:
          conv_user_id = conversation.metadata.get('user_id')
          if conv_user_id and conv_user_id != current_user['user_id']:
            raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="无权访问此会话"
            )
      # 自动将当前登录用户ID注入到消息元数据
      try:
        message.metadata = message.metadata or {}
        if 'user_id' not in message.metadata:
          message.metadata['user_id'] = current_user['user_id']
        try:
          os.environ['A2A_CURRENT_USER_ID'] = str(current_user['user_id'])
          os.environ['USER_ID'] = str(current_user['user_id'])
          if 'DEFAULT_USER_ID' in os.environ:
            os.environ.pop('DEFAULT_USER_ID', None)
        except Exception:
          pass
      except Exception:
        pass
        message.metadata = message.metadata or {}
        if 'user_id' not in message.metadata:
          message.metadata['user_id'] = current_user['user_id']
        try:
          os.environ['A2A_CURRENT_USER_ID'] = str(current_user['user_id'])
          os.environ['USER_ID'] = str(current_user['user_id'])
          if 'DEFAULT_USER_ID' in os.environ:
            os.environ.pop('DEFAULT_USER_ID', None)
        except Exception:
          pass
    else:
      try:
        env_uid = os.environ.get('A2A_CURRENT_USER_ID') or os.environ.get('USER_ID') or os.environ.get('FRONTEND_USER_ID')
        if env_uid:
          message.metadata = message.metadata or {}
          if 'user_id' not in message.metadata:
            message.metadata['user_id'] = str(env_uid)
          os.environ['A2A_CURRENT_USER_ID'] = str(env_uid)
          os.environ['USER_ID'] = str(env_uid)
        elif message.metadata and message.metadata.get('conversation_id'):
          conversation = self.manager.get_conversation(message.metadata.get('conversation_id'))
          if conversation and conversation.metadata and conversation.metadata.get('user_id'):
            message.metadata['user_id'] = conversation.metadata.get('user_id')
      except Exception:
        pass
    
    message = self.manager.sanitize_message(message)

    # === PHA v2 主路径（阶段27：默认开启，失败回 v1）===
    # 决策逻辑：
    # - is_v2_request() 默认 True（PHA_USE_V2 默认 true）
    # - header X-PHA-V2-Disable=true 可显式关 v2（强制 v1）
    # - v2 失败/异常 → 自动 fallback v1 ADK
    #
    # 优势（vs 阶段4 灰度路由）：
    # - 100% 流量走 v2（42 MCP 工具 + StateGraph 可观测）
    # - 失败兜底 v1（永远不挂）
    # - 部署可缩到 1 容器（v2 in-process）
    v2_attempted = False
    v2_disabled_by_header = False
    try:
        # 显式关闭：X-PHA-V2-Disable=true
        if request is not None:
            try:
                if request.headers.get("x-pha-v2-disable", "").lower() == "true":
                    v2_disabled_by_header = True
                    logging.info("[PHA v2] disabled by X-PHA-V2-Disable header")
            except Exception:
                pass

        from A2AServer.v2.bridge import is_v2_request, v2_process_message
        # 阶段27：默认尝试 v2，除非显式关闭
        if not v2_disabled_by_header and is_v2_request(request):
            v2_attempted = True
            logging.info("[PHA v2] routing to v2 HostGraph (default since stage27)")
            # 异步包装：bridge 是 async，process_message 是同步接口
            async def _v2_runner():
                try:
                    r = await v2_process_message(message)
                    if r.get("error"):
                        logging.warning(f"[PHA v2] error, fallback to v1: {r['error']}")
                        await self.manager.process_message(message)
                    elif r.get("message") is not None:
                        # 注入 v2 结果到 manager 的会话
                        try:
                            self.manager._messages.append(r["message"])
                            conv_id = message.metadata.get("conversation_id") if message.metadata else None
                            if conv_id:
                                conv = self.manager.get_conversation(conv_id)
                                if conv:
                                    conv.messages.append(r["message"])
                        except Exception as inner_e:
                            logging.warning(f"[PHA v2] inject result failed: {inner_e}")
                        logging.info(f"[PHA v2] success: agent={r.get('result', {}).get('agent')}")
                except Exception as e:
                    logging.exception(f"[PHA v2] runner exception, fallback to v1: {e}")
                    await self.manager.process_message(message)

            task = asyncio.create_task(_v2_runner())
    except ImportError as e:
        logging.debug(f"[PHA v2] import not available: {e}")
    except Exception as e:
        logging.warning(f"[PHA v2] setup failed, fallback to v1: {e}")

    if not v2_attempted:
        task = asyncio.create_task(self.manager.process_message(message))
    def _done_cb(t):
      try:
        exc = t.exception()
      except Exception:
        exc = None
      if exc:
        import uuid
        logger.error(f"process_message error: {exc}")
        try:
          conv_id = message.metadata.get('conversation_id') if message.metadata else None
          conv = self.manager.get_conversation(conv_id)
          if conv:
            from A2AServer.common.A2Atypes import Message as AMsg, TextPart as AText
            err_msg = AMsg(
              role='agent',
              parts=[AText(text=f"服务暂时不可用：{str(exc)}")],
              metadata={
                'conversation_id': conv_id,
                'last_message_id': message.metadata.get('message_id') if message.metadata else None,
                'message_id': str(uuid.uuid4()),
              },
            )
            conv.messages.append(err_msg)
        except Exception:
          pass
        try:
          mid = message.metadata.get('message_id') if message.metadata else None
          if mid in self.manager._pending_message_ids:
            self.manager._pending_message_ids.remove(mid)
        except Exception:
          pass
    task.add_done_callback(_done_cb)
    return SendMessageResponse(result=MessageInfo(
        message_id=message.metadata['message_id'],
        conversation_id=message.metadata['conversation_id'] if 'conversation_id' in message.metadata else '',
    ))

  async def _list_messages(self, request: Request, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    message_data = await request.json()
    logging.info(f"Request to /message/list with body: {message_data}")
    params = message_data['params']
    conversation_id = params.get('conversation_id') if isinstance(params, dict) else params
    
    conversation = self.manager.get_conversation(conversation_id)
    if conversation:
      logging.info(f"Found conversation {conversation_id} with {len(conversation.messages)} messages")
      # 如果用户已登录，验证会话权限
      if current_user and conversation.metadata:
        conv_user_id = conversation.metadata.get('user_id')
        if conv_user_id and conv_user_id != current_user['user_id']:
          raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此会话"
          )
      
      return ListMessageResponse(result=self.cache_content(
          conversation.messages))
    return ListMessageResponse(result=[])

  def cache_content(self, messages: list[Message]):
    rval = []
    for m in messages:
      message_id = get_message_id(m)
      if not message_id:
        rval.append(m)
        continue
      new_parts = []
      for i, part in enumerate(m.parts):
        if part.type != 'file':
          new_parts.append(part)
          continue
        message_part_id = f"{message_id}:{i}"
        if message_part_id in self._message_to_cache:
          cache_id = self._message_to_cache[message_part_id]
        else:
          cache_id = str(uuid.uuid4())
          self._message_to_cache[message_part_id] = cache_id
        # Replace the part data with a url reference
        new_parts.append(FilePart(
            file=FileContent(
                mimeType=part.file.mimeType,
                uri=f"/message/file/{cache_id}",
            )
        ))
        if cache_id not in self._file_cache:
          self._file_cache[cache_id] = part
      m.parts = new_parts
      rval.append(m)
    return rval

  async def _pending_messages(self):
    return PendingMessageResponse(result=self.manager.get_pending_messages())

  async def _list_conversation(self, request: Request, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    conversations = self.manager.conversations
    # 如果用户已登录，只返回该用户的会话
    if current_user:
      user_conversations = [
        conv for conv in conversations 
        if conv.metadata and conv.metadata.get('user_id') == current_user['user_id']
      ]
      return ListConversationResponse(result=user_conversations)
    return ListConversationResponse(result=conversations)

  def _get_events(self):
    return GetEventResponse(result=self.manager.events)

  async def _query_events(self, request: Request, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    data = await request.json()
    params = data.get("params")
    conversation_id = None
    if isinstance(params, dict):
      conversation_id = params.get("conversation_id")
    else:
      conversation_id = params
    
    # 如果用户已登录，验证会话权限
    if current_user and conversation_id:
      conversation = self.manager.get_conversation(conversation_id)
      if conversation and conversation.metadata:
        conv_user_id = conversation.metadata.get('user_id')
        if conv_user_id and conv_user_id != current_user['user_id']:
          raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此会话"
          )
    
    # 过滤出属于该 conversation_id 的事件
    events = [
        event for event in self.manager.events
        if getattr(event.content, "metadata", {}).get("conversation_id") == conversation_id
    ]
    return QueryEventResponse(result=events)

  def _list_tasks(self):
    return ListTaskResponse(result=self.manager.tasks)

  async def _register_agent(self, request: Request):
    message_data = await request.json()
    url = message_data['params']
    try:
      self.manager.register_agent(url)
    except Exception as e:
      logging.warning(f"代理注册失败: {url}: {e}")
    return RegisterAgentResponse()

  async def _list_agents(self):
    return ListAgentResponse(result=self.manager.agents)

  def _files(self, file_id):
    if file_id not in self._file_cache:
      raise Exception("file not found")
    part = self._file_cache[file_id]
    if "image" in part.file.mimeType:
      return Response(
          content=base64.b64decode(part.file.bytes),
          media_type=part.file.mimeType)
    return Response(content=part.file.bytes, media_type=part.file.mimeType)
  
  async def _update_api_key(self, request: Request):
    """Update the API key"""
    try:
        data = await request.json()
        api_key = data.get("api_key", "")
        
        if api_key:
            # Update in the manager
            self.update_api_key(api_key)
            return {"status": "success"}
        return {"status": "error", "message": "No API key provided"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

  # ====== 文件上传/下载功能 ======
  async def _upload_file(self, file: UploadFile = File(...), current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    limiter = _get_upload_limiter()
    await limiter.acquire()
    try:
      file_ext = os.path.splitext(file.filename)[1]
      file_id = f"{uuid.uuid4().hex}{file_ext}"
      save_path = os.path.join(self._upload_dir, file_id)
      max_size = int(os.getenv("HOSTAPI_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
      chunk_size = int(os.getenv("HOSTAPI_UPLOAD_CHUNK_BYTES", str(1024 * 1024)))
      total = 0
      with open(save_path, "wb") as out:
        while True:
          chunk = await file.read(chunk_size)
          if not chunk:
            break
          total += len(chunk)
          if total > max_size:
            try:
              out.close()
            except Exception:
              pass
            try:
              os.remove(save_path)
            except Exception:
              pass
            raise HTTPException(status_code=400, detail="文件大小超过限制")
          await anyio.to_thread.run_sync(out.write, chunk)
      url_path = f"/files/{file_id}"
      return {
        "fileId": file_id,
        "filename": file.filename,
        "mimeType": file.content_type,
        "size": total,
        "url": url_path
      }
    except Exception as e:
      logging.exception("上传文件失败")
      raise HTTPException(status_code=500, detail=str(e))
    finally:
      try:
        limiter.release()
      except Exception:
        pass

  async def _upload_multiple_files(self, files: List[UploadFile] = File(...), current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    results = []
    for f in files:
      # 复用单文件上传逻辑
      res = await self._upload_file(file=f, current_user=current_user)
      results.append(res)
    return {"files": results}

  async def _get_uploaded_file(self, file_id: str):
    path = os.path.join(self._upload_dir, file_id)
    if not os.path.isfile(path):
      raise HTTPException(status_code=404, detail="file not found")
    mime, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=mime or 'application/octet-stream')

  async def _delete_uploaded_file(self, file_id: str, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    path = os.path.join(self._upload_dir, file_id)
    if not os.path.isfile(path):
      raise HTTPException(status_code=404, detail="file not found")
    os.remove(path)
    return {"success": True}

  async def _list_uploaded_files(self):
    files = []
    try:
      for name in os.listdir(self._upload_dir):
        p = os.path.join(self._upload_dir, name)
        if os.path.isfile(p):
          mime, _ = mimetypes.guess_type(p)
          stat = os.stat(p)
          files.append({
            "fileId": name,
            "filename": name,
            "mimeType": mime or 'application/octet-stream',
            "size": stat.st_size,
            "url": f"/files/{name}",
            "createdAt": stat.st_ctime
          })
      # 按创建时间倒序
      files.sort(key=lambda x: x["createdAt"], reverse=True)
      return files
    except FileNotFoundError:
      return []
