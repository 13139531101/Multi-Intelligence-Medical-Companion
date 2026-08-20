import asyncio
import click
import os
import sys
import logging

# 优先使用本仓库的 src 版本，避免误用 build/lib 或已安装旧版本
_current_dir = os.path.dirname(__file__)
_src_path = os.path.abspath(os.path.join(_current_dir, "..", "A2AServer", "src"))
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from A2AServer.common.server import A2AServer
from A2AServer.common.A2Atypes import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from A2AServer.task_manager import AgentTaskManager
from A2AServer.agent import BasicAgent
from dotenv import load_dotenv
from memory_service import MedicationReminderMemoryService

load_dotenv()

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 强制配置 root logger
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _safe_text(text: str) -> str:
    """Strip surrogate characters that orjson can't serialize, then truncate."""
    if not isinstance(text, str):
        text = str(text)
    text = text.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
    return text[:8000]


@click.command(help="启动用药提醒助手 A2A Server")
@click.option("--host", "host", default="localhost", help="服务器绑定的主机名（默认为 localhost）")
@click.option("--port", "port", default=10012,help="服务器监听的端口号（默认为 10012）")
@click.option("--prompt", "agent_prompt_file", default="memory_enhanced_agent_prompt.md",help="Agent 的 prompt 文件路径（默认为 memory_enhanced_agent_prompt.md）")
@click.option("--model", "model_name", default="deepseek-chat",help="使用的模型名称（如 deepseek-chat）")
@click.option("--provider", "provider", default="deepseek", help="模型提供方名称（如 deepseek、openai 等）")
@click.option("--mcp_config", "mcp_config_path", default="mcp_config.json",help="MCP 配置文件路径（默认为 mcp_config.json）")
@click.option("--agent_url", "agent_url", default="",help="Agent Card中对外展示和访问的地址")
def main(host, port, agent_prompt_file, model_name, provider, mcp_config_path, agent_url=""):
    """启动用药提醒助手 A2A Server
    host: 启动的Agent的主机
    port: 启动的端口
    agent_prompt_file: prompt文件
    """
    input_mode, output_mode = ["text", "text/plain"], ["text", "text/plain"]
    # Agent支持的输入和输出，默认只支持文本
    BasicAgent.SUPPORTED_CONTENT_TYPES = input_mode
    try:
        # 定义 Agent 能力和技能,  功能（支持流式响应）
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
                id="MedicationReminder",
                name="用药提醒助手",
                description="提供智能的用药提醒、复诊预约管理和服药依从性监控服务",
                tags=["medication", "reminder", "appointment", "health"],
                examples=[
                    "帮我设置阿莫西林的用药提醒，每日3次",
                    "查看我今天的用药安排",
                    "添加下周三的复诊预约提醒"
                ]
            )
        if not agent_url:
            agent_url = f"http://{host}:{port}/"
        # 包括 agent 的名字、描述、接口 URL、支持的输入输出格式、版本号等
        agent_card = AgentCard(
            name="用药提醒助手",
            description="提供智能的用药提醒、复诊预约管理和服药依从性监控服务",
            url=agent_url,
            version="1.0.0",
            defaultInputModes=input_mode,
            defaultOutputModes=output_mode,
            capabilities=capabilities,
            skills=[skill],
        )
        agent = BasicAgent(config_path=mcp_config_path, model_name=model_name, prompt_file=agent_prompt_file, provider=provider)

        # 预加载逻辑在服务器 startup 事件中执行，避免与主事件循环不一致
        
        # 初始化记忆服务（使用 asyncio.run，避免 MainThread 无事件循环错误）
        enable_memory_flag = os.getenv("ENABLE_AGENT_MEMORY", "true").lower()
        skip_memory_init = os.getenv("SKIP_MEMORY_INIT", "0") == "1"
        enable_memory = (enable_memory_flag in ("true", "1")) and not skip_memory_init

        if not enable_memory:
            logger.warning("记忆服务未启用（ENABLE_AGENT_MEMORY=false 或 SKIP_MEMORY_INIT=1）")
        else:
            try:
                memory_service = MedicationReminderMemoryService()
                memory_initialized = asyncio.run(memory_service.initialize())
                if memory_initialized:
                    logger.info("用药提醒记忆服务初始化成功")
                else:
                    logger.warning("用药提醒记忆服务初始化失败，智能体将在无记忆模式下运行")
            except Exception as e:
                logger.error(f"记忆服务初始化异常: {e}")
                logger.warning("智能体将在无记忆模式下运行")
        # 启动 A2A 服务器（MCP 预加载由服务器生命周期管理）
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=agent),
            host=host,
            port=port,
        )

        # 阶段48-A2A: 挂载纯 Starlette ANP 端点到 /anp
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import JSONResponse
            import uuid

            # ORjsonResponse: handles surrogate characters without errors
            class ORjsonResponse(JSONResponse):
                def render(self, content) -> bytes:
                    import orjson
                    return orjson.dumps(content)

            _task_mgr = server.task_manager

            anp_app = Starlette()

            async def agent_card(request: Request):
                return ORjsonResponse({
                    "name": "MedicationReminder",
                    "description": "用药提醒助手",
                    "version": "2.0-stage48-A2A",
                    "did": "did:wba:pha.local:medication_reminder",
                    "endpoints": [{"url": "http://medication_reminder:10012/anp", "type": "ANP"}],
                    "capabilities": {"streaming": True},
                })

            async def anp_rpc(request: Request):
                """
                ANP JSON-RPC 2.0 handler → V2Agent.stream()
                """
                try:
                    import orjson
                    raw_body = await request.body()
                    body_str = raw_body.decode("utf-8", "replace")
                    body = orjson.loads(body_str)
                    method = body.get("method", "")
                    params = body.get("params", {})
                    task = params.get("task", {})
                    user_id = params.get("user_id", "anonymous")
                    session_id = params.get("session_id", str(uuid.uuid4()))

                    # 阶段48-A2A Phase 1: Ed25519 签名验证
                    caller_did = request.headers.get("X-ANP-DID")
                    sig_b64 = request.headers.get("X-ANP-Signature")
                    ts_str = request.headers.get("X-ANP-Timestamp")
                    if caller_did and sig_b64 and ts_str:
                        try:
                            from A2AServer.v2.did_wba import get_keystore, verify_request
                            import base64
                            ks = get_keystore()
                            doc = ks.get_document(caller_did)
                            if doc and doc.public_key:
                                pub_bytes = base64.b64decode(doc.public_key)
                                ts = float(ts_str)
                                valid, err = verify_request(pub_bytes, sig_b64, "POST", "/agent/rpc", body_str, timestamp=ts)
                                if not valid:
                                    logger.warning("[ANP] signature verify failed for %s: %s", caller_did, err)
                                    return ORjsonResponse({
                                        "jsonrpc": "2.0",
                                        "id": body.get("id"),
                                        "error": {"code": -32603, "message": f"invalid signature: {err}"},
                                    })
                            else:
                                logger.warning("[ANP] unknown caller DID %s, skipping verify", caller_did)
                        except Exception as verify_err:
                            logger.warning("[ANP] verify error %s: %s", caller_did, verify_err)

                    if method == "task/send":
                        message = task.get("message", {})
                        parts = message.get("parts", [])
                        if isinstance(parts, list) and parts:
                            query = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
                        else:
                            query = message.get("text", "") or message.get("content", "") or str(message)

                        if not query:
                            return ORjsonResponse({
                                "jsonrpc": "2.0",
                                "id": body.get("id"),
                                "result": {"status": "ok", "parts": [], "is_task_complete": True},
                            })

                        logger.info("[ANP:medication_reminder] query=%s session=%s user=%s", query[:50], session_id, user_id)

                        from A2AServer.v2.sub_agents import MedicationReminderV2
                        _model = os.getenv("LLM_MODEL", "deepseek-chat")
                        agent_instance = MedicationReminderV2(model=_model)
                        result_parts = []
                        is_task_complete = False

                        async for chunk in agent_instance.stream(query, session_id, user_id):
                            chunk_type = chunk.get("type", "normal")
                            content = chunk.get("content", "")
                            if chunk_type == "complete":
                                is_task_complete = True
                                break
                            if chunk_type == "error":
                                logger.error("[ANP:medication_reminder] stream error: %s", content)
                                return ORjsonResponse({
                                    "jsonrpc": "2.0",
                                    "id": body.get("id"),
                                    "error": {"code": -32603, "message": str(content)[:500]},
                                })
                            if chunk_type in ("normal", "status", "reasoning") and content:
                                result_parts.append({"type": "text", "text": _safe_text(content)})
                            elif chunk_type == "tool_result":
                                raw_output = chunk.get("output", "")
                                try:
                                    if isinstance(raw_output, bytes):
                                        output_text = raw_output.decode("utf-8", errors="replace")
                                    else:
                                        output_text = str(raw_output)
                                except Exception:
                                    output_text = repr(raw_output)
                                result_parts.append({"type": "text", "text": f"[{chunk.get('name', 'tool')}: {_safe_text(output_text)}]"})

                        return ORjsonResponse({
                            "jsonrpc": "2.0",
                            "id": body.get("id"),
                            "result": {
                                "status": "ok",
                                "parts": result_parts,
                                "is_task_complete": is_task_complete,
                            },
                        })

                    return ORjsonResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": {"status": "ok"}})
                except Exception as e:
                    logger.exception("[ANP:medication_reminder] error")
                    return ORjsonResponse({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)[:200]}})
                    return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}})

            anp_app.add_route("/agent/ad.json", agent_card, methods=["GET"])
            anp_app.add_route("/agent/rpc", anp_rpc, methods=["POST"])

            async def did_document(request: Request):
                did = request.path_params.get("did", "")
                try:
                    from A2AServer.v2.did_wba import get_keystore
                    ks = get_keystore()
                    doc = ks.get_document(did) if did else None
                    if doc:
                        return ORjsonResponse(doc.to_dict())
                except Exception:
                    pass
                return ORjsonResponse({"error": "DID not found"}, status_code=404)

            anp_app.add_route("/did/document/{did}", did_document, methods=["GET"])
            server.app.mount("/anp", anp_app)
            # 阶段48-A2A: 初始化 DID keystore（自己的密钥 + bootstrap 远程公钥）
            _SELF_DID = "did:wba:pha.local:medication_reminder"
            try:
                from A2AServer.v2.did_wba import get_keystore, bootstrap_remote_dids
                ks = get_keystore(self_did=_SELF_DID)
                logger.info("[ANP] DID keystore initialized, known DIDs: %s", ks.list_dids())
                results = asyncio.run(bootstrap_remote_dids(_SELF_DID))
                logger.info("[ANP] DID bootstrap results: %s", results)
            except Exception as ks_err:
                logger.warning("[ANP] DID keystore init failed: %s", ks_err)
            logger.info("[ANP] medication_reminder /anp mounted on port %s", port)
        except Exception as anp_e:
            logger.warning("[ANP] medication_reminder ANP mount failed: %s", anp_e)

        logger.info(f"Starting agent on {host}:{port}")
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)

if __name__ == "__main__":
    main()
