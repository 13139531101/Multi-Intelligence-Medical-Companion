"""阶段48-21: Domain Manifest API 端点.

让前端能读当前 domain 配置 + 切换 domain.

端点:
  GET  /v2/manifest           - 当前 domain 详情 (含 agents / port / did)
  GET  /v2/manifest/list      - 所有可用 yaml (for 下拉切换)
  POST /v2/manifest/switch    - 切换 domain (写到文件 + 重置 runtime cache)
"""
from __future__ import annotations
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from .domain_manifest import (
    load_default,
    DomainManifest,
    AgentSpec,
    DEFAULT_MANIFEST_ENV,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/manifest", tags=["manifest"])


# ============================================================
# Response models
# ============================================================
class AgentInfo(BaseModel):
    name: str
    display_name: str
    description: str
    keywords: list[str]
    aliases: list[str]
    port: Optional[int] = None
    dangerously: bool = False
    phacore_modules: list[str] = []
    tools_module: Optional[str] = None


class ManifestResponse(BaseModel):
    domain_name: str
    display_name: str
    description: str
    version: str
    host_agent: str
    agents: list[AgentInfo]
    did_domain: str
    did_prefix: str
    mcp_transport: str
    source: str                              # yaml path or "<hardcoded>"
    env_name: Optional[str] = None           # PHA_DOMAIN_MANIFEST 当前值


@router.get("", response_model=ManifestResponse)
async def get_manifest(request: Request):
    """获取当前 domain manifest."""
    m = load_default()
    return ManifestResponse(
        domain_name=m.domain.name,
        display_name=m.domain.display_name,
        description=m.domain.description,
        version=m.domain.version,
        host_agent=m.host_agent_name,
        agents=[
            AgentInfo(
                name=a.name,
                display_name=a.display_name,
                description=a.description,
                keywords=a.keywords,
                aliases=a.aliases,
                port=a.port,
                dangerously=a.dangerously,
                phacore_modules=a.phacore_modules,
                tools_module=a.tools_module,
            )
            for a in m.agents
        ],
        did_domain=m.did_domain,
        did_prefix=m.did_prefix,
        mcp_transport=m.mcp_transport,
        source=m.source_path or "<unknown>",
        env_name=os.getenv(DEFAULT_MANIFEST_ENV),
    )


@router.get("/list")
async def list_available_manifests():
    """列出 examples/domain_configs/ 下所有可用 yaml (前端下拉)."""
    from .domain_manifest import _MANIFEST_DIR
    if not _MANIFEST_DIR.exists():
        return {"manifests": [], "manifest_dir": str(_MANIFEST_DIR)}
    manifests = []
    for p in sorted(_MANIFEST_DIR.glob("*.yaml")):
        try:
            preview = DomainManifest.from_yaml(p)
            manifests.append({
                "file": p.name,
                "name": preview.domain.name,
                "display_name": preview.domain.display_name,
                "description": preview.domain.description,
                "agent_count": len(preview.agents),
                "host_agent": preview.host_agent_name,
            })
        except Exception as e:
            logger.warning("[manifest/] cannot parse %s: %s", p, e)
    return {"manifests": manifests, "manifest_dir": str(_MANIFEST_DIR)}


class SwitchManifestRequest(BaseModel):
    name: str = ""                          # yaml basename (不带 .yaml)
    file: str = ""                          # 完整 yaml 路径


@router.post("/switch")
async def switch_manifest(req: SwitchManifestRequest):
    """切换 domain (运行时).

    策略 (阶段 48-21):
      1. 写到 env var (process-level, 不持久化)
      2. 重新 load manifest, 验证 yaml 可读
      3. 返回 {ok, manifest}
      注: agent 端 runtime cache (v2_runtime 单例) 会在下次 get_middlewares 时自动刷新.
    """
    target = req.file
    if not target and req.name:
        from .domain_manifest import _MANIFEST_DIR
        candidate = _MANIFEST_DIR / f"{req.name}.yaml"
        if not candidate.exists():
            raise HTTPException(404, f"找不到 yaml: {req.name} (在 {_MANIFEST_DIR})")
        target = str(candidate)
    if not target:
        raise HTTPException(400, "需要 name 或 file 字段")

    # 1. 先验证 yaml 能 load
    try:
        m = DomainManifest.from_yaml(target)
    except Exception as e:
        raise HTTPException(400, f"yaml 加载失败: {e}")

    # 2. 写到 env var
    os.environ[DEFAULT_MANIFEST_ENV] = target
    logger.info("[manifest/switch] 切换到 %s (%s)", m.domain.name, target)

    return {
        "ok": True,
        "domain_name": m.domain.name,
        "display_name": m.domain.display_name,
        "agent_count": len(m.agents),
        "host_agent": m.host_agent_name,
        "note": "env var 已更新. 现有 tool cache 会在下次请求时自动读新 manifest.",
    }


@router.get("/dangerous")
async def get_dangerous_agents():
    """当前 domain 里哪些 agent 是 dangerously=true (前端显示 HITL 候选)."""
    m = load_default()
    return {
        "dangerous_agents": m.dangerous_agents(),
        "count": len(m.dangerous_agents()),
    }


__all__ = ["router"]
