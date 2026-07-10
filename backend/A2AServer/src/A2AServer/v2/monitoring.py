"""
PHA v2 监控模块（阶段14）

**作用**：收集 v2 运行时关键指标
- 工具调用缓存命中率
- V2Agent 单例复用次数
- 端到端延迟分位数
- LLM API 错误率

**暴露方式**：
1. 函数 API：`get_metrics()` 返回 dict
2. HTTP endpoint：`GET /metrics` (Prometheus 格式)
3. 日志：定期打印
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# 指标收集
# ============================================================
_metrics = {
    "tool_cache_hits": 0,
    "tool_cache_misses": 0,
    "tool_cache_skips": 0,  # 写操作跳过缓存
    "agent_singleton_reuse": 0,
    "agent_new_creation": 0,
    "request_count": 0,
    "request_latencies": [],  # 滚动窗口 1000
    "request_errors": 0,
    "llm_api_calls": 0,
    "llm_api_errors": 0,
    "started_at": time.time(),
}

MAX_LATENCY_WINDOW = 1000


def record_tool_cache_hit():
    _metrics["tool_cache_hits"] += 1


def record_tool_cache_miss():
    _metrics["tool_cache_misses"] += 1


def record_tool_cache_skip():
    _metrics["tool_cache_skips"] += 1


def record_agent_reuse():
    _metrics["agent_singleton_reuse"] += 1


def record_agent_new():
    _metrics["agent_new_creation"] += 1


def record_request(latency_sec: float, error: bool = False):
    _metrics["request_count"] += 1
    if error:
        _metrics["request_errors"] += 1
    _metrics["request_latencies"].append(latency_sec)
    if len(_metrics["request_latencies"]) > MAX_LATENCY_WINDOW:
        _metrics["request_latencies"] = _metrics["request_latencies"][-MAX_LATENCY_WINDOW:]


def record_llm_call(error: bool = False):
    _metrics["llm_api_calls"] += 1
    if error:
        _metrics["llm_api_errors"] += 1


def get_metrics() -> dict:
    """获取当前所有指标"""
    import statistics

    latencies = _metrics["request_latencies"]
    if latencies:
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        p50 = sorted_lat[int(n * 0.5)] if n > 0 else 0
        p95 = sorted_lat[int(n * 0.95)] if n > 0 else 0
        p99 = sorted_lat[int(n * 0.99)] if n > 0 else 0
    else:
        p50 = p95 = p99 = 0

    cache_total = _metrics["tool_cache_hits"] + _metrics["tool_cache_misses"]
    cache_hit_rate = round(_metrics["tool_cache_hits"] / cache_total * 100, 1) if cache_total else 0

    uptime = time.time() - _metrics["started_at"]

    return {
        "uptime_sec": round(uptime, 1),
        "tool_cache": {
            "hits": _metrics["tool_cache_hits"],
            "misses": _metrics["tool_cache_misses"],
            "skips": _metrics["tool_cache_skips"],
            "hit_rate": cache_hit_rate,
        },
        "agent_singleton": {
            "reuse": _metrics["agent_singleton_reuse"],
            "new": _metrics["agent_new_creation"],
            "reuse_rate": round(
                _metrics["agent_singleton_reuse"]
                / max(1, _metrics["agent_singleton_reuse"] + _metrics["agent_new_creation"])
                * 100, 1
            ),
        },
        "requests": {
            "total": _metrics["request_count"],
            "errors": _metrics["request_errors"],
            "error_rate": round(
                _metrics["request_errors"] / max(1, _metrics["request_count"]) * 100, 1
            ),
            "latency_p50": round(p50, 2),
            "latency_p95": round(p95, 2),
            "latency_p99": round(p99, 2),
            "window_size": len(latencies),
        },
        "llm_api": {
            "calls": _metrics["llm_api_calls"],
            "errors": _metrics["llm_api_errors"],
            "error_rate": round(
                _metrics["llm_api_errors"] / max(1, _metrics["llm_api_calls"]) * 100, 1
            ),
        },
    }


def get_prometheus_metrics() -> str:
    """导出 Prometheus 格式指标"""
    m = get_metrics()
    lines = [
        "# HELP pha_tool_cache_hits Tool call cache hits",
        "# TYPE pha_tool_cache_hits counter",
        f"pha_tool_cache_hits {m['tool_cache']['hits']}",
        "",
        "# HELP pha_tool_cache_misses Tool call cache misses",
        "# TYPE pha_tool_cache_misses counter",
        f"pha_tool_cache_misses {m['tool_cache']['misses']}",
        "",
        "# HELP pha_tool_cache_hit_rate Tool call cache hit rate",
        "# TYPE pha_tool_cache_hit_rate gauge",
        f"pha_tool_cache_hit_rate {m['tool_cache']['hit_rate']}",
        "",
        "# HELP pha_request_latency_seconds Request latency percentiles",
        "# TYPE pha_request_latency_seconds gauge",
        f'pha_request_latency_seconds{{quantile="0.5"}} {m["requests"]["latency_p50"]}',
        f'pha_request_latency_seconds{{quantile="0.95"}} {m["requests"]["latency_p95"]}',
        f'pha_request_latency_seconds{{quantile="0.99"}} {m["requests"]["latency_p99"]}',
        "",
        "# HELP pha_request_total Total requests",
        "# TYPE pha_request_total counter",
        f"pha_request_total {m['requests']['total']}",
        "",
        "# HELP pha_request_errors Total request errors",
        "# TYPE pha_request_errors counter",
        f"pha_request_errors {m['requests']['errors']}",
    ]
    return "\n".join(lines)


def reset_metrics():
    """重置所有指标（仅用于测试）"""
    global _metrics
    _metrics = {
        "tool_cache_hits": 0,
        "tool_cache_misses": 0,
        "tool_cache_skips": 0,
        "agent_singleton_reuse": 0,
        "agent_new_creation": 0,
        "request_count": 0,
        "request_latencies": [],
        "request_errors": 0,
        "llm_api_calls": 0,
        "llm_api_errors": 0,
        "started_at": time.time(),
    }


def print_summary():
    """打印人类可读的指标摘要"""
    m = get_metrics()
    print("=" * 60)
    print("PHA v2 监控摘要")
    print("=" * 60)
    print(f"  Uptime: {m['uptime_sec']}s")
    print(f"  Tool Cache: hits={m['tool_cache']['hits']} misses={m['tool_cache']['misses']} skips={m['tool_cache']['skips']} hit_rate={m['tool_cache']['hit_rate']}%")
    print(f"  Agent Singleton: reuse={m['agent_singleton']['reuse']} new={m['agent_singleton']['new']} reuse_rate={m['agent_singleton']['reuse_rate']}%")
    print(f"  Requests: total={m['requests']['total']} errors={m['requests']['errors']} err_rate={m['requests']['error_rate']}%")
    print(f"  Latency P50/P95/P99: {m['requests']['latency_p50']}/{m['requests']['latency_p95']}/{m['requests']['latency_p99']}s")
    print(f"  LLM API: calls={m['llm_api']['calls']} errors={m['llm_api']['errors']} err_rate={m['llm_api']['error_rate']}%")
