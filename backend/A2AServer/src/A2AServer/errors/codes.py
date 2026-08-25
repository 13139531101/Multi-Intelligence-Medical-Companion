# -*- coding: utf-8 -*-
"""
PHA v2 错误码定义（阶段48-ops）
所有错误码采用 HTTP 状态码 + 6位业务码的组合。

格式：ERR-{category}-{code}
  category: 3字母分类（见下方）
  code: 3位数字

HTTP 状态码映射：
  400 - 请求参数错误
  401 - 未认证
  403 - 无权限
  404 - 资源不存在
  429 - 请求过于频繁
  500 - 服务器内部错误
  502 - 上游服务不可用
  503 - 服务不可用（降级）

使用方式：
    from A2AServer.errors import PHAError, ErrCode
    raise PHAError(ErrCode.AGENT_NOT_FOUND, agent_name="health_advisor")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 错误分类
# ============================================================

class ErrCategory(str, Enum):
    SYS = "SYS"    # 系统级错误
    AGENT = "AGT"  # Agent 相关
    MCP = "MCP"    # MCP 工具调用
    A2A = "A2A"   # A2A 网络调用
    DB = "DB"      # 数据库错误
    AUTH = "AUTH"  # 认证/授权错误
    LLM = "LLM"    # LLM 调用错误
    VAL = "VAL"    # 参数校验错误


# ============================================================
# 错误码定义表
# ============================================================

class ErrCode(str, Enum):
    # ---- SYS (1xx) ----
    SYS_INTERNAL = "ERR-SYS-001"  # 服务器内部错误
    SYS_NOT_IMPLEMENTED = "ERR-SYS-002"  # 功能未实现
    SYS_TIMEOUT = "ERR-SYS-003"  # 操作超时
    SYS_UNAVAILABLE = "ERR-SYS-004"  # 服务不可用
    SYS_CONFIG_MISSING = "ERR-SYS-005"  # 缺少配置

    # ---- AGENT (1xx) ----
    AGENT_NOT_FOUND = "ERR-AGT-101"  # Agent 不存在
    AGENT_NOT_READY = "ERR-AGT-102"  # Agent 未就绪
    AGENT_TIMEOUT = "ERR-AGT-103"  # Agent 处理超时
    AGENT_NO_CAPABILITY = "ERR-AGT-104"  # Agent 不支持该能力
    AGENT_ROUTING_FAILED = "ERR-AGT-105"  # 无法路由到合适的 Agent

    # ---- A2A (2xx) ----
    A2A_SEND_FAILED = "ERR-A2A-201"  # 发送消息失败
    A2A_PEER_UNREACHABLE = "ERR-A2A-202"  # 无法连接目标 Agent
    A2A_INVALID_MESSAGE = "ERR-A2A-203"  # 消息格式错误
    A2A_SIGNATURE_INVALID = "ERR-A2A-204"  # DID 签名验证失败
    A2A_DID_NOT_FOUND = "ERR-A2A-205"  # DID 无法解析
    A2A_CALL_NOT_ALLOWED = "ERR-A2A-206"  # 跨 Agent 调用被信任边界拒绝

    # ---- MCP (3xx) ----
    MCP_TOOL_NOT_FOUND = "ERR-MCP-301"  # MCP 工具不存在
    MCP_TOOL_EXEC_FAILED = "ERR-MCP-302"  # MCP 工具执行失败
    MCP_SERVER_UNAVAILABLE = "ERR-MCP-303"  # MCP 服务器不可用
    MCP_TIMEOUT = "ERR-MCP-304"  # MCP 调用超时
    MCP_TRANSPORT_ERROR = "ERR-MCP-305"  # MCP 传输层错误

    # ---- DB (4xx) ----
    DB_CONNECTION_FAILED = "ERR-DB-401"  # 数据库连接失败
    DB_QUERY_FAILED = "ERR-DB-402"  # 数据库查询失败
    DB_TRANSACTION_FAILED = "ERR-DB-403"  # 事务执行失败
    DB_RECORD_NOT_FOUND = "ERR-DB-404"  # 记录不存在
    DB_DUPLICATE_KEY = "ERR-DB-405"  # 唯一键冲突

    # ---- AUTH (5xx) ----
    AUTH_TOKEN_INVALID = "ERR-AUTH-501"  # Token 无效或过期
    AUTH_PERMISSION_DENIED = "ERR-AUTH-502"  # 权限不足
    AUTH_RATE_LIMITED = "ERR-AUTH-503"  # 请求频率超限

    # ---- LLM (6xx) ----
    LLM_API_ERROR = "ERR-LLM-601"  # LLM API 调用失败
    LLM_TIMEOUT = "ERR-LLM-602"  # LLM 调用超时
    LLM_QUOTA_EXCEEDED = "ERR-LLM-603"  # LLM API 配额用尽
    LLM_MODEL_NOT_FOUND = "ERR-LLM-604"  # 请求的模型不存在

    # ---- VAL (7xx) ----
    VAL_MISSING_FIELD = "ERR-VAL-701"  # 缺少必需字段
    VAL_INVALID_FORMAT = "ERR-VAL-702"  # 字段格式错误
    VAL_OUT_OF_RANGE = "ERR-VAL-703"  # 值超出允许范围
    VAL_UNSUPPORTED_VALUE = "ERR-VAL-704"  # 不支持的值


# ============================================================
# HTTP 状态码映射
# ============================================================

_HTTP_STATUS_MAP: Dict[ErrCode, int] = {
    # SYS
    ErrCode.SYS_INTERNAL: 500,
    ErrCode.SYS_NOT_IMPLEMENTED: 501,
    ErrCode.SYS_TIMEOUT: 504,
    ErrCode.SYS_UNAVAILABLE: 503,
    ErrCode.SYS_CONFIG_MISSING: 500,
    # AGENT
    ErrCode.AGENT_NOT_FOUND: 404,
    ErrCode.AGENT_NOT_READY: 503,
    ErrCode.AGENT_TIMEOUT: 504,
    ErrCode.AGENT_NO_CAPABILITY: 501,
    ErrCode.AGENT_ROUTING_FAILED: 400,
    # A2A
    ErrCode.A2A_SEND_FAILED: 502,
    ErrCode.A2A_PEER_UNREACHABLE: 503,
    ErrCode.A2A_INVALID_MESSAGE: 400,
    ErrCode.A2A_SIGNATURE_INVALID: 401,
    ErrCode.A2A_DID_NOT_FOUND: 404,
    ErrCode.A2A_CALL_NOT_ALLOWED: 403,
    # MCP
    ErrCode.MCP_TOOL_NOT_FOUND: 404,
    ErrCode.MCP_TOOL_EXEC_FAILED: 500,
    ErrCode.MCP_SERVER_UNAVAILABLE: 503,
    ErrCode.MCP_TIMEOUT: 504,
    ErrCode.MCP_TRANSPORT_ERROR: 502,
    # DB
    ErrCode.DB_CONNECTION_FAILED: 503,
    ErrCode.DB_QUERY_FAILED: 500,
    ErrCode.DB_TRANSACTION_FAILED: 500,
    ErrCode.DB_RECORD_NOT_FOUND: 404,
    ErrCode.DB_DUPLICATE_KEY: 409,
    # AUTH
    ErrCode.AUTH_TOKEN_INVALID: 401,
    ErrCode.AUTH_PERMISSION_DENIED: 403,
    ErrCode.AUTH_RATE_LIMITED: 429,
    # LLM
    ErrCode.LLM_API_ERROR: 502,
    ErrCode.LLM_TIMEOUT: 504,
    ErrCode.LLM_QUOTA_EXCEEDED: 429,
    ErrCode.LLM_MODEL_NOT_FOUND: 404,
    # VAL
    ErrCode.VAL_MISSING_FIELD: 400,
    ErrCode.VAL_INVALID_FORMAT: 400,
    ErrCode.VAL_OUT_OF_RANGE: 400,
    ErrCode.VAL_UNSUPPORTED_VALUE: 400,
}


def get_http_status(code: ErrCode) -> int:
    return _HTTP_STATUS_MAP.get(code, 500)


# ============================================================
# 错误消息模板（支持 i18n）
# ============================================================

_ERROR_MESSAGES: Dict[ErrCode, Dict[str, str]] = {
    ErrCode.AGENT_NOT_FOUND: {
        "en": "Agent not found: {agent_name}",
        "zh": "Agent 不存在：{agent_name}",
    },
    ErrCode.AGENT_NOT_READY: {
        "en": "Agent not ready: {agent_name}",
        "zh": "Agent 未就绪：{agent_name}",
    },
    ErrCode.A2A_PEER_UNREACHABLE: {
        "en": "Cannot reach peer agent: {callee}",
        "zh": "无法连接目标 Agent：{callee}",
    },
    ErrCode.A2A_CALL_NOT_ALLOWED: {
        "en": "Call not allowed: {caller} cannot call {callee}",
        "zh": "调用被拒绝：{caller} 无权调用 {callee}",
    },
    ErrCode.MCP_TOOL_NOT_FOUND: {
        "en": "MCP tool not found: {tool_name}",
        "zh": "MCP 工具不存在：{tool_name}",
    },
    ErrCode.MCP_TIMEOUT: {
        "en": "MCP tool call timeout after {timeout}s",
        "zh": "MCP 工具调用超时（{timeout}秒）",
    },
    ErrCode.DB_RECORD_NOT_FOUND: {
        "en": "Record not found: {table}.{id}",
        "zh": "记录不存在：{table}（id={id}）",
    },
    ErrCode.AUTH_TOKEN_INVALID: {
        "en": "Authentication failed: token invalid or expired",
        "zh": "认证失败：Token 无效或已过期",
    },
    ErrCode.LLM_TIMEOUT: {
        "en": "LLM call timeout after {timeout}s",
        "zh": "LLM 调用超时（{timeout}秒）",
    },
}


def get_message(code: ErrCode, lang: str = "zh", **kwargs: Any) -> str:
    """
    获取错误消息，支持 i18n 和模板变量替换。
    """
    templates = _ERROR_MESSAGES.get(code, {})
    template = templates.get(lang, templates.get("en", str(code.value)))
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


# ============================================================
# PHAError 异常类
# ============================================================

@dataclass
class PHAError(Exception):
    """
    PHA 统一异常类型。

    Attributes:
        code: 错误码（ErrCode 枚举）
        message: 错误消息（自动从 i18n 模板生成，或传入自定义消息）
        details: 附加上下文（agent_name、tool_name 等）
        lang: i18n 语言（zh / en）
    """
    code: ErrCode
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    lang: str = "zh"

    def __post_init__(self) -> None:
        if self.message is None:
            self.message = get_message(self.code, self.lang, **self.details)
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        return get_http_status(self.code)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            }
        }


# ============================================================
# 便捷构造函数
# ============================================================

def agent_not_found(agent_name: str, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.AGENT_NOT_FOUND, details={"agent_name": agent_name}, lang=lang)


def a2a_peer_unreachable(callee: str, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.A2A_PEER_UNREACHABLE, details={"callee": callee}, lang=lang)


def a2a_call_not_allowed(caller: str, callee: str, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.A2A_CALL_NOT_ALLOWED, details={"caller": caller, "callee": callee}, lang=lang)


def mcp_tool_not_found(tool_name: str, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.MCP_TOOL_NOT_FOUND, details={"tool_name": tool_name}, lang=lang)


def mcp_timeout(tool_name: str, timeout: float, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.MCP_TIMEOUT, details={"tool_name": tool_name, "timeout": timeout}, lang=lang)


def db_record_not_found(table: str, record_id: str, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.DB_RECORD_NOT_FOUND, details={"table": table, "id": record_id}, lang=lang)


def llm_timeout(timeout: float, lang: str = "zh") -> PHAError:
    return PHAError(ErrCode.LLM_TIMEOUT, details={"timeout": timeout}, lang=lang)


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
