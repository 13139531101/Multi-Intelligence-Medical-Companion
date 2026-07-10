"""
PHA v2 限流（阶段12）

**问题**：
- LLM API (DeepSeek) 有 QPS 限制（默认 60 QPS）
- 单实例 v2 突发请求可能瞬间打爆 LLM API
- 触发 429 限流后整个服务雪崩

**方案**：token bucket 算法限流
- 全局：限制每秒 N 个 LLM 调用
- 按 user：每个 user_id 每分钟 M 个请求
- 按 agent：每个 agent 类独立配额

**实现**：
- 纯 Python，无外部依赖
- 异步友好（asyncio.Lock）
- 可监控（stats 接入 monitoring）

**用法**：
```python
from A2AServer.v2.rate_limit import get_rate_limiter

limiter = get_rate_limiter()
if not await limiter.allow_llm_call(user_id='u1'):
    raise RateLimitError("LLM API 限流")
```
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """限流异常"""
    pass


# ============================================================
# Token Bucket 单实现
# ============================================================
class TokenBucket:
    """Token bucket 限流器（异步安全）"""

    def __init__(self, rate: float, capacity: Optional[int] = None):
        """
        Args:
            rate: 每秒补充的 token 数
            capacity: 桶容量（默认等于 rate）
        """
        self.rate = rate
        self.capacity = capacity or max(1, int(rate))
        self._tokens = float(self.capacity)
        self._last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """
        尝试获取 N 个 token

        Returns:
            True: 允许
            False: 拒绝（限流）
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_refill
            # 补充 token
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.rate,
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def wait_and_acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """等待直到获取 token（或超时）"""
        start = time.time()
        while time.time() - start < timeout:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(1.0 / self.rate)
        return False

    def stats(self) -> dict:
        return {
            "rate": self.rate,
            "capacity": self.capacity,
            "current_tokens": round(self._tokens, 2),
        }


# ============================================================
# 滑动窗口限流（按 user）
# ============================================================
class SlidingWindowLimiter:
    """按 user_id 滑动窗口限流（每分钟最多 N 次）"""

    def __init__(self, max_requests: int, window_sec: float = 60.0):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_sec
            # 清理过期记录
            self._history[key] = [t for t in self._history[key] if t > cutoff]
            if len(self._history[key]) >= self.max_requests:
                return False
            self._history[key].append(now)
            return True

    def stats(self) -> dict:
        total = sum(len(v) for v in self._history.values())
        return {
            "max_requests": self.max_requests,
            "window_sec": self.window_sec,
            "active_keys": len(self._history),
            "total_requests": total,
        }


# ============================================================
# PHA v2 限流器（组合）
# ============================================================
class PHA2RateLimiter:
    """
    PHA v2 多层限流

    限流层（从最严到最松）：
    1. 全局 LLM QPS（默认 30 QPS - DeepSeek 推荐）
    2. 按 user_id（默认 60 req/min - 防单用户刷爆）
    3. 按 agent 类（默认 60 req/min/agent）
    """

    def __init__(
        self,
        llm_qps: float = 30.0,
        user_rpm: int = 60,
        agent_rpm: int = 60,
        window_sec: float = 60.0,
    ):
        self.llm_bucket = TokenBucket(rate=llm_qps)
        self.user_limiter = SlidingWindowLimiter(max_requests=user_rpm, window_sec=window_sec)
        self.agent_limiter = SlidingWindowLimiter(max_requests=agent_rpm, window_sec=window_sec)
        self._stats = {
            "llm_allowed": 0,
            "llm_denied": 0,
            "user_denied": 0,
            "agent_denied": 0,
        }

    async def allow_llm_call(self, user_id: Optional[str] = None, agent_name: Optional[str] = None) -> bool:
        """
        检查是否允许一次 LLM 调用

        Returns:
            True: 允许
            False: 拒绝（需限流）
        """
        # 1. 全局 LLM QPS
        # 1. 全局 LLM QPS
        if not await self.llm_bucket.acquire():
            self._stats["llm_denied"] += 1
            logger.warning(f"[rate_limit] LLM QPS limit hit")
            return False

        # 2. 按 user
        if user_id and not await self.user_limiter.allow(user_id):
            self._stats["user_denied"] += 1
            logger.warning(
                f"[rate_limit] user {user_id} RPM limit hit "
                f"(history={len(self.user_limiter._history.get(user_id, []))})"
            )
            return False

        # 3. 按 agent
        if agent_name and not await self.agent_limiter.allow(agent_name):
            self._stats["agent_denied"] += 1
            logger.warning(f"[rate_limit] agent {agent_name} RPM limit hit")
            return False

        self._stats["llm_allowed"] += 1
        return True

    def stats(self) -> dict:
        return {
            **self._stats,
            "llm_bucket": self.llm_bucket.stats(),
            "user_limiter": self.user_limiter.stats(),
            "agent_limiter": self.agent_limiter.stats(),
        }


# ============================================================
# 全局单例 + 配置
# ============================================================
import os

_global_limiter: Optional[PHA2RateLimiter] = None


def get_rate_limiter() -> PHA2RateLimiter:
    """获取全局限流器单例"""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = PHA2RateLimiter(
            llm_qps=float(os.getenv("PHA_LLM_QPS", "30")),
            user_rpm=int(os.getenv("PHA_USER_RPM", "60")),
            agent_rpm=int(os.getenv("PHA_AGENT_RPM", "60")),
            window_sec=float(os.getenv("PHA_RATE_LIMIT_WINDOW", "60")),
        )
        logger.info(
            f"[rate_limit] initialized: llm_qps={_global_limiter.llm_bucket.rate}, "
            f"user_rpm={_global_limiter.user_limiter.max_requests}, "
            f"agent_rpm={_global_limiter.agent_limiter.max_requests}, "
            f"window_sec={_global_limiter.user_limiter.window_sec}"
        )
    return _global_limiter


def reset_rate_limiter():
    """重置限流器（仅用于测试）"""
    global _global_limiter
    _global_limiter = None
