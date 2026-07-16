"""
PHA v2 LLM 响应语义缓存（阶段39-3）

**目的**：减少 LLM API 调用，节省成本 + 加速响应

**三种缓存策略**：
1. **精确匹配**: message hash（key = hash(messages + params)）
2. **前缀匹配**: 相同 system + 前 N 轮 user
3. **语义匹配**: embedding 相似度 > 阈值（需要 embedding 模型，简化版跳过）

**当前实现**：精确匹配 + 简单的"相似文本"匹配（normalize 后 hash）

**生产应**：
- 用 Redis 存（跨进程）
- 加 LRU eviction
- 加 TTL（默认 1 小时）
- 加 embedding 缓存（Redis + 向量索引）

**集成**：
- multi_model.chat() 之前查缓存
- 缓存命中直接返回，不调 LLM
- 记录 hit/miss 到 monitoring
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 1. 缓存条目
# ============================================================

@dataclass
class CacheEntry:
    key: str
    messages_hash: str
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    hit_count: int = 0
    task_type: str = "chat"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "messages_hash": self.messages_hash,
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "hit_count": self.hit_count,
            "task_type": self.task_type,
            "text_len": len(self.text),
        }


# ============================================================
# 2. 哈希函数
# ============================================================

def normalize_messages(messages: List[Dict[str, str]]) -> str:
    """规范化 messages（去空格 + 小写）"""
    parts = []
    for m in messages:
        role = m.get("role", "").strip()
        content = re.sub(r"\s+", " ", m.get("content", "").strip())
        parts.append(f"{role}:{content}")
    return "\n".join(parts)


def hash_messages(
    messages: List[Dict[str, str]],
    task_type: str = "chat",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """计算 messages 的 hash（精确匹配 key）"""
    norm = normalize_messages(messages)
    raw = f"{task_type}|{max_tokens}|{temperature:.2f}|{norm}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_messages_similar(messages: List[Dict[str, str]]) -> str:
    """
    计算 messages 的"相似" hash（忽略 temperature + max_tokens）
    用于同类问题的缓存复用
    """
    norm = normalize_messages(messages)
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


# ============================================================
# 3. LRU 缓存
# ============================================================

class SemanticCache:
    """
    LLM 响应 LRU 缓存（按 hash key）

    特性：
    - LRU eviction（max_size 限制）
    - TTL（默认 1 小时）
    - 精确 hash + 相似 hash 两种 lookup
    - 统计 hit / miss / evictions
    """

    def __init__(self, max_size: int = 1000, ttl_sec: int = 3600):
        self.max_size = max_size
        self.ttl_sec = ttl_sec
        self._cache: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "stores": 0,
        }

    def get(self, messages: List[Dict[str, str]], task_type: str = "chat",
            max_tokens: int = 2048, temperature: float = 0.7) -> Optional[CacheEntry]:
        """查缓存（先精确，再相似）"""
        # 1. 精确 hash
        key = hash_messages(messages, task_type, max_tokens, temperature)
        entry = self._lookup(key)
        if entry:
            return entry

        # 2. 相似 hash（忽略 temp/tokens）
        sim_key = hash_messages_similar(messages)
        entry = self._lookup(sim_key)
        if entry:
            return entry

        self._stats["misses"] += 1
        return None

    def _lookup(self, key: str) -> Optional[CacheEntry]:
        if key not in self._cache:
            return None
        entry = self._cache[key]
        # TTL 检查
        if time.time() - entry.created_at > self.ttl_sec:
            del self._cache[key]
            self._stats["expirations"] += 1
            return None
        # LRU: 移到末尾
        self._cache.move_to_end(key)
        entry.last_used_at = time.time()
        entry.hit_count += 1
        self._stats["hits"] += 1
        return entry

    def set(self, messages: List[Dict[str, str]], text: str,
            provider: str, model: str, task_type: str = "chat",
            max_tokens: int = 2048, temperature: float = 0.7,
            prompt_tokens: int = 0, completion_tokens: int = 0) -> CacheEntry:
        """存缓存"""
        messages_hash = hash_messages(messages, task_type, max_tokens, temperature)
        sim_hash = hash_messages_similar(messages)

        entry = CacheEntry(
            key=messages_hash,
            messages_hash=messages_hash,
            text=text,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            task_type=task_type,
        )
        # 存 2 个 key（精确 + 相似）
        self._cache[messages_hash] = entry
        if sim_hash != messages_hash:
            self._cache[sim_hash] = entry
        self._stats["stores"] += 1
        # LRU eviction
        self._evict_if_needed()
        return entry

    def _evict_if_needed(self):
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)  # 移除最旧
            self._stats["evictions"] += 1

    def clear(self):
        self._cache.clear()
        logger.info("[semantic_cache] cleared")

    def stats(self) -> Dict[str, Any]:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total * 100 if total else 0
        return {
            **self._stats,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": round(hit_rate, 1),
            "ttl_sec": self.ttl_sec,
        }

    def list_entries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近的缓存条目（调试用）"""
        return [e.to_dict() for e in list(self._cache.values())[-limit:]]


# ============================================================
# 4. 单例 + 集成 helper
# ============================================================

_cache: Optional[SemanticCache] = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        max_size = int(__import__("os").getenv("PHA_LLM_CACHE_SIZE", "1000"))
        ttl = int(__import__("os").getenv("PHA_LLM_CACHE_TTL", "3600"))
        _cache = SemanticCache(max_size=max_size, ttl_sec=ttl)
        logger.info("[semantic_cache] initialized: max_size=%d, ttl=%ds", max_size, ttl)
    return _cache


def cached_chat(
    messages: List[Dict[str, str]],
    chat_fn,
    task_type: str = "chat",
    max_tokens: int = 2048,
    temperature: float = 0.7,
):
    """
    缓存 wrapper：先查缓存，未命中调 chat_fn，结果存缓存

    chat_fn: async (messages, task_type, max_tokens, temperature) -> ChatResult
    """
    cache = get_cache()
    # 1. 查
    entry = cache.get(messages, task_type, max_tokens, temperature)
    if entry:
        logger.debug("[semantic_cache] HIT key=%s hits=%d", entry.key[:8], entry.hit_count)
        # 构造伪 ChatResult
        from dataclasses import dataclass
        @dataclass
        class CachedResult:
            text: str
            provider: str
            model: str
            prompt_tokens: int = 0
            completion_tokens: int = 0
            latency_ms: float = 0.0
            fallback_used: bool = False
            error: str = None
        return CachedResult(
            text=entry.text,
            provider=entry.provider + " (cached)",
            model=entry.model,
            prompt_tokens=entry.prompt_tokens,
            completion_tokens=entry.completion_tokens,
        )

    # 2. miss → 调 LLM
    result = chat_fn(messages, task_type, max_tokens, temperature)

    # 3. 存
    if result and result.text:
        cache.set(
            messages,
            result.text,
            provider=result.provider,
            model=result.model,
            task_type=task_type,
            max_tokens=max_tokens,
            temperature=temperature,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )
    return result


__all__ = [
    "CacheEntry",
    "SemanticCache",
    "get_cache",
    "hash_messages",
    "normalize_messages",
    "cached_chat",
]