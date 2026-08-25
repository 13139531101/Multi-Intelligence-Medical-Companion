# -*- coding: utf-8 -*-
"""PHA v2 可观测性模块包"""
from .metrics import (
    setup_metrics,
    get_metrics_bytes,
    get_metrics_content_type,
    LatencyTracker,
    REQUEST_TOTAL,
    REQUEST_LATENCY,
    ACTIVE_REQUESTS,
    LLM_CALLS_TOTAL,
    LLM_LATENCY,
    LLM_TOKENS,
    MCP_TOOL_CALLS_TOTAL,
    MCP_TOOL_LATENCY,
    A2A_RPC_CALLS_TOTAL,
    A2A_RPC_LATENCY,
    A2A_RPC_ERRORS,
    DB_QUERY_LATENCY,
    DB_QUERY_ERRORS,
    CONVERSATION_ACTIVE,
    AGENT_TOOL_INVOCATION,
    AGENT_INFO,
)
from .structured_logging import (
    setup_logging,
    PHAJsonLog,
    LogContext,
)

__all__ = [
    # metrics
    "setup_metrics",
    "get_metrics_bytes",
    "get_metrics_content_type",
    "LatencyTracker",
    "REQUEST_TOTAL",
    "REQUEST_LATENCY",
    "ACTIVE_REQUESTS",
    "LLM_CALLS_TOTAL",
    "LLM_LATENCY",
    "LLM_TOKENS",
    "MCP_TOOL_CALLS_TOTAL",
    "MCP_TOOL_LATENCY",
    "A2A_RPC_CALLS_TOTAL",
    "A2A_RPC_LATENCY",
    "A2A_RPC_ERRORS",
    "DB_QUERY_LATENCY",
    "DB_QUERY_ERRORS",
    "CONVERSATION_ACTIVE",
    "AGENT_TOOL_INVOCATION",
    "AGENT_INFO",
    # logging
    "setup_logging",
    "PHAJsonLog",
    "LogContext",
]
