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


@router.post("/metrics/reset")
async def v2_metrics_reset():
    """重置指标（仅用于测试）"""
    from .monitoring import reset_metrics
    reset_metrics()
    return {"status": "reset", "metrics": get_metrics()}
