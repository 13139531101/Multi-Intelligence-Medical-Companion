"""阶段48-20: Domain Manifest Loader.

让 PHA 平台从"健康助手"变成"多领域多智能体平台".
用一个 yaml 文件描述整个 agent 拓扑, 切换场景只换 yaml, 代码 0 改.

用法:
    from .domain_manifest import DomainManifest, load_default
    manifest = load_default()           # 默认 PHA 健康
    # 或
    manifest = DomainManifest.from_yaml("examples/domain_configs/hr_bot.yaml")

然后用:
    manifest.agents                    # list of AgentSpec
    manifest.get_agent("health_advisor")
    manifest.host_agent_name           # "health_advisor"
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


# 环境变量控制
DEFAULT_MANIFEST_ENV = "PHA_DOMAIN_MANIFEST"     # 例: "pha.health" / "hr.company" / "edu.tutor"
# 找 examples/domain_configs/, 从 __file__ 向上遍历, 找到第一个匹配.
# 这是兼容本地开发 (i:\A2A\3\A2AServer\backend\A2AServer\src\A2AServer\v2)
# 和 Docker container (/app/A2AServer/v2) 两种深度.
_THIS = Path(__file__).resolve()
_CANDIDATES = []
# 试 0..8 每一个 parent 深度
try:
    for i in range(min(len(_THIS.parents), 9)):
        _CANDIDATES.append(_THIS.parents[i] / "examples" / "domain_configs")
except Exception:
    pass

# 兜底: env var PHA_MANIFEST_DIR
_env_dir = os.getenv("PHA_MANIFEST_DIR")
if _env_dir:
    _CANDIDATES.insert(0, Path(_env_dir))

_MANIFEST_DIR = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0] if _CANDIDATES else _THIS.parents[2])


@dataclass
class AgentSpec:
    """yaml 里的一个 agent 配置."""
    name: str                                              # "health_advisor"
    display_name: str = ""                                  # "健康顾问"
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    tools_module: Optional[str] = None
    phacore_modules: List[str] = field(default_factory=list)   # ["ocr"] re-export
    aliases: List[str] = field(default_factory=list)
    dangerously: bool = False                              # HITL required
    port: Optional[int] = None

    def to_registry_kwargs(self) -> dict:
        """转成 @register_agent 等价的 kwargs."""
        return {
            "name": self.name,
            "description": self.display_name or self.description,
            "keywords": self.keywords,
            "tools_module": self.tools_module,
            "aliases": self.aliases,
            "enabled": True,
        }


@dataclass
class ServiceDiscovery:
    default_port_offset: int = 10010
    services: Dict[str, int] = field(default_factory=dict)

    def get_port(self, agent_name: str, agent_spec_port: Optional[int] = None) -> int:
        if agent_spec_port:
            return agent_spec_port
        if agent_name in self.services:
            return self.services[agent_name]
        # fallback: auto
        return self.default_port_offset + hash(agent_name) % 100


@dataclass
class HostConfig:
    name: str = "main"                # fallback agent
    fallback_keywords: List[str] = field(default_factory=list)
    classify_model: str = "deepseek-chat"


@dataclass
class DomainConfig:
    name: str = "default"
    display_name: str = ""
    description: str = ""
    version: str = "0.1.0"


@dataclass
class DomainManifest:
    """总 manifest, 一切配置都从这里读."""
    domain: DomainConfig = field(default_factory=DomainConfig)
    host: HostConfig = field(default_factory=HostConfig)
    agents: List[AgentSpec] = field(default_factory=list)
    service_discovery: ServiceDiscovery = field(default_factory=ServiceDiscovery)
    did_domain: str = "pha.local"
    did_prefix: str = "did:wba"
    mcp_transport: str = "streamable_http"
    tool_filter_blacklist: List[str] = field(default_factory=list)

    # 来源 (yaml path) - 用于 debug
    source_path: Optional[str] = None

    @property
    def host_agent_name(self) -> str:
        return self.host.name

    def get_agent(self, name: str) -> Optional[AgentSpec]:
        for a in self.agents:
            if a.name == name:
                return a
        return None

    def get_agent_by_alias(self, alias: str) -> Optional[AgentSpec]:
        for a in self.agents:
            if alias in a.aliases or a.display_name == alias:
                return a
        return None

    def dangerous_agents(self) -> List[str]:
        return [a.name for a in self.agents if a.dangerously]

    # -----------------------------------------------------------
    # 加载
    # -----------------------------------------------------------
    @classmethod
    def from_yaml(cls, path: str | Path) -> "DomainManifest":
        """从 yaml 文件加载.

        yaml 结构参考 examples/domain_configs/pha.health.yaml.
        """
        import yaml   # 兼容 PyYAML 已装 (pha project 已有)
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"[DomainManifest] 不存在: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        m = cls()
        m.source_path = str(path)

        # domain
        d = data.get("domain", {})
        m.domain = DomainConfig(
            name=d.get("name", path.stem),
            display_name=d.get("display_name", path.stem),
            description=d.get("description", ""),
            version=d.get("version", "0.1.0"),
        )

        # host
        h = data.get("host", {})
        m.host = HostConfig(
            name=h.get("name", m.agents[0].name if m.agents else "main"),
            fallback_keywords=h.get("fallback_keywords", []),
            classify_model=h.get("classify_model", "deepseek-chat"),
        )

        # agents
        for ad in data.get("agents", []):
            m.agents.append(AgentSpec(
                name=ad["name"],
                display_name=ad.get("display_name", ad.get("description", "")),
                description=ad.get("description", ""),
                keywords=ad.get("keywords", []),
                tools_module=ad.get("tools_module"),
                phacore_modules=ad.get("phacore_modules", []),
                aliases=ad.get("aliases", []),
                dangerously=ad.get("dangerously", False),
                port=ad.get("port"),
            ))

        # service_discovery
        sd = data.get("service_discovery", {})
        m.service_discovery = ServiceDiscovery(
            default_port_offset=sd.get("default_port_offset", 10010),
            services=sd.get("services", {}),
        )

        # did
        d = data.get("did", {})
        m.did_domain = d.get("domain", "pha.local")
        m.did_prefix = d.get("prefix", "did:wba")

        # mcp
        m.mcp_transport = data.get("mcp_transport", "streamable_http")

        # tool filter
        m.tool_filter_blacklist = data.get("tool_filter", {}).get("blacklist", [])

        logger.info(
            "[DomainManifest] loaded %s (agents=%d, host=%s) from %s",
            m.domain.name, len(m.agents), m.host.name, path,
        )
        return m


def load_default() -> DomainManifest:
    """根据 PHA_DOMAIN_MANIFEST 环境变量加载 manifest.

    优先级:
      1. $PHA_DOMAIN_MANIFEST 完整路径 或 不带后缀的文件名 (在 examples/domain_configs/ 下找)
      2. 默认 examples/domain_configs/pha.health.yaml

    不需要依赖 yaml 也能 fallback (硬编码 PHA 默认 4 agent)
    """
    env = os.getenv(DEFAULT_MANIFEST_ENV)
    if env:
        if env.endswith((".yaml", ".yml")):
            path = env if os.path.exists(env) else _MANIFEST_DIR / env
        else:
            path = _MANIFEST_DIR / f"{env}.yaml"
        if Path(path).exists():
            return DomainManifest.from_yaml(path)
        logger.warning("[DomainManifest] env %s=%s 找不到, 用默认", DEFAULT_MANIFEST_ENV, env)

    default = _MANIFEST_DIR / "pha.health.yaml"
    if default.exists():
        return DomainManifest.from_yaml(default)
    return _hardcoded_pha_manifest()


def _hardcoded_pha_manifest() -> DomainManifest:
    """兼容 fallback: 没 yaml 时用硬编码 PHA 默认 4 agent (向后兼容 stage 48-19 之前)."""
    m = DomainManifest()
    m.source_path = "<hardcoded>"
    m.domain = DomainConfig(name="pha_legacy", display_name="PHA 默认 (legacy)")
    m.agents = [
        AgentSpec(name="health_advisor", display_name="健康顾问",
                  keywords=["头疼", "发烧", "症状", "blood 血压 血糖"],
                  tools_module="health_advisor", phacore_modules=["ocr"],
                  aliases=["健康顾问"], port=9101),
        AgentSpec(name="health_records", display_name="健康档案管理员",
                  keywords=["档案", "体检", "报告"],
                  tools_module="health_records", phacore_modules=["ocr"],
                  aliases=["健康档案管理员"], port=9102),
        AgentSpec(name="medication_reminder", display_name="用药提醒助手",
                  keywords=["药", "提醒", "medication"],
                  tools_module="medication_reminder", phacore_modules=["ocr"],
                  aliases=["用药提醒助手"], dangerously=True, port=9103),
        AgentSpec(name="visit_summary", display_name="就诊摘要生成器",
                  keywords=["摘要", "总结", "就诊"],
                  tools_module="visit_summary", phacore_modules=[],
                  aliases=["就诊摘要"], port=9104),
    ]
    m.host = HostConfig(name="health_advisor", fallback_keywords=["怎么办"])
    return m


__all__ = [
    "DomainManifest",
    "DomainConfig",
    "AgentSpec",
    "HostConfig",
    "ServiceDiscovery",
    "load_default",
]
