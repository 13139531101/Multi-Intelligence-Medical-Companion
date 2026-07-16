"""
PHA v2 ANP Bridge - 把 hostapi + 4 个 MCP agent 包装为 ANP

阶段33：让 PHA 完整支持 ANP 协议（Agent Network Protocol）

**目标**：
- hostapi 启动时挂一个 ANP endpoint（独立 port）
- 4 个 MCP agent 也可以挂 ANP bridge
- 任何 ANP 客户端（Crawler/DID:WBA）都能发现 + 调用

**ANP 默认暴露**：
- GET  /agent/ad.json            → Agent Description (DID + skills)
- GET  /agent/interface.json     → OpenRPC 接口定义
- POST /agent/rpc                → JSON-RPC 2.0 调用
- GET  /agents                   → 列出 hostapi 已发现的所有 sub-agent
- GET  /agents/{name}/ad.json    → 转发到对应 sub-agent 的 ad.json（ANP crawler 模式）

**DID 策略**：
- hostapi:    did:wba:pha.local:hostapi
- health_advisor:  did:wba:pha.local:health_advisor
- health_records:  did:wba:pha.local:health_records
- medication_reminder: did:wba:pha.local:medication_reminder
- visit_summary:  did:wba:pha.local:visit_summary
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Any, Dict

import httpx

# 注意：anp_bridge.py 不会直接 mount，create_hostapi_anp_app() 里的
# endpoint 用 Request，必须 import
try:
    from fastapi import Request
except ImportError:
    Request = None

logger = logging.getLogger(__name__)


# ============================================================
# ANP 客户端：发现 + 远程调用
# ============================================================
async def discover_anp_agent(base_url: str, timeout: float = 3.0) -> Dict[str, Any] | None:
    """
    ANP 爬虫模式：GET /agent/ad.json 发现 agent

    Args:
        base_url: agent 基础 URL（如 http://health_advisor:10011）
        timeout: 超时秒数

    Returns:
        Agent Description dict 或 None（不可达）
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{base_url}/agent/ad.json")
            if r.status_code == 200:
                ad = r.json()
                ad["_base_url"] = base_url
                return ad
    except Exception as e:
        logger.debug("[anp] discover %s failed: %s", base_url, e)
    return None


async def discover_all_anp_agents(base_urls: list[str]) -> list[Dict[str, Any]]:
    """并发发现所有 ANP agent"""
    tasks = [discover_anp_agent(url) for url in base_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


async def call_anp_rpc(
    base_url: str,
    method: str,
    params: Dict[str, Any],
    *,
    timeout: float = 60.0,
    did: str | None = None,
) -> Dict[str, Any]:
    """
    ANP 远程调用：POST /agent/rpc

    Args:
        base_url: agent 基础 URL
        method: 方法名（如 "handle_request"）
        params: 方法参数
        timeout: 超时
        did: 可选 DID 身份（用于身份验证）

    Returns:
        JSON-RPC 2.0 响应
    """
    import uuid

    body = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": str(uuid.uuid4()),
    }

    headers = {"Content-Type": "application/json"}
    if did:
        headers["X-ANP-DID"] = did

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base_url}/agent/rpc",
            json=body,
            headers=headers,
        )
        return r.json()


# ============================================================
# 已知 PHA agent 配置（默认发现列表）
# ============================================================
def get_default_agent_urls() -> list[str]:
    """从环境变量读 agent URL 列表，默认值匹配 docker-compose"""
    urls = os.getenv("PHA_ANP_AGENT_URLS", "").strip()
    if urls:
        return [u.strip() for u in urls.split(",") if u.strip()]
    # 默认（docker compose 内）
    return [
        "http://health_records:10010",
        "http://health_advisor:10011",
        "http://medication_reminder:10012",
        "http://visit_summary:10013",
    ]


