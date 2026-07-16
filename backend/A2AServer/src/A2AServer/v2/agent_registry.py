"""
PHA v2 AgentRegistry - 阶段31 自动注册机制

**目标**：新增/删除一个 sub-agent **只改 1 个文件**（sub_agents.py），
其他模块（host_graph / monitoring_endpoints / bridge）**自动适配**。

**使用方式**：

```python
# sub_agents.py
from .agent_registry import register_agent, AgentRegistry

@register_agent(
    name="health_advisor",
    description="AI 问诊、健康教育、症状分析",
    keywords=["头疼", "发烧", "症状", "建议"],
    tools_module="health_advisor",
    aliases=["健康顾问"],
)
class HealthAdvisorV2(V2Agent):
    system_prompt = "..."
```

```python
# 其他文件
from .agent_registry import AgentRegistry

# 列出所有已注册 agent
for agent in AgentRegistry.list():
    print(agent.name, agent.description, agent.keywords)

# 按 name 获取
agent = AgentRegistry.get("health_advisor")
node = agent.node_name  # "invoke_health_advisor"
class_ref = agent.cls  # HealthAdvisorV2
```
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Type, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class AgentSpec:
    """Agent 注册信息（装饰器注入）"""

    name: str                                          # "health_advisor"
    description: str = ""                              # "AI 问诊..."
    keywords: List[str] = field(default_factory=list)  # 关键词路由
    tools_module: Optional[str] = None                 # "health_advisor"
    aliases: List[str] = field(default_factory=list)   # ["健康顾问"]
    enabled: bool = True                               # 灰度开关

    # 运行时填充
    cls: Optional[Type] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not self.name:
            raise ValueError("AgentSpec.name 不能为空")

    @property
    def node_name(self) -> str:
        """LangGraph 节点名（必须以 invoke_ 开头才能识别为 invoke agent 节点）"""
        return f"invoke_{self.name}"

    @property
    def class_name(self) -> str:
        return self.cls.__name__ if self.cls else "?"


class AgentRegistry:
    """
    全局 Agent 注册表（单例）

    使用方式：
    - 装饰器：@register_agent(...) 注册
    - 查询：AgentRegistry.get(name) / AgentRegistry.list()
    - 动态启停：AgentRegistry.enable(name, False) / AgentRegistry.remove(name)
    """

    _agents: Dict[str, AgentSpec] = {}
    _loaded: bool = False

    @classmethod
    def register(cls, spec: AgentSpec, agent_cls: Type) -> AgentSpec:
        """注册一个 agent（由装饰器调用）"""
        if spec.name in cls._agents:
            logger.warning(
                "[agent_registry] agent '%s' already registered, overwriting",
                spec.name,
            )
        spec.cls = agent_cls
        cls._agents[spec.name] = spec
        logger.info(
            "[agent_registry] registered '%s' (%s) keywords=%d",
            spec.name,
            spec.class_name,
            len(spec.keywords),
        )
        return spec

    @classmethod
    def get(cls, name: str) -> Optional[AgentSpec]:
        """按 name 获取"""
        return cls._agents.get(name)

    @classmethod
    def list(cls, enabled_only: bool = True) -> List[AgentSpec]:
        """列出所有 agent"""
        all_agents = list(cls._agents.values())
        if enabled_only:
            all_agents = [a for a in all_agents if a.enabled]
        return all_agents

    @classmethod
    def names(cls, enabled_only: bool = True) -> List[str]:
        """列出所有 agent name"""
        return [a.name for a in cls.list(enabled_only)]

    @classmethod
    def enable(cls, name: str, enabled: bool = True):
        """启用/禁用一个 agent"""
        if name in cls._agents:
            cls._agents[name].enabled = enabled
            logger.info("[agent_registry] %s %s", name, "enabled" if enabled else "disabled")

    @classmethod
    def remove(cls, name: str):
        """移除一个 agent"""
        if name in cls._agents:
            del cls._agents[name]
            logger.info("[agent_registry] removed %s", name)

    @classmethod
    def by_class(cls, agent_cls: Type) -> Optional[AgentSpec]:
        """按 Class 反查 spec"""
        for spec in cls._agents.values():
            if spec.cls is agent_cls:
                return spec
        return None

    @classmethod
    def by_alias(cls, alias: str) -> Optional[AgentSpec]:
        """按 alias 查找"""
        for spec in cls._agents.values():
            if alias in spec.aliases:
                return spec
        return None

    @classmethod
    def clear(cls):
        """清空（仅测试用）"""
        cls._agents.clear()

    @classmethod
    def stats(cls) -> dict:
        return {
            "total": len(cls._agents),
            "enabled": len(cls.list(enabled_only=True)),
            "disabled": len(cls.list(enabled_only=False)) - len(cls.list(enabled_only=True)),
            "names": cls.names(),
        }


def register_agent(
    name: str,
    description: str = "",
    keywords: Optional[List[str]] = None,
    tools_module: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    enabled: bool = True,
):
    """
    Agent 注册装饰器

    Args:
        name: agent 标识（如 "health_advisor"），全局唯一
        description: 描述（用于前端展示 / debugging）
        keywords: 关键词（用于 host_graph layer2 启发式路由）
        tools_module: MCP 工具模块名（用于 mcp_discover / load_mcp_tools）
        aliases: 中文/英文别名（兼容 v1 的 metadata.selected_agent）
        enabled: 是否启用（False 时不参与路由和并行）

    Example:
        @register_agent(
            name="health_advisor",
            description="AI 问诊、健康教育、症状分析",
            keywords=["头疼", "发烧", "症状", "建议", "health", "symptom"],
            tools_module="health_advisor",
            aliases=["健康顾问"],
        )
        class HealthAdvisorV2(V2Agent):
            system_prompt = "..."
    """
    def decorator(cls):
        spec = AgentSpec(
            name=name,
            description=description,
            keywords=keywords or [],
            tools_module=tools_module,
            aliases=aliases or [],
            enabled=enabled,
        )
        return AgentRegistry.register(spec, cls)
    return decorator


# ============================================================
# 自动发现
# ============================================================
def discover_agents(force: bool = False) -> List[AgentSpec]:
    """
    自动发现所有已注册的 agent

    通过 import sub_agents 触发 @register_agent 装饰器执行
    """
    if AgentRegistry._loaded and not force:
        return AgentRegistry.list()

    try:
        # import 触发所有 @register_agent 装饰器
        from . import sub_agents  # noqa: F401
    except ImportError as e:
        logger.warning("[agent_registry] failed to import sub_agents: %s", e)

    AgentRegistry._loaded = True
    agents = AgentRegistry.list()
    logger.info(
        "[agent_registry] discovered %d agents: %s",
        len(agents),
        [a.name for a in agents],
    )
    return agents


# 兼容导出
__all__ = [
    "AgentSpec",
    "AgentRegistry",
    "register_agent",
    "discover_agents",
]