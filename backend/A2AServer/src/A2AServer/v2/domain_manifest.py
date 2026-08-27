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
    peers: List[str] = field(default_factory=list)       # 阶段48-A2A: 允许调用的其他 agent 列表

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

    def can_call(self, caller: str, callee: str) -> bool:
        """
        阶段48-A2A: 检查 caller 是否被允许调用 callee（信任边界）。
        - caller 在 peers 列表中声明了 callee → 允许
        - callee 未定义 peers（空列表）→ 允许（向后兼容）
        - caller 未在 manifest 中注册 → 允许（向后兼容）
        """
        for a in self.agents:
            if a.name == caller:
                peers = a.peers
                if not peers:  # 空列表表示允许所有
                    return True
                return callee in peers
        # caller 不在 manifest 中，保守允许
        return True

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
                peers=ad.get("peers", []),   # 阶段48-A2A
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


def _build_manifest_from_env() -> Optional[DomainManifest]:
    """
    阶段48-config: 完全从环境变量构建 manifest。
    如果 PHA_DOMAIN 没有配置，返回 None 回退到 YAML 方式。
    """
    domain_name = os.getenv("PHA_DOMAIN")
    if not domain_name:
        return None

    m = DomainManifest()
    m.source_path = "<env>"

    # domain
    m.domain = DomainConfig(
        name=domain_name,
        display_name=os.getenv("PHA_DOMAIN_DISPLAY_NAME", domain_name),
        description=os.getenv("PHA_DOMAIN_DESCRIPTION", ""),
        version=os.getenv("PHA_DOMAIN_VERSION", "0.1.0"),
    )

    # host
    m.host = HostConfig(
        name=os.getenv("PHA_HOST_NAME", "health_advisor"),
        fallback_keywords=_parse_list(os.getenv("PHA_HOST_FALLBACK_KEYWORDS", "怎么办,怎么,为什么")),
        classify_model=os.getenv("PHA_HOST_CLASSIFY_MODEL", "deepseek-chat"),
    )

    # did
    m.did_domain = os.getenv("PHA_DID_DOMAIN", "pha.local")
    m.did_prefix = os.getenv("PHA_DID_PREFIX", "did:wba")

    # mcp
    m.mcp_transport = os.getenv("PHA_MCP_TRANSPORT", "streamable_http")

    # tool filter
    blacklist_str = os.getenv("PHA_TOOL_BLACKLIST", "")
    m.tool_filter_blacklist = _parse_list(blacklist_str)

    # agents: 从环境变量构建（支持最多 4 个）
    agent_names = os.getenv("PHA_AGENT_NAMES", "health_advisor,health_records,medication_reminder,visit_summary")
    for name in _parse_list(agent_names):
        env_prefix = f"{name.upper().replace('-', '_')}_"
        agent = AgentSpec(
            name=name,
            display_name=os.getenv(f"{env_prefix}DISPLAY_NAME", name),
            description=os.getenv(f"{env_prefix}DESCRIPTION", ""),
            keywords=_parse_list(os.getenv(f"{env_prefix}KEYWORDS", "")),
            tools_module=os.getenv(f"{env_prefix}TOOLS_MODULE", name),
            phacore_modules=_parse_list(os.getenv(f"{env_prefix}PHACORE_MODULES", "ocr")),
            aliases=_parse_list(os.getenv(f"{env_prefix}ALIASES", "")),
            dangerously=os.getenv(f"{env_prefix}DANGEROUSLY", "false").lower() == "true",
            port=int(os.getenv(f"{env_prefix}PORT", _get_default_port(name))),
            peers=_parse_list(os.getenv(f"{env_prefix}PEERS", "")),
        )
        m.agents.append(agent)

    # service_discovery
    sd = ServiceDiscovery()
    for agent in m.agents:
        port_env = f"{agent.name.upper().replace('-', '_')}_PORT"
        if port_env in os.environ:
            try:
                sd.services[agent.name] = int(os.environ[port_env])
            except ValueError:
                pass
    m.service_discovery = sd

    logger.info("[DomainManifest] built from env: domain=%s, agents=%d", m.domain.name, len(m.agents))
    return m


