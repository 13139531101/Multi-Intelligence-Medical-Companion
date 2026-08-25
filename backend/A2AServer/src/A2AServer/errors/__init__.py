# -*- coding: utf-8 -*-
"""PHA v2 错误码模块"""
from .codes import (
    ErrCategory,
    ErrCode,
    PHAError,
    get_http_status,
    get_message,
    agent_not_found,
    a2a_peer_unreachable,
    a2a_call_not_allowed,
    mcp_tool_not_found,
    mcp_timeout,
    db_record_not_found,
    llm_timeout,
)

__all__ = [
    "ErrCategory",
    "ErrCode",
    "PHAError",
    "get_http_status",
    "get_message",
    "agent_not_found",
    "a2a_peer_unreachable",
    "a2a_call_not_allowed",
    "mcp_tool_not_found",
    "mcp_timeout",
    "db_record_not_found",
    "llm_timeout",
]
