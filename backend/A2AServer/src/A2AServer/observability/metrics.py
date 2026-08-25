# -*- coding: utf-8 -*-
"""
PHA v2 可观测性 - Prometheus metrics（阶段48-ops）
所有 agent 共享同一套指标定义，零侵入接入。

使用方式（在服务入口）：
    from A2AServer.observability.metrics import setup_metrics
    setup_metrics("health_advisor")

暴露端点：GET /metrics（prometheus_client 自动格式）
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY,
)

logger = logging.getLogger(__name__)

# 全局注册表（单例）
_metrics_initialized = False
_service_name: Optional[str] = None

# ============================================================
# 1. 业务指标
# ============================================================

# --- 请求计数 ---
REQUEST_TOTAL = Counter(
    "pha_requests_total",
    "Total HTTP/A2A requests",
    ["agent", "method", "status"],
)

# --- 活跃请求 ---
ACTIVE_REQUESTS = Gauge(
    "pha_active_requests",
    "Currently active requests",
    ["agent"],
)

# --- 请求延迟 ---
REQUEST_LATENCY = Histogram(
    "pha_request_latency_seconds",
    "Request latency in seconds",
    ["agent", "method"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# --- LLM 调用计数 ---
LLM_CALLS_TOTAL = Counter(
    "pha_llm_calls_total",
    "Total LLM API calls",
    ["agent", "model", "status"],
)

# --- LLM 延迟 ---
LLM_LATENCY = Histogram(
    "pha_llm_latency_seconds",
    "LLM call latency in seconds",
    ["agent", "model"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# --- LLM Token 消耗 ---
LLM_TOKENS = Counter(
    "pha_llm_tokens_total",
    "Total LLM tokens consumed",
    ["agent", "model", "token_type"],
)

# ============================================================
# 2. MCP 工具指标
# ============================================================

MCP_TOOL_CALLS_TOTAL = Counter(
    "pha_mcp_tool_calls_total",
    "Total MCP tool calls",
    ["agent", "tool_name", "status"],
)

MCP_TOOL_LATENCY = Histogram(
    "pha_mcp_tool_latency_seconds",
    "MCP tool call latency in seconds",
    ["agent", "tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ============================================================
# 3. A2A 网络指标
# ============================================================

A2A_RPC_CALLS_TOTAL = Counter(
    "pha_a2a_rpc_calls_total",
    "Total A2A/ANP RPC calls",
    ["caller", "callee", "method", "status"],
)

A2A_RPC_LATENCY = Histogram(
    "pha_a2a_rpc_latency_seconds",
    "A2A/ANP RPC call latency in seconds",
    ["caller", "callee", "method"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

A2A_RPC_ERRORS = Counter(
    "pha_a2a_rpc_errors_total",
    "Total A2A/ANP RPC errors",
    ["caller", "callee", "method", "error_type"],
)

# ============================================================
# 4. 数据库指标
# ============================================================

DB_QUERY_LATENCY = Histogram(
    "pha_db_query_latency_seconds",
    "Database query latency in seconds",
    ["agent", "operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

DB_QUERY_ERRORS = Counter(
    "pha_db_query_errors_total",
    "Database query errors",
    ["agent", "operation"],
)

# ============================================================
# 5. Agent 特有指标
# ============================================================

CONVERSATION_ACTIVE = Gauge(
    "pha_active_conversations",
    "Currently active conversation sessions",
    ["agent"],
)

AGENT_TOOL_INVOCATION = Counter(
    "pha_agent_tool_invocations_total",
    "Total tool invocations by agent",
    ["agent", "tool_name", "result"],
)


# ============================================================
# 6. 基础设施指标
# ============================================================

AGENT_INFO = Info(
    "pha_agent",
    "PHA agent information",
)


# ============================================================
# 公共工具函数
# ============================================================

class LatencyTracker:
    """上下文管理器：自动记录 Histogram + Gauge"""

    def __init__(
        self,
        latency_hist: Histogram,
        labels: dict,
        gauge: Optional[Gauge] = None,
        gauge_labels: Optional[dict] = None,
    ):
        self.hist = latency_hist
        self.labels = labels
        self.gauge = gauge
        self.gauge_labels = gauge_labels if gauge_labels is not None else labels
        self._start: Optional[float] = None

    def __enter__(self):
        self._start = time.perf_counter()
        if self.gauge:
            self.gauge.labels(**self.gauge_labels).inc()
        return self

    def __exit__(self, *args):
        elapsed = time.perf_counter() - self._start
        self.hist.labels(**self.labels).observe(elapsed)
        if self.gauge:
            self.gauge.labels(**self.gauge_labels).dec()


def setup_metrics(service_name: str, registry: CollectorRegistry = REGISTRY) -> None:
    """
    初始化 metrics（每个服务只调一次）。
    自动暴露 /metrics 端点（FastAPI/Starlette 路由需手动注册）。
    """
    global _metrics_initialized, _service_name
    if _metrics_initialized:
        return
    _metrics_initialized = True
    _service_name = service_name

    AGENT_INFO.info({
        "service": service_name,
        "version": "v2.0-stage48",
    })
    logger.info("[metrics] Prometheus metrics initialized for agent=%s", service_name)


def get_metrics_bytes() -> bytes:
    """生成 /metrics 端点的响应体（prometheus 采集格式）"""
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