# ============================================================
# hostapi 端 ANP 服务（FastAPI 挂在 /agent）
# ============================================================
def create_hostapi_anp_app():
    """
    为 hostapi 创建 ANP 兼容的 FastAPI sub-app

    暴露：
    - GET  /agent/ad.json          → hostapi 自己的 AD
    - GET  /agent/interface.json   → hostapi 的接口
    - POST /agent/rpc              → hostapi 的方法
    - GET  /agents                 → 已发现的所有 PHA ANP agent
    """
    try:
        from fastapi import FastAPI
        from anp.openanp import AgentConfig, anp_agent, interface
    except ImportError as e:
        raise ImportError(
            f"需要安装 anp + fastapi: pip install 'anp[api]' fastapi"
        ) from e

    @anp_agent(AgentConfig(
        name="HostAPI",
        did="did:wba:pha.local:hostapi",
        prefix="/agent",
        description="PHA Host API - 多 agent 编排器，支持 A2A/MCP/ANP 三协议",
    ))
    class HostAPIANP:
        """HostAPI ANP Bridge"""

        @interface
        async def route_query(
            self,
            user_id: str,
            query: str,
            conversation_id: str = "default",
        ) -> Dict[str, Any]:
            """
            ANP 客户端调用入口：
            1. hostapi 路由到合适的 sub-agent
            2. forward 调用
            3. 返回结果
            """
            # 这里复用 host_graph.route_and_invoke
            from .host_graph import route_and_invoke
            result = await route_and_invoke(
                query=query,
                conversation_id=conversation_id,
                user_id=user_id,
                mode="single",
            )
            return {
                "agent": "hostapi",
                "routing": result.get("routing"),
                "content": result.get("content", ""),
                "tool_calls": result.get("tool_calls", []),
            }

        @interface
        async def parallel_query(
            self,
            user_id: str,
            query: str,
            conversation_id: str = "default",
        ) -> Dict[str, Any]:
            """ANP 客户端调用：4 个 sub-agent 并行（阶段30 multi 模式）"""
            from .host_graph import route_and_invoke
            result = await route_and_invoke(
                query=query,
                conversation_id=conversation_id,
                user_id=user_id,
                mode="multi",
            )
            return {
                "agent": "hostapi_multi",
                "routing": result.get("routing"),
                "content": result.get("content", ""),
                "parallel_responses": result.get("parallel_responses", {}),
            }

        @interface
        async def list_agents(self) -> Dict[str, Any]:
            """ANP crawler：列出所有 PHA agent"""
            from .agent_registry import discover_agents
            specs = discover_agents()
            return {
                "count": len(specs),
                "agents": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "did": f"did:wba:pha.local:{s.name}",
                        "keywords": s.keywords,
                        "enabled": s.enabled,
                    }
                    for s in specs
                ],
            }

    app = FastAPI(title="PHA HostAPI ANP Bridge")
    app.include_router(HostAPIANP.router())

    # ANP 代理：forward 到 PHA 内部其他 agent（crawler 友好）
    @app.get("/agents")
    async def list_discovered_agents():
        """ANP 列出已发现的 PHA agent"""
        from .agent_registry import discover_agents
        specs = discover_agents()
        return {
            "count": len(specs),
            "agents": [
                {
                    "name": s.name,
                    "description": s.description,
                    "did": f"did:wba:pha.local:{s.name}",
                    "did_wba": f"did:wba:pha.local:{s.name}",
                }
                for s in specs
            ],
        }

    @app.get("/agents/discover")
    async def discover_external():
        """ANP 爬虫：主动发现所有外部 ANP agent（简单版，向后兼容）"""
        urls = get_default_agent_urls()
        agents = await discover_all_anp_agents(urls)
        return {
            "discovered_count": len(agents),
            "candidates": urls,
            "agents": agents,
        }

    @app.get("/agents/crawl")
    async def crawl_external(
        max_depth: int = 2,
        max_nodes: int = 50,
        force_refresh: bool = False,
    ):
        """
        阶段38-1: ANP 递归爬虫（增强版）
        - 从种子 URL 开始 BFS
        - 拉 /agent/ad.json
        - 解析 relatedAgents / sameAs / seeAlso
        - 递归爬 (max_depth)
        - 按 DID 去重
        - 5 分钟缓存
        """
        from .anp_crawler import crawl_with_cache
        urls = get_default_agent_urls()
        result = await crawl_with_cache(
            seed_urls=urls,
            cache_key="external_crawl",
            force_refresh=force_refresh,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        return {
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "duration_ms": result.duration_ms,
            "seed_count": result.seed_count,
            "discovered_count": result.discovered_count,
            "reachable_count": result.reachable_count,
            "failed_count": len(result.failed_urls),
            "failed_urls": result.failed_urls,
            "nodes": [n.to_dict() for n in result.nodes],
            "graph": result.graph,
        }

    @app.get("/agents/crawl/cache")
    async def crawl_cache_status():
        """查看 ANP crawler 缓存状态"""
        from .anp_crawler import get_cached_crawl
        cached = get_cached_crawl("external_crawl")
        if not cached:
            return {"cached": False}
        return {
            "cached": True,
            "finished_at": cached.finished_at,
            "age_seconds": time.time() - cached.finished_at,
            "discovered_count": cached.discovered_count,
            "reachable_count": cached.reachable_count,
        }

    @app.get("/agents/crawl/clear")
    async def crawl_cache_clear():
        """清 ANP crawler 缓存"""
        from .anp_crawler import clear_crawl_cache
        clear_crawl_cache()
        return {"cleared": True}

    @app.get("/did/resolve/{did}")
    async def did_resolve(did: str):
        """阶段38-1: DID 解析（DID:WBA → URL）"""
        from .anp_crawler import resolve_did_to_url
        url = resolve_did_to_url(did)
        if not url:
            return {"did": did, "resolved": False}
        return {"did": did, "resolved": True, "url": url}

    # ============================================================
    # 阶段39-2: DID WBA 签名/验证 HTTP 端点
    # ============================================================
    from .did_wba import get_keystore as _get_keystore, verify_request

    @app.get("/did/list")
    async def did_list():
        """阶段39-2: 列出所有已注册的 DID"""
        ks = _get_keystore()
        return {
            "dids": [
                {
                    "did": did,
                    "doc": ks.get_document(did).to_dict() if ks.get_document(did) else None,
                }
                for did in ks.list_dids()
            ]
        }

    @app.get("/did/document/{did}")
    async def did_document(did: str):
        """阶段39-2: 获取 DID 文档（含公钥）"""
        ks = _get_keystore()
        doc = ks.get_document(did)
        if not doc:
            return {"resolved": False, "did": did}
        return {"resolved": True, "did": did, "document": doc.to_dict()}

    @app.post("/did/verify")
    async def did_verify(req: Request):
        """阶段39-2: 验证签名

        body: {did, signature, method, path, body, timestamp}
        """
        body = await req.json()
        did = body.get("did")
        signature = body.get("signature")
        method = body.get("method", "GET")
        path = body.get("path", "/")
        req_body = body.get("body", "")
        timestamp = body.get("timestamp")

        ks = _get_keystore()
        doc = ks.get_document(did)
        if not doc:
            return {"valid": False, "error": "unknown did"}

        public_key = base64.b64decode(doc.public_key)
        valid, err = verify_request(public_key, signature, method, path, req_body, timestamp)
        return {"valid": valid, "error": err, "did": did}

    @app.post("/did/sign")
    async def did_sign(req: Request):
        """阶段39-2: 用某 DID 私钥签名（仅测试用，生产应禁用）"""
        from .did_wba import sign_request
        body = await req.json()
        did = body.get("did")
        method = body.get("method", "GET")
        path = body.get("path", "/")
        req_body = body.get("body", "")

        ks = _get_keystore()
        private_key = ks.get_private_key(did)
        if not private_key:
            return {"error": "no private key for did"}

        signature = sign_request(private_key, method, path, req_body)
        return {
            "did": did,
            "signature": signature,
            "timestamp": time.time(),
        }

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "anp": True,
            "version": "2.0-stage33",
        }

    return app


__all__ = [
    "discover_anp_agent",
    "discover_all_anp_agents",
    "call_anp_rpc",
    "create_hostapi_anp_app",
    "get_default_agent_urls",
]