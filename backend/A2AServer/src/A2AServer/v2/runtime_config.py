"""
RuntimeConfig — 运行时配置单例

目的：
- 让 env 变量做"默认值"，但 admin dashboard 可以在不重启的情况下改
- 每次 set() 写 Postgres（pha_runtime_config 表），重启后仍生效
- 暴露 version() 计数器，消费端可以检测变更

设计依据：用户决策"配置变更持久化到 Postgres"
与 audit log 不同：audit log 仍是 in-memory deque（write_audit.py:131）
本表是新的，专用 runtime config，不动 audit
"""
import os
import json
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# env → 默认值 映射
# ============================================================
def _defaults_from_env() -> Dict[str, Any]:
    return {
        # semantic cache
        "cache_similarity_threshold": float(os.getenv("PHA_CACHE_SIMILARITY", "0.85")),
        "cache_ttl_sec": int(os.getenv("PHA_LLM_CACHE_TTL", "3600")),
        "cache_max_size": int(os.getenv("PHA_LLM_CACHE_SIZE", "1000")),
        # model routing
        "fallback_chain": [
            p.strip() for p in os.getenv(
                "PHA_MODEL_FALLBACK_CHAIN", "deepseek,qwen,claude,local"
            ).split(",") if p.strip()
        ],
        "task_routing": {
            "chat": os.getenv("PHA_TASK_CHAT", "deepseek").lower(),
            "code": os.getenv("PHA_TASK_CODE", "deepseek").lower(),
            "analysis": os.getenv("PHA_TASK_ANALYSIS", "claude").lower(),
            "summary": os.getenv("PHA_TASK_SUMMARY", "qwen").lower(),
            "translation": os.getenv("PHA_TASK_TRANSLATION", "qwen").lower(),
            "creative": os.getenv("PHA_TASK_CREATIVE", "claude").lower(),
        },
    }


# Postgres 持久化失败时的降级（不阻断运行时配置）
def _try_persist(key: str, value: Any, version: int) -> None:
    """写 Postgres（异步-非关键）。失败只 log，不抛。"""
    try:
        import psycopg
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            return
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pha_runtime_config (key, value, version, updated_at)
                    VALUES (%s, %s::jsonb, %s, now())
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        version = EXCLUDED.version,
                        updated_at = now()
                    """,
                    (key, json.dumps(value), version),
                )
    except Exception as e:
        logger.debug(f"[runtime_config] persist {key} failed: {e}")


def _try_load_all() -> Dict[str, Any]:
    """启动时从 Postgres 加载所有已持久化的 key，覆盖默认值"""
    try:
        import psycopg
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            return {}
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM pha_runtime_config")
                out: Dict[str, Any] = {}
                for k, v in cur.fetchall():
                    if isinstance(v, str):
                        try:
                            out[k] = json.loads(v)
                        except Exception:
                            out[k] = v
                    else:
                        out[k] = v
                return out
    except Exception as e:
        logger.debug(f"[runtime_config] load from db failed: {e}")
        return {}


# ============================================================
# 单例
# ============================================================
class RuntimeConfig:
    _instance: Optional["RuntimeConfig"] = None
    _lock_cls = threading.Lock()

    def __init__(self):
        # 内存快照
        self._values: Dict[str, Any] = _defaults_from_env()
        # 用 Postgres 中的值覆盖 env 默认
        persisted = _try_load_all()
        if persisted:
            self._values.update(persisted)
        self._version_per_key: Dict[str, int] = {k: 0 for k in self._values}
        self._lock = threading.Lock()

    # ---------- 单例获取 ----------
    @classmethod
    def instance(cls) -> "RuntimeConfig":
        if cls._instance is None:
            with cls._lock_cls:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------- 读 ----------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """完整快照（不包含凭证类 key）"""
        with self._lock:
            return {k: v for k, v in self._values.items() if _is_safe_key(k)}

    def version(self, key: str) -> int:
        with self._lock:
            return self._version_per_key.get(key, 0)

    # ---------- 写 ----------
    def set(self, key: str, value: Any, persist: bool = True) -> int:
        """设置一个 key。返回新的 version 计数。"""
        with self._lock:
            self._values[key] = value
            self._version_per_key[key] = self._version_per_key.get(key, 0) + 1
            new_version = self._version_per_key[key]
        if persist:
            _try_persist(key, value, new_version)
        logger.info(f"[runtime_config] {key} -> {value} (v{new_version})")
        return new_version

    def reset_all(self) -> None:
        """重置回 env 默认值（dashboard 'reset to env' 按钮）"""
        env_defaults = _defaults_from_env()
        with self._lock:
            self._values = env_defaults
            self._version_per_key = {k: 0 for k in env_defaults}
        # 删掉 Postgres 中的所有行
        try:
            import psycopg
            dsn = os.getenv("DATABASE_URL")
            if dsn:
                with psycopg.connect(dsn, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM pha_runtime_config")
        except Exception as e:
            logger.debug(f"[runtime_config] reset_all db cleanup failed: {e}")


# ============================================================
# 辅助
# ============================================================
def _is_safe_key(k: str) -> bool:
    """屏蔽任何看起来像凭证的 key 离开边界"""
    upper = k.upper()
    for bad in ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD"):
        if bad in upper:
            return False
    return True


def get_runtime_config() -> RuntimeConfig:
    return RuntimeConfig.instance()
