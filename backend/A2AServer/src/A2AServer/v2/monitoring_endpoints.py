"""
PHA v2 监控 HTTP 端点（阶段14）

**作用**：暴露 /health 和 /metrics 端点供 K8s 探针和 Prometheus 抓取

**端点**：
- GET /health           - 简单存活探针（返回 200 if alive）
- GET /health/deep      - 深度健康检查（含 LLM API 连通性）
- GET /metrics          - Prometheus 文本格式
- GET /v2/metrics/json  - JSON 格式（方便调试）
- GET /v2/status        - 详细状态（含缓存、限流、单例）

**集成方式**：在 hostapi 中 import 并 mount router：
```python
from A2AServer.v2.monitoring_endpoints import router as v2_monitor_router
app.include_router(v2_monitor_router)
```

**用途**：
- K8s liveness probe: GET /health
- K8s readiness probe: GET /health/deep
- Prometheus scrape: GET /metrics
- 运维调试: GET /v2/status
"""
from __future__ import annotations

import logging
import time
import json

from fastapi import APIRouter, Response

from .monitoring import (
    get_metrics,
    get_prometheus_metrics,
    print_summary,
)
from .rate_limit import get_rate_limiter
from .tool_cache import get_tool_cache

# v2_agent 仅在 /v2/status 端点里用，懒加载（避免未装 langchain 时模块加载失败）
def _get_v2_agent_singleton_keys():
    try:
        from .v2_agent import V2Agent
        return list(V2Agent._agent_instance_cache.keys())
    except Exception:
        return []

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["v2-monitoring"])


# ============================================================
# 兼容 K8s 探针（不带 /v2 前缀）
# ============================================================
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health():
    """简单存活探针（K8s liveness probe）"""
    return {"status": "ok", "ts": time.time()}


