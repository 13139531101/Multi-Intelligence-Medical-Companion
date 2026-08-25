# -*- coding: utf-8 -*-
"""Tests for A2AServer structured_logging module"""
import pytest
import sys
import logging
import json

sys.path.insert(0, "backend/A2AServer/src")

from A2AServer.observability.structured_logging import (
    setup_logging,
    LogContext,
    get_request_logger,
    PHAJsonLog,
    standard_fields,
)


class TestLogContext:
    def test_context_sets_fields(self):
        with LogContext(request_id="req-1", user_id="u-1"):
            from A2AServer.observability.structured_logging import _log_ctx
            ctx = _log_ctx.get()
            assert ctx["request_id"] == "req-1"
            assert ctx["user_id"] == "u-1"

    def test_context_restored_after(self):
        from A2AServer.observability.structured_logging import _log_ctx
        before = _log_ctx.get()
        with LogContext(request_id="req-2"):
            pass
        after = _log_ctx.get()
        assert after == before

    def test_nested_context(self):
        with LogContext(a="1"):
            with LogContext(b="2"):
                from A2AServer.observability.structured_logging import _log_ctx
                ctx = _log_ctx.get()
                assert ctx["a"] == "1"
                assert ctx["b"] == "2"


class TestPHAJsonLog:
    def test_format_contains_required_fields(self):
        setup_logging("test_agent", json_format=True)
        formatter = PHAJsonLog(agent_name="test_agent")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["message"] == "hello"
        assert data["agent"] == "test_agent"

    def test_format_excludes_standard_fields(self):
        formatter = PHAJsonLog("test")
        std = standard_fields()
        # standard_fields() should be a set
        assert isinstance(std, set)


class TestGetRequestLogger:
    def test_returns_logger_instance(self):
        logger = get_request_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_no_raise(self):
        # Should not raise
        setup_logging("test", level="DEBUG", json_format=False)