def _parse_list(value: str) -> List[str]:
    """解析逗号分隔的字符串为空列表"""
    if not value or not value.strip():
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _get_default_port(name: str) -> str:
    """根据 name 返回默认端口"""
    defaults = {
        "health_records": "10010",
        "health_advisor": "10011",
        "medication_reminder": "10012",
        "visit_summary": "10013",
    }
    return defaults.get(name, "10000")


def _apply_env_overrides(manifest: DomainManifest) -> None:
    """用环境变量覆盖 manifest 中的 agent 端口（向后兼容）"""
    for agent in manifest.agents:
        env_key = f"{agent.name.upper().replace('-', '_')}_PORT"
        if env_key in os.environ:
            try:
                agent.port = int(os.environ[env_key])
            except ValueError:
                pass


def load_default() -> DomainManifest:
    """
    阶段48-config: 完全从环境变量构建 manifest（推荐方式）。

    优先级:
      1. PHA_DOMAIN_MANIFEST=env → 从环境变量构建（客户推荐方式）
      2. PHA_DOMAIN_MANIFEST=<yaml文件> → 从 YAML 文件加载（向后兼容）
      3. 默认 pha.health.yaml 存在 → 从 YAML 加载
      4. 完全 fallback 硬编码（最后兜底）

    从环境变量构建时，所有 agent 配置均从 .env 读取，实现"只改 .env 即可部署"。
    """
    env = os.getenv(DEFAULT_MANIFEST_ENV)

    # 模式1: env 模式（阶段48-config 推荐方式）
    if env == "env":
        manifest = _build_manifest_from_env()
        if manifest:
            return manifest
        logger.warning("[DomainManifest] PHA_DOMAIN_MANIFEST=env 但 PHA_DOMAIN 未配置，回退到 YAML 方式")

    # 模式2: 指定 YAML 文件
    if env and env != "env":
        if env.endswith((".yaml", ".yml")):
            path = env if os.path.exists(env) else _MANIFEST_DIR / env
        else:
            path = _MANIFEST_DIR / f"{env}.yaml"
        if Path(path).exists():
            manifest = DomainManifest.from_yaml(path)
            _apply_env_overrides(manifest)
            return manifest
        logger.warning("[DomainManifest] env %s=%s 找不到, 回退", DEFAULT_MANIFEST_ENV, env)

    # 模式3: 默认 YAML
    default = _MANIFEST_DIR / "pha.health.yaml"
    if default.exists():
        manifest = DomainManifest.from_yaml(default)
    else:
        manifest = _hardcoded_pha_manifest()

    _apply_env_overrides(manifest)
    return manifest


def _hardcoded_pha_manifest() -> DomainManifest:
    """兼容 fallback: 没 yaml 时用硬编码 PHA 默认 4 agent (向后兼容 stage 48-19 之前)."""
    m = DomainManifest()
    m.source_path = "<hardcoded>"
    m.domain = DomainConfig(name="pha_legacy", display_name="PHA 默认 (legacy)")
    m.agents = [
        # 阶段48-A2A: health_advisor 可以调用所有 peer
        # 端口对应 docker-compose:
        #   health_advisor=10011, health_records=10010, medication_reminder=10012, visit_summary=10013
        AgentSpec(name="health_advisor", display_name="健康顾问",
                  keywords=["头疼", "发烧", "症状", "blood 血压 血糖"],
                  tools_module="health_advisor", phacore_modules=["ocr"],
                  aliases=["健康顾问"], port=10011,
                  peers=["health_records", "medication_reminder", "visit_summary"]),
        AgentSpec(name="health_records", display_name="健康档案管理员",
                  keywords=["档案", "体检", "报告"],
                  tools_module="health_records", phacore_modules=["ocr"],
                  aliases=["健康档案管理员"], port=10010,
                  peers=["health_advisor", "medication_reminder"]),
        AgentSpec(name="medication_reminder", display_name="用药提醒助手",
                  keywords=["药", "提醒", "medication"],
                  tools_module="medication_reminder", phacore_modules=["ocr"],
                  aliases=["用药提醒助手"], dangerously=True, port=10012,
                  peers=["health_advisor", "health_records"]),
        AgentSpec(name="visit_summary", display_name="就诊摘要生成器",
                  keywords=["摘要", "总结", "就诊"],
                  tools_module="visit_summary", phacore_modules=[],
                  aliases=["就诊摘要"], port=10013,
                  peers=["health_advisor", "health_records"]),
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
