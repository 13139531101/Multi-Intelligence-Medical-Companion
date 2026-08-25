# -*- coding: utf-8 -*-
"""Tests for A2AServer errors module"""
import pytest
import sys

sys.path.insert(0, "backend/A2AServer/src")

from A2AServer.errors import (
    ErrCode,
    ErrCategory,
    PHAError,
    get_http_status,
    get_message,
    agent_not_found,
    a2a_call_not_allowed,
    mcp_tool_not_found,
    db_record_not_found,
    llm_timeout,
)


class TestErrCode:
    def test_all_codes_have_http_status(self):
        for code in ErrCode:
            status = get_http_status(code)
            assert 100 <= status < 600, f"{code.value} has invalid HTTP status {status}"

    def test_agent_errors_return_404(self):
        assert get_http_status(ErrCode.AGENT_NOT_FOUND) == 404

    def test_auth_errors_return_401(self):
        assert get_http_status(ErrCode.AUTH_TOKEN_INVALID) == 401

    def test_a2a_call_not_allowed_returns_403(self):
        assert get_http_status(ErrCode.A2A_CALL_NOT_ALLOWED) == 403

    def test_rate_limit_returns_429(self):
        assert get_http_status(ErrCode.AUTH_RATE_LIMITED) == 429


class TestPHASError:
    def test_basic_error(self):
        err = PHAError(ErrCode.SYS_INTERNAL, message="test error")
        assert err.code == ErrCode.SYS_INTERNAL
        assert err.http_status == 500
        assert err.message == "test error"

    def test_auto_message_zh(self):
        err = agent_not_found("health_advisor", lang="zh")
        assert "health_advisor" in err.message
        assert err.code == ErrCode.AGENT_NOT_FOUND

    def test_auto_message_en(self):
        err = agent_not_found("health_advisor", lang="en")
        assert "health_advisor" in err.message
        assert "en" in err.message.lower()

    def test_to_dict(self):
        err = db_record_not_found("users", "u-123")
        d = err.to_dict()
        assert "error" in d
        assert d["error"]["code"] == ErrCode.DB_RECORD_NOT_FOUND.value
        assert "users" in d["error"]["message"]

    def test_http_status_from_code(self):
        err = mcp_tool_not_found("fake_tool")
        assert err.http_status == 404


class TestGetMessage:
    def test_template_vars_replaced(self):
        # A2A_CALL_NOT_ALLOWED template has both {caller} and {callee}
        msg = get_message(ErrCode.A2A_CALL_NOT_ALLOWED, lang="zh", caller="ha", callee="mr")
        assert "ha" in msg
        assert "mr" in msg

    def test_fallback_to_english(self):
        msg = get_message(ErrCode.AGENT_NOT_FOUND, lang="unsupported_lang")
        assert "health_advisor" not in msg  # raw template with placeholder
