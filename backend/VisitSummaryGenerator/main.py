import logging
import os
import sys
from starlette.applications import Starlette

import click
from dotenv import load_dotenv

# Prefer local A2AServer/src over site-packages
_current_dir = os.path.dirname(__file__)
_src_path = os.path.abspath(
    os.path.join(_current_dir, "..", "A2AServer", "src")
)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

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


def build_app(host: str, port: int, agent_prompt_file: str, model_name: str,
              provider: str, mcp_config_path: str, agent_url: str = "") -> Starlette:
    """
    构建 A2AServer + ANP Starlette app（阶段48-ops: 支持 uvicorn --workers 多进程）。

    所有初始化（MCP preload / DID keystore）移入 lifespan，
    确保每个 uvicorn worker 独立初始化。
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    import uuid

    from A2AServer.agent import BasicAgent
    from A2AServer.common.A2Atypes import AgentCapabilities, AgentCard, AgentSkill
    from A2AServer.common.server import A2AServer
    from A2AServer.task_manager import AgentTaskManager

    input_mode, output_mode = ["text", "text/plain"], ["text", "text/plain"]
    BasicAgent.SUPPORTED_CONTENT_TYPES = input_mode

    capabilities = AgentCapabilities(streaming=True)
    skill = AgentSkill(
        id="VisitSummaryGenerator",
        name="就诊摘要生成",
        description="处理医疗文档、生成就诊摘要和提供健康分析",
        tags=["医疗文档", "摘要生成", "健康分析"],
        examples=[
            "解析门诊记录并提取关键信息",
            "生成综合就诊摘要报告",
            "分析健康趋势和风险评估",
        ],
    )
    if not agent_url:
        agent_url = f"http://{host}:{port}/"
    agent_card = AgentCard(
        name="就诊摘要生成",
        description="就诊摘要生成智能体，专门处理医疗文档、生成就诊摘要和提供健康分析",
        url=agent_url,
        version="1.0.0",
        defaultInputModes=input_mode,
        defaultOutputModes=output_mode,
        capabilities=capabilities,
        skills=[skill],
    )
    agent = BasicAgent(
        config_path=mcp_config_path,
        model_name=model_name,
        prompt_file=agent_prompt_file,
        provider=provider,
    )

    # 阶段48-ops: VisitSummaryGenerator 无独立记忆服务，仅初始化 MCP / DID
    async def on_startup_callback():
        """每个 uvicorn worker 启动时执行一次初始化"""
        # 1. MCP 工具预加载
        try:
            if not getattr(agent, "tool_ready", False):
                logger.info("[lifespan] preloading MCP tools...")
                await agent.setup_tools()
                logger.info("[lifespan] MCP tools loaded")
        except Exception as e:
            logger.error(f"[lifespan] MCP preload failed: {e}")

        # 2. DID keystore bootstrap
        try:
            from A2AServer.v2.did_wba import get_keystore, bootstrap_remote_dids
            _SELF_DID = "did:wba:pha.local:visit_summary"
            ks = get_keystore(self_did=_SELF_DID)
            logger.info(f"[lifespan] DID keystore ready, DIDs: {ks.list_dids()}")
            results = await bootstrap_remote_dids(_SELF_DID)
            logger.info(f"[lifespan] DID bootstrap: {results}")
        except Exception as e:
            logger.warning(f"[lifespan] DID bootstrap failed: {e}")

    # 构建 A2AServer（lifespan 接收 on_startup 回调）
    server = A2AServer(
        agent_card=agent_card,
        task_manager=AgentTaskManager(agent=agent),
        host=host,
        port=port,
        on_startup=on_startup_callback,
    )

    # 阶段48-A2A: 挂载纯 Starlette ANP 端点到 /anp
    try:
        anp_app = Starlette()

        class ORjsonResponse(JSONResponse):
            def render(self, content) -> bytes:
                import orjson
                return orjson.dumps(content)

        async def agent_card_handler(_request: Request):
            return ORjsonResponse({
                "name": "VisitSummaryGenerator",
                "description": "就诊摘要生成",
                "version": "2.0-stage48-A2A",
                "did": "did:wba:pha.local:visit_summary",
                "endpoints": [{"url": "http://visit_summary:10013/anp", "type": "ANP"}],
                "capabilities": {"streaming": True},
            })

        async def anp_rpc(request: Request):
            """ANP JSON-RPC 2.0 handler → V2Agent.stream()"""
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

                # Ed25519 DID 签名验证
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
                            valid, err = verify_request(
                                pub_bytes, sig_b64, "POST", "/agent/rpc",
                                body_str, timestamp=ts
                            )
                            if not valid:
                                logger.warning("[ANP] sig verify failed for %s: %s", caller_did, err)
                                return ORjsonResponse({
                                    "jsonrpc": "2.0", "id": body.get("id"),
                                    "error": {"code": -32603, "message": f"invalid sig: {err}"},
                                })
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
                        return JSONResponse({
                            "jsonrpc": "2.0", "id": body.get("id"),
                            "result": {"status": "ok", "parts": [], "is_task_complete": True},
                        })

                    logger.info("[ANP:visit_summary] query=%s session=%s user=%s",
                                query[:50], session_id, user_id)

                    from A2AServer.v2.sub_agents import VisitSummaryV2
                    model = os.getenv("LLM_MODEL", "deepseek-chat")
                    agent_instance = VisitSummaryV2(model=model)
                    result_parts = []
                    is_task_complete = False

                    async for chunk in agent_instance.stream(query, session_id, user_id):
                        chunk_type = chunk.get("type", "normal")
                        content = chunk.get("content", "")
                        if chunk_type == "complete":
                            is_task_complete = True
                            break
                        if chunk_type == "error":
                            logger.error("[ANP] stream error: %s", content)
                            return ORjsonResponse({
                                "jsonrpc": "2.0", "id": body.get("id"),
                                "error": {"code": -32603, "message": str(content)[:500]},
                            })
                        if chunk_type in ("normal", "status", "reasoning") and content:
                            result_parts.append({"type": "text", "text": _safe_text(content)})
                        elif chunk_type == "tool_result":
                            raw_output = chunk.get("output", "")
                            try:
                                output_text = raw_output.decode("utf-8", errors="replace") \
                                    if isinstance(raw_output, bytes) else str(raw_output)
                            except Exception:
                                output_text = repr(raw_output)
                            result_parts.append({
                                "type": "text",
                                "text": f"[{chunk.get('name', 'tool')}: {_safe_text(output_text)}]"
                            })

                    return ORjsonResponse({
                        "jsonrpc": "2.0", "id": body.get("id"),
                        "result": {
                            "status": "ok",
                            "parts": result_parts,
                            "is_task_complete": is_task_complete,
                        },
                    })

                return ORjsonResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": {"status": "ok"}})

            except Exception as e:
                logger.exception("[ANP:visit_summary] error")
                return ORjsonResponse({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)[:200]}})

        async def did_document(_request: Request):
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

        async def metrics_handler(_request):
            try:
                sys.path.insert(0, "/app/A2AServer/src")
                from A2AServer.observability.metrics import get_metrics_bytes, get_metrics_content_type
                from starlette.responses import Response
                return Response(content=get_metrics_bytes(), media_type=get_metrics_content_type())
            except Exception:
                return JSONResponse({"error": "metrics unavailable"}, status_code=503)

        anp_app.add_route("/agent/ad.json", agent_card_handler, methods=["GET"])
        anp_app.add_route("/agent/rpc", anp_rpc, methods=["POST"])
        anp_app.add_route("/did/document/{did}", did_document, methods=["GET"])
        anp_app.add_route("/metrics", metrics_handler, methods=["GET"])

        server.app.mount("/anp", anp_app)
        logger.info(f"[ANP] visit_summary /anp mounted on port {port}")

    except Exception as anp_e:
        logger.warning(f"[ANP] visit_summary ANP mount failed: {anp_e}")

    return server.app


@click.command(help="启动就诊摘要生成 A2A Server")
@click.option("--host", "host", default="localhost",
              help="服务器绑定的主机名（默认为 localhost）")
@click.option("--port", "port", default=10013, help="服务器监听的端口号（默认为 10013）")
@click.option("--prompt", "agent_prompt_file", default="memory_enhanced_agent_prompt.md",
              help="Agent 的 prompt 文件路径")
@click.option("--model", "model_name", default="deepseek-chat",
              help="使用的模型名称")
@click.option("--provider", "provider", default="deepseek",
              help="模型提供方名称")
@click.option("--mcp_config", "mcp_config_path", default="mcp_config.json",
              help="MCP 配置文件路径")
@click.option("--agent_url", "agent_url", default="",
              help="Agent Card 中对外展示和访问的地址")
@click.option("--factory", "factory_mode", is_flag=True, default=False,
              help="阶段48-ops: 仅构建 app，不启动服务器（供 uvicorn --workers 调用）")
def main(host, port, agent_prompt_file, model_name, provider,
         mcp_config_path, agent_url, factory_mode):
    """启动就诊摘要生成 A2A Server"""
    if factory_mode:
        # uvicorn --workers 模式：只返回 app，进程管理由 uvicorn 负责
        return

    app = build_app(host, port, agent_prompt_file, model_name,
                    provider, mcp_config_path, agent_url)

    import uvicorn
    logger.info(f"Starting agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    main()