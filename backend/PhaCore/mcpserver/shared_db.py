"""PhaCore shared_db - 统一 PG 连接 + DSN 处理.

之前 4 份 `_normalize_pg_dsn` + 5 个 `database_config.py` 重复实现,
现在统一一份.
"""
from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Optional, Iterator
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def _get_raw_dsn(env_var: str = "MEDICATION_DB_DSN", default: str = "") -> str:
    """读 env var, 支持 fallback."""
    return (
        os.getenv(env_var)
        or os.getenv("PGSQL_DSN")
        or os.getenv("POSTGRES_DSN")
        or os.getenv("DATABASE_URL")
        or default
    )


def _build_pg_dsn(
    agent_name: str = "",
    host: str = "",
    port: int = 5432,
    database: str = "",
    user: str = "",
    password: str = "",
    env_var: str = "MEDICATION_DB_DSN",
) -> str:
    """构造 PG DSN, 优先级: env var > 显式参数 > default.

    兼容 Windows host=postgres → localhost 的修复逻辑 (之前 4 份重复).
    """
    raw = _get_raw_dsn(env_var)
    if raw:
        return _normalize_pg_dsn(raw)

    if not all([host, database, user]):
        logger.warning("[PhaCore.shared_db] %s: DSN incomplete, falling back to localhost defaults", agent_name)
        host = host or "localhost"
        database = database or "personal_health_assistant"
        user = user or "pha"

    pwd = f":{password}" if password else ""
    return f"postgresql://{user}{pwd}@{host}:{port}/{database}"


def _normalize_pg_dsn(dsn: str) -> str:
    """DSN 规范化: Windows 'postgres' → 'localhost' (跨平台兼容).

    之前 4 份逐字符复制:
      - MedicationReminder/reminder_tool.py:32
      - MedicationReminder/notification_tool.py:37
      - MedicationReminder/drug_safety_tool.py:32
      - HealthRecordsManager/async_analysis_tool.py:86 (inline)
    现在统一一份.
    """
    dsn = (dsn or "").strip()
    if not dsn:
        return dsn
    if os.name != "nt":
        return dsn
    try:
        u = urlparse(dsn)
        host = (u.hostname or "").strip().lower()
        if host != "postgres":
            return dsn
        userinfo = ""
        if u.username:
            userinfo = u.username
            if u.password:
                userinfo = f"{userinfo}:{u.password}"
            userinfo = f"{userinfo}@"
        port = f":{u.port}" if u.port else ""
        netloc = f"{userinfo}localhost{port}"
        return urlunparse(u._replace(netloc=netloc))
    except Exception:
        return dsn


@contextmanager
def get_pg_conn(
    agent_name: str = "",
    env_var: str = "MEDICATION_DB_DSN",
    row_factory: bool = True,
) -> Iterator["psycopg.Connection"]:
    """统一的 psycopg connection 上下文管理器.

    Args:
        agent_name: 调用方 agent 名 (用于 log)
        env_var: 优先读这个 env var
        row_factory: True 用 dict_row (默认)
    """
    import psycopg
    from psycopg.rows import dict_row

    dsn = _build_pg_dsn(agent_name=agent_name, env_var=env_var)
    conn_kwargs = {"row_factory": dict_row} if row_factory else {}
    conn = psycopg.connect(dsn, **conn_kwargs)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


__all__ = [
    "_build_pg_dsn",
    "_normalize_pg_dsn",
    "get_pg_conn",
]
