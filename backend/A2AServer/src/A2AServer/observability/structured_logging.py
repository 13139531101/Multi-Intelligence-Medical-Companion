# -*- coding: utf-8 -*-
"""
PHA v2 结构化日志（阶段48-ops）
- JSON 格式日志 → Loki / ELK 采集
- 自动附加 request_id / user_id / agent_name 等上下文
- 与 python-json-logger 兼容

使用方式：
    from A2AServer.observability import setup_logging, LogContext

    # 服务入口
    setup_logging("health_advisor")

    # 请求处理中
    with LogContext(request_id="req-123", user_id="u-456"):
        logger.info("处理请求")
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# context var：自动在每条日志里注入字段
_log_ctx: ContextVar[Dict[str, Any]] = ContextVar("log_ctx", default={})

# 全局初始化标记
_logging_initialized = False


class PHAJsonLog(logging.Formatter):
    """
    JSON formatter：
    {
      "timestamp": "2026-08-23T10:12:00.000Z",
      "level": "INFO",
      "logger": "health_advisor",
      "message": "处理请求",
      "request_id": "req-123",
      "user_id": "u-456",
      "agent": "health_advisor",
      "duration_ms": 45.2,
      ...
    }
    """

    def __init__(self, agent_name: str = "pha"):
        super().__init__()
        self.agent_name = agent_name

    def format(self, record: logging.LogRecord) -> str:
        ctx = _log_ctx.get()

        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
            timespec="milliseconds"
        )

        payload = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "agent": self.agent_name,
            # 附加 context var 里的字段
            **ctx,
            # 标准字段
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # duration_ms：如果 record 里有就加上
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = record.duration_ms

        # exc_info
        if record.exc_text:
            payload["exc_text"] = record.exc_text

        # 追加 record.__dict__ 里的自定义字段（避开标准 logging 字段）
        _extra = {k: v for k, v in record.__dict__.items()
                  if k not in standard_fields()}
        payload.update(_extra)

        return json.dumps(payload, ensure_ascii=False, default=str)


def standard_fields() -> set:
    return {
        "name", "msg", "args", "created", "filename", "funcName", "levelname",
        "levelno", "lineno", "module", "msecs", "message", "pathname",
        "process", "processName", "relativeCreated", "stack_info", "exc_info",
        "exc_text", "thread", "threadName", "message", "taskName",
    }


class LogContext:
    """线程安全的日志上下文管理器"""

    __slots__ = ("_token", "_updates")

    def __init__(self, **kwargs: Any):
        self._token: Optional[object] = None
        self._updates = kwargs

    def __enter__(self) -> "LogContext":
        self._token = _log_ctx.set({**_log_ctx.get(), **self._updates})
        return self

    def __exit__(self, *args):
        if self._token is not None:
            _log_ctx.reset(self._token)


def setup_logging(
    agent_name: str = "pha",
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """
    初始化日志：
    - json_format=True  → PHAJsonLog（给 Loki/ELK 用）
    - json_format=False → 标准人类可读格式（开发用）
    """
    global _logging_initialized
    _logging_initialized = True

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复 handler
    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if json_format:
        # Loki/ELK 友好 JSON
        formatter = PHAJsonLog(agent_name=agent_name)
    else:
        # 开发用彩色格式
        fmt = (
            "%(asctime)s %(levelname)-8s %(name)s:%(funcName)s:%(lineno)d  %(message)s"
        )
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # 第三方库降噪
    for noisy in ["urllib3", "httpx", "httpcore", "uvicorn.access"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("[logging] structured logging initialized agent=%s json=%s",
                  agent_name, json_format)


def get_request_logger(name: str = __name__) -> logging.Logger:
    """获取带当前 LogContext 的 logger（每次打日志自动附带上文）"""
    return logging.getLogger(name)
