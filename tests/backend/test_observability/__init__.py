# -*- coding: utf-8 -*-
"""Tests for A2AServer observability metrics module"""
import pytest
import sys

sys.path.insert(0, "backend/A2AServer/src")

from A2AServer.observability.metrics import (
    setup_metrics,
    get_metrics_bytes,
    get_metrics_content_type,
    LatencyTracker,
    REQUEST_TOTAL,
    REQUEST_LATENCY,
    ACTIVE_REQUESTS,
    LLM_CALLS_TOTAL,
    MCP_TOOL_CALLS_TOTAL,
    A2A_RPC_CALLS_TOTAL,
    DB_QUERY_LATENCY,
)


class TestMetricsSetup:
    def test_setup_metrics_twice_noop(self):
        # Should not raise
        setup_metrics("test_agent_1")
        setup_metrics("test_agent_1")  # second call is no-op

    def test_get_metrics_bytes(self):
        setup_metrics("test_agent_bytes")
        data = get_metrics_bytes()
        assert isinstance(data, bytes)
        assert b"pha_agent_info" in data

    def test_get_metrics_content_type(self):
        ct = get_metrics_content_type()
        assert "text/plain" in ct or "openmetrics" in ct


class TestLatencyTracker:
    def test_latency_tracker_records(self):
        setup_metrics("test_tracker")
        with LatencyTracker(REQUEST_LATENCY, {"agent": "test", "method": "GET"}):
            pass  # simulate a fast operation
        # No exception = success

    def test_latency_tracker_with_labels(self):
        tracker = LatencyTracker(
            REQUEST_LATENCY,
            {"agent": "ha", "method": "POST"},
            gauge=ACTIVE_REQUESTS,
            gauge_labels={"agent": "ha"},
        )
        with tracker:
            pass

    def test_latency_tracker_context_manager(self):
        import time
        setup_metrics("test_ctx")
        with LatencyTracker(REQUEST_LATENCY, {"agent": "test", "method": "GET"}):
            time.sleep(0.01)
        # no exception = success


class TestCounterIncrement:
    def test_request_total_increment(self):
        setup_metrics("test_counter")
        before = REQUEST_TOTAL.labels(agent="test", method="GET", status="200")._value.get()
        REQUEST_TOTAL.labels(agent="test", method="GET", status="200").inc()
        after = REQUEST_TOTAL.labels(agent="test", method="GET", status="200")._value.get()
        assert after == before + 1

    def test_llm_calls_total_with_labels(self):
        setup_metrics("test_llm")
        LLM_CALLS_TOTAL.labels(agent="test", model="deepseek", status="ok").inc()

    def test_a2a_rpc_calls_total(self):
        A2A_RPC_CALLS_TOTAL.labels(
            caller="health_advisor",
            callee="medication_reminder",
            method="task/send",
            status="ok",
        ).inc()

    def test_mcp_tool_calls_total(self):
        MCP_TOOL_CALLS_TOTAL.labels(
            agent="health_advisor",
            tool_name="get_medications",
            status="ok",
        ).inc()

    def test_db_query_latency(self):
        import time
        setup_metrics("test_db")
        with LatencyTracker(DB_QUERY_LATENCY, {"agent": "test", "operation": "select"}):
            time.sleep(0.001)