@health_router.get("/health/deep")
async def health_deep():
    """
    深度健康检查（K8s readiness probe）
    检查 LLM API 连通性
    """
    checks = {
        "v2_runtime": "unknown",
        "tool_cache": "unknown",
        "rate_limiter": "unknown",
    }
    overall_ok = True

    # 1. v2 运行时
    try:
        from .v2_runtime import get_runtime
        runtime = get_runtime()
        checks["v2_runtime"] = "ok" if runtime.available else "degraded"
    except Exception as e:
        checks["v2_runtime"] = f"error: {e}"
        overall_ok = False

    # 2. 工具调用缓存
    try:
        cache = get_tool_cache()
        s = cache.stats()
        checks["tool_cache"] = "ok"
        checks["tool_cache_size"] = s["size"]
    except Exception as e:
        checks["tool_cache"] = f"error: {e}"
        overall_ok = False

    # 3. 限流器
    try:
        limiter = get_rate_limiter()
        s = limiter.stats()
        checks["rate_limiter"] = "ok"
        checks["llm_allowed"] = s["llm_allowed"]
        checks["llm_denied"] = s["llm_denied"]
    except Exception as e:
        checks["rate_limiter"] = f"error: {e}"
        overall_ok = False

    status_code = 200 if overall_ok else 503
    payload = {
        "status": "ok" if overall_ok else "degraded",
        "checks": checks,
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


# ============================================================
# Prometheus 端点
# ============================================================
def _prometheus_response():
    return Response(
        content=get_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

health_router.add_api_route(
    "/metrics",
    _prometheus_response,
    methods=["GET"],
    tags=["metrics"],
)


# ============================================================
# v2 详细状态（JSON）
# ============================================================
@router.get("/status")
async def v2_status():
    """v2 详细状态（JSON，方便调试）"""
    return {
        "metrics": get_metrics(),
        "tool_cache": get_tool_cache().stats(),
        "rate_limiter": get_rate_limiter().stats(),
        "agent_singleton_classes": _get_v2_agent_singleton_keys(),
    }


@router.get("/agents/status")
async def v2_agents_status():
    """
    阶段30新增：每个 subagent 的运行状态

    返回每个 agent 的：
    - 是否已实例化（singleton）
    - 加载的工具数
    - 模型
    - 创建时间 / 最后调用时间
    - 累计调用次数 / 累计 token 数（如可统计）

    阶段31：自动从 AgentRegistry 发现所有 agent（无需 hardcode）
    """
    from .v2_agent import V2Agent
    from .agent_registry import discover_agents

    # 阶段31：从 registry 自动获取所有 agent（不 hardcode 4 个 class）
    specs = discover_agents()
    agent_class_map = {spec.name: spec.cls for spec in specs}

    agents = {}
    # 阶段30：cache_key 是 (V2Agent 子类, model)
    for cache_key in V2Agent._agent_instance_cache.keys():
        if isinstance(cache_key, tuple) and len(cache_key) == 2:
            sub_cls, model = cache_key
        else:
            sub_cls, model = None, "unknown"

        # 通过类名映射出 agent_name（阶段31 改为查 registry）
        agent_name = None
        for n, cls in agent_class_map.items():
            if cls is sub_cls:
                agent_name = n
                break
        if agent_name is None:
            agent_name = getattr(sub_cls, "__name__", str(cache_key))

        # 创建临时实例拿元数据（触发 _agent 构建拿 tools）
        try:
            tmp = sub_cls()
            tmp_tools_count = len(getattr(tmp, "_tools", []) or [])
            tmp_prompt_chars = len(getattr(tmp, "system_prompt", "") or "")
            tmp_system_prompt_preview = (getattr(tmp, "system_prompt", "") or "")[:200]

            # 如果 _tools 还是空，从 mcp_discover 查
            if tmp_tools_count == 0:
                try:
                    from .mcp_discover import discover_mcp_tools_static
                    discovered = discover_mcp_tools_static(agent_name)
                    tmp_tools_count = len(discovered)
                except Exception:
                    pass
        except Exception as e:
            tmp_tools_count = -1
            tmp_prompt_chars = -1
            tmp_system_prompt_preview = f"<error: {e}>"

        agents[agent_name] = {
            "name": agent_name,
            "model": model,
            "tools_count": tmp_tools_count,
            "system_prompt_chars": tmp_prompt_chars,
            "system_prompt_preview": tmp_system_prompt_preview,
            "is_loaded": True,
            "class": getattr(sub_cls, "__name__", "?"),
            "cached": True,
        }

    # 从 monitoring.metrics 拿 cumulative 调用数
    metrics = get_metrics()
    agent_singleton_metrics = metrics.get("agent_singleton", {})

    # 阶段31：增加 registry 状态（哪些已注册但未加载）
    registry_specs = [
        {
            "name": s.name,
            "description": s.description,
            "keywords": s.keywords,
            "tools_module": s.tools_module,
            "aliases": s.aliases,
            "enabled": s.enabled,
            "node_name": s.node_name,
            "class": s.class_name,
            "is_loaded": s.name in agents,
        }
        for s in specs
    ]

    return {
        "agents": agents,
        "registry": registry_specs,
        "registry_stats": {
            "total": len(specs),
            "loaded": len(agents),
            "unloaded": len(specs) - len(agents),
        },
        "cache_size": len(V2Agent._agent_instance_cache),
        "metrics": {
            "agent_singleton_new": agent_singleton_metrics.get("new", 0),
            "agent_singleton_reuse": agent_singleton_metrics.get("reuse", 0),
            "agent_singleton_reuse_rate": agent_singleton_metrics.get("reuse_rate", 0),
        },
        "ts": time.time(),
    }


@router.get("/agents/{agent_name}/status")
async def v2_agent_status(agent_name: str):
    """
    阶段30新增：单个 subagent 的详细状态

    Args:
        agent_name: agent_name（health_advisor / health_records / medication_reminder / visit_summary 等）

    阶段31：自动从 AgentRegistry 发现
    """
    from .v2_agent import V2Agent
    from .agent_registry import AgentRegistry

    spec = AgentRegistry.get(agent_name)
    if spec is None:
        return {
            "agent": agent_name,
            "error": "unknown agent name",
            "known_agents": AgentRegistry.names(),
        }
    sub_cls = spec.cls

    # 找 cache
    is_loaded = False
    model = None
    for cache_key in V2Agent._agent_instance_cache.keys():
        if isinstance(cache_key, tuple) and len(cache_key) == 2 and cache_key[0] is sub_cls:
            is_loaded = True
            model = cache_key[1]
            break

    # 创建临时实例拿元数据
    try:
        tmp = sub_cls()
        tools_count = len(getattr(tmp, "_tools", []) or [])
        prompt_chars = len(getattr(tmp, "system_prompt", "") or "")
        prompt_preview = (getattr(tmp, "system_prompt", "") or "")[:500]
        tool_names = []
        try:
            tmp._ensure_agent()
            tool_names = [getattr(t, "name", str(t)) for t in (tmp._tools or [])]
        except Exception:
            pass
        # 如果 _tools 仍空，从 mcp_discover 查
        if tools_count == 0:
            try:
                from .mcp_discover import discover_mcp_tools_static
                discovered = discover_mcp_tools_static(agent_name)
                tools_count = len(discovered)
                tool_names = [t.get("name", str(t)) for t in discovered]
            except Exception:
                pass
    except Exception as e:
        tools_count = -1
        prompt_chars = -1
        prompt_preview = f"<error: {e}>"
        tool_names = []

    return {
        "agent": agent_name,
        "description": spec.description,
        "keywords": spec.keywords,
        "aliases": spec.aliases,
        "tools_module": spec.tools_module,
        "is_loaded": is_loaded,
        "model": model,
        "tools_count": tools_count,
        "tool_names": tool_names,
        "system_prompt_chars": prompt_chars,
        "system_prompt_preview": prompt_preview,
        "class": sub_cls.__name__,
    }


@router.get("/metrics/json")
async def v2_metrics_json():
    """v2 指标 JSON 格式"""
    return get_metrics()


@router.get("/summary")
async def v2_summary():
    """v2 人类可读摘要（用于日志/调试）"""
    # 复用 print_summary 但转 string
    import io
    import contextlib
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        print_summary()
    return {"summary": f.getvalue()}


# ============================================================
# 阶段19：写操作审计端点
# ============================================================
@router.get("/audit/stats")
async def v2_audit_stats():
    """写操作审计统计"""
    from .write_audit import get_write_guard
    return get_write_guard().stats()


@router.get("/audit/recent")
async def v2_audit_recent(limit: int = 50, user_id: str = "", tool_name: str = ""):
    """最近写操作审计记录"""
    from .write_audit import get_write_guard
    return {
        "entries": get_write_guard().get_recent(
            limit=min(limit, 500),
            user_id=user_id or None,
            tool_name=tool_name or None,
        ),
        "count": limit,
    }


@router.post("/metrics/reset")
async def v2_metrics_reset():
    """重置指标（仅用于测试）"""
    from .monitoring import reset_metrics
    reset_metrics()
    return {"status": "reset", "metrics": get_metrics()}


# ============================================================
# 阶段38-3: Alert 端点
# ============================================================

@router.get("/alerts/active")
async def v2_alerts_active():
    """当前触发的报警"""
    from .alerting import get_alert_manager
    mgr = get_alert_manager()
    return {
        "active": mgr.get_active_alerts(),
        "stats": mgr.get_stats(),
    }


@router.get("/alerts/history")
async def v2_alerts_history(limit: int = 50):
    """报警历史"""
    from .alerting import get_alert_manager
    mgr = get_alert_manager()
    return {
        "history": mgr.get_history(limit=limit),
        "stats": mgr.get_stats(),
    }


@router.get("/alerts/rules")
async def v2_alerts_rules():
    """所有报警规则 + 状态"""
    from .alerting import get_alert_manager
    mgr = get_alert_manager()
    return {
        "rules": mgr.list_rules(),
    }


@router.post("/alerts/evaluate")
async def v2_alerts_evaluate():
    """手动触发一次评估（基于当前指标）"""
    from .alerting import get_alert_manager
    mgr = get_alert_manager()
    metrics = get_metrics()
    await mgr.evaluate(metrics)
    return {
        "evaluated": True,
        "active_after": mgr.get_active_alerts(),
        "stats": mgr.get_stats(),
    }


@router.post("/alerts/rule/add")
async def v2_alerts_add_rule(rule: dict):
    """添加自定义报警规则"""
    from .alerting import get_alert_manager, AlertRule, Severity
    mgr = get_alert_manager()
    new_rule = AlertRule(
        name=rule["name"],
        metric_path=rule["metric_path"],
        comparator=rule["comparator"],
        threshold=float(rule["threshold"]),
        severity=Severity(rule.get("severity", "warning")),
        description=rule.get("description", ""),
        enabled=rule.get("enabled", True),
    )
    mgr.add_rule(new_rule)
    return {"status": "added", "rule": new_rule.name}


@router.delete("/alerts/rule/{name}")
async def v2_alerts_remove_rule(name: str):
    """删除报警规则"""
    from .alerting import get_alert_manager
    mgr = get_alert_manager()
    mgr.remove_rule(name)
    return {"status": "removed", "rule": name}
