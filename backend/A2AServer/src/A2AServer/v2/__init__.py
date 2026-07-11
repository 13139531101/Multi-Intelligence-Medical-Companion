"""PHA v2 智能体运行时层（阶段2 + 阶段3）"""
# 阶段14-部署：v2 包改为懒加载，避免未装 LangChain 1.x 时整个包导入失败
# 这样 monitoring/rate_limit/tool_cache 等基础模块可在不装 langchain 的环境（如 hostapi）中独立使用

__all__ = [
    "V2AgentRuntime",
    "get_runtime",
    "V2Agent",
    "HealthAdvisorV2",
    "HealthRecordsV2",
    "MedicationReminderV2",
    "VisitSummaryV2",
    "build_host_graph",
    "get_host_graph",
    "route_and_invoke",
    "HostState",
    "warmup_v2",
    "warmup_v2_sync",
]


def __getattr__(name):
    """PEP 562 模块级 __getattr__：按需加载子模块"""
    if name in ("V2AgentRuntime", "get_runtime", "warmup_v2", "warmup_v2_sync"):
        from . import v2_runtime
        return getattr(v2_runtime, name)
    if name == "V2Agent":
        from . import v2_agent
        return v2_agent.V2Agent
    if name in ("HealthAdvisorV2", "HealthRecordsV2", "MedicationReminderV2", "VisitSummaryV2"):
        from . import sub_agents
        return getattr(sub_agents, name)
    if name in ("build_host_graph", "get_host_graph", "route_and_invoke", "HostState"):
        from . import host_graph
        return getattr(host_graph, name)
    raise AttributeError(f"module 'A2AServer.v2' has no attribute {name!r}")
