"""
PHA v2 - ANP Bridge（阶段33）

**作用**：把 PHA 的 4 个 A2A MCP agent 包装为 ANP 协议兼容的 agent。

**架构**：
```
[hostapi] → A2A JSON-RPC → [MCP Agent container]
                          ↓
                  [ANP Bridge (本文件)]
                          ↓
              /agent/ad.json (ANP Agent Description)
              /agent/interface.json (OpenRPC)
              /agent/rpc (JSON-RPC 2.0)
```

**部署**：每个 MCP agent 容器多启动一个 ANP FastAPI（端口不同），
或共用同一个 FastAPI app 同时挂载 A2A + ANP 路由。

**验证**：
- ANP 客户端用 GET /agent/ad.json 拿到 Agent Description
- ANP 客户端用 GET /agent/interface.json 拿到 OpenRPC 接口
- ANP 客户端用 POST /agent/rpc 调用方法（forward 到原 A2A handler）
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def create_anp_agent(
    *,
    agent_name: str,
    description: str,
    did_domain: str,
    forward_to_a2a: callable,
    prefix: str = "/agent",
):
    """
    创建 ANP agent（包装现有的 A2A MCP server）

    Args:
        agent_name: "HealthAdvisor" / "HealthRecords" / "MedicationReminder" / "VisitSummary"
        description: agent 描述
        did_domain: DID 域名（"pha.example.com"）
        forward_to_a2a: 实际调用 A2A 的函数（同步或异步）
        prefix: ANP 路由前缀（默认 /agent）

    Returns:
        FastAPI app + router
    """
    try:
        from anp.openanp import AgentConfig, anp_agent, interface
    except ImportError as e:
        raise ImportError(f"ANP SDK 未安装: pip install 'anp[api]'") from e

    @anp_agent(AgentConfig(
        name=agent_name,
        did=f"did:wba:{did_domain}:{agent_name.lower()}",
        prefix=prefix,
        description=description,
    ))
    class _ANPBridge:
        """ANP Bridge：把 ANP 调用 forward 到 A2A"""

        @interface
        async def handle_request(
            self,
            user_id: str,
            query: str,
            session_id: str = "default",
            metadata: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            """处理 ANP 调用 → forward 到 A2A"""
            try:
                logger.info(
                    "[ANP bridge %s] handle_request user=%s query=%s",
                    agent_name, user_id, query[:50],
                )
                result = await forward_to_a2a(
                    user_id=user_id,
                    query=query,
                    session_id=session_id,
                    metadata=metadata or {},
                )
                return {
                    "agent": agent_name,
                    "status": "ok",
                    "result": result,
                }
            except Exception as e:
                logger.exception("[ANP bridge %s] error", agent_name)
                return {
                    "agent": agent_name,
                    "status": "error",
                    "error": str(e),
                }

        @interface
        async def describe(self) -> Dict[str, Any]:
            """ANP metadata：返回 agent 详细描述"""
            return {
                "agent": agent_name,
                "description": description,
                "did": f"did:wba:{did_domain}:{agent_name.lower()}",
                "transport": "a2a+anp",
                "version": "2.0-stage33",
            }

    return _ANPBridge


def create_anp_app(
    *,
    agent_name: str,
    description: str,
    forward_to_a2a: callable,
    did_domain: str = "pha.local",
    prefix: str = "/agent",
):
    """
    创建独立 ANP FastAPI app（独立端口）

    Returns:
        FastAPI app
    """
    try:
        from fastapi import FastAPI
    except ImportError:
        raise ImportError("FastAPI required")

    bridge = create_anp_agent(
        agent_name=agent_name,
        description=description,
        did_domain=did_domain,
        forward_to_a2a=forward_to_a2a,
        prefix=prefix,
    )

    app = FastAPI(title=f"PHA {agent_name} ANP Bridge")
    app.include_router(bridge.router())

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": agent_name, "transport": "anp+a2a"}

    return app


# ANP 默认配置
ANP_AGENT_CONFIGS = {
    "health_advisor": {
        "description": "AI 问诊、健康教育、症状分析",
        "default_did_domain": "pha.local",
    },
    "health_records": {
        "description": "检查报告 OCR、存储、检索",
        "default_did_domain": "pha.local",
    },
    "medication_reminder": {
        "description": "药品安全、用药计划、提醒通知",
        "default_did_domain": "pha.local",
    },
    "visit_summary": {
        "description": "就诊记录整理、报告生成",
        "default_did_domain": "pha.local",
    },
}


__all__ = ["create_anp_agent", "create_anp_app", "ANP_AGENT_CONFIGS"]