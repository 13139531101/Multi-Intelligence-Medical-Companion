"""
PHA v2 多模型协同（阶段24）

实现：
- 4 Provider 抽象：DeepSeek / Qwen (DashScope) / Claude (Anthropic) / Local
- 智能路由：按 task_type（chat / code / summary / analysis）选最佳 provider
- 自动 fallback：主 provider 失败时降级到备选
- 限流：每 provider 每分钟 N 次（防滥用）
- 统计：每个 provider 的 success/error/tokens/latency

API:
  await router.chat(prompt, task_type="chat", max_tokens=2048, temperature=0.7)
  → 选最佳 provider → 失败 fallback → 返 ChatResult
"""
import os
import time
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from collections import deque

import httpx

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("QWEN_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
DASHSCOPE_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-plus")

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_BASE_URL = os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com/v1")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

LOCAL_MODEL_URL = os.getenv("LOCAL_MODEL_URL", "")  # 如 http://localhost:11434/v1 (ollama)

# 限流：每 provider 每分钟 N 次
PROVIDER_RATE_LIMIT_PER_MIN = int(os.getenv("PHA_PROVIDER_RATE_LIMIT", "60"))

# fallback 链：主失败时按这个顺序
FALLBACK_CHAIN = os.getenv(
    "PHA_MODEL_FALLBACK_CHAIN",
    "deepseek,qwen,claude,local"
).split(",")

# 任务类型 → 最佳 provider 映射
TASK_ROUTING = {
    "chat": os.getenv("PHA_TASK_CHAT", "deepseek").lower(),
    "code": os.getenv("PHA_TASK_CODE", "deepseek").lower(),
    "analysis": os.getenv("PHA_TASK_ANALYSIS", "claude").lower(),
    "summary": os.getenv("PHA_TASK_SUMMARY", "qwen").lower(),
    "translation": os.getenv("PHA_TASK_TRANSLATION", "qwen").lower(),
    "creative": os.getenv("PHA_TASK_CREATIVE", "claude").lower(),
}


# ============================================================
# 数据结构
# ============================================================
@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class ChatResult:
    """统一 LLM 返回"""
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    fallback_used: bool = False
    error: Optional[str] = None


@dataclass
class ProviderStats:
    name: str
    success: int = 0
    error: int = 0
    rate_limited: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    last_error: Optional[str] = None
    last_used: float = 0.0


# ============================================================
# Provider 抽象基类
# ============================================================
class Provider:
    name: str = "base"

    async def chat(
        self, messages: List[ChatMessage],
        max_tokens: int = 2048, temperature: float = 0.7,
    ) -> ChatResult:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return True


# ============================================================
# DeepSeek Provider（OpenAI 兼容）
# ============================================================
class DeepSeekProvider(Provider):
    name = "deepseek"

    def __init__(self):
        self._api_key = DEEPSEEK_API_KEY
        self._base_url = DEEPSEEK_BASE_URL.rstrip("/")
        self._model = DEEPSEEK_MODEL

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def chat(self, messages, max_tokens=2048, temperature=0.7) -> ChatResult:
        t0 = time.time()
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResult(
            text=choice["message"]["content"],
            provider=self.name,
            model=self._model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=(time.time() - t0) * 1000,
        )


# ============================================================
# Qwen (DashScope) Provider
# ============================================================
class QwenProvider(Provider):
    name = "qwen"

    def __init__(self):
        self._api_key = DASHSCOPE_API_KEY
        self._base_url = DASHSCOPE_BASE_URL.rstrip("/")
        self._model = DASHSCOPE_MODEL

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def chat(self, messages, max_tokens=2048, temperature=0.7) -> ChatResult:
        t0 = time.time()
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResult(
            text=choice["message"]["content"],
            provider=self.name,
            model=self._model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=(time.time() - t0) * 1000,
        )


# ============================================================
# Claude (Anthropic) Provider
# ============================================================
class ClaudeProvider(Provider):
    name = "claude"

    def __init__(self):
        self._api_key = CLAUDE_API_KEY
        self._base_url = CLAUDE_BASE_URL.rstrip("/")
        self._model = CLAUDE_MODEL

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def chat(self, messages, max_tokens=2048, temperature=0.7) -> ChatResult:
        t0 = time.time()
        # Anthropic 格式不同：system 单独，messages 只有 user/assistant
        system_msg = ""
        claude_messages = []
        for m in messages:
            if m.role == "system":
                system_msg += m.content + "\n"
            else:
                claude_messages.append({"role": m.role, "content": m.content})
        url = f"{self._base_url}/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": claude_messages,
        }
        if system_msg:
            body["system"] = system_msg.strip()
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]
        usage = data.get("usage", {})
        return ChatResult(
            text=text,
            provider=self.name,
            model=self._model,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            latency_ms=(time.time() - t0) * 1000,
        )


# ============================================================
# Local Provider（Ollama / vLLM 等 OpenAI 兼容）
# ============================================================
class LocalProvider(Provider):
    name = "local"

    def __init__(self):
        self._base_url = LOCAL_MODEL_URL.rstrip("/")
        self._model = os.getenv("LOCAL_MODEL_NAME", "llama3.1:8b")

    def is_configured(self) -> bool:
        return bool(self._base_url)

    async def chat(self, messages, max_tokens=2048, temperature=0.7) -> ChatResult:
        t0 = time.time()
        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResult(
            text=choice["message"]["content"],
            provider=self.name,
            model=self._model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=(time.time() - t0) * 1000,
        )


# ============================================================
# 限流（每 provider 60s 窗口）
# ============================================================
class RateLimiter:
    def __init__(self):
        self._windows: Dict[str, deque] = {}

    def is_allowed(self, provider_name: str) -> bool:
        now = time.time()
        dq = self._windows.setdefault(provider_name, deque())
        while dq and dq[0] < now - 60:
            dq.popleft()
        if len(dq) >= PROVIDER_RATE_LIMIT_PER_MIN:
            return False
        dq.append(now)
        return True


# ============================================================
# Router（主类）
# ============================================================
class ModelRouter:
    """多模型路由器"""

    def __init__(self):
        self._providers: Dict[str, Provider] = {
            "deepseek": DeepSeekProvider(),
            "qwen": QwenProvider(),
            "claude": ClaudeProvider(),
            "local": LocalProvider(),
        }
        self._limiter = RateLimiter()
        self._stats: Dict[str, ProviderStats] = {
            name: ProviderStats(name=name) for name in self._providers
        }

    def get_provider(self, name: str) -> Optional[Provider]:
        return self._providers.get(name)

    def list_providers(self) -> List[dict]:
        """列所有 provider + 状态"""
        out = []
        for name, p in self._providers.items():
            out.append({
                "name": name,
                "configured": p.is_configured(),
                "model": getattr(p, "_model", ""),
                "stats": self._stats[name].__dict__,
            })
        return out

    def _record_success(self, name: str, latency_ms: float, tokens: int) -> None:
        s = self._stats[name]
        s.success += 1
        s.total_latency_ms += latency_ms
        s.total_tokens += tokens
        s.last_used = time.time()

    def _record_error(self, name: str, err: str) -> None:
        s = self._stats[name]
        s.error += 1
        s.last_error = err[:200]
        s.last_used = time.time()

    def _record_rate_limited(self, name: str) -> None:
        self._stats[name].rate_limited += 1

    async def chat(
        self,
        messages: List[ChatMessage],
        task_type: str = "chat",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        prefer_provider: str = None,
    ) -> ChatResult:
        """
        智能路由 + fallback
        """
        # 1. 选主 provider
        primary = prefer_provider or TASK_ROUTING.get(task_type, "deepseek")
        chain = [primary] + [p for p in FALLBACK_CHAIN if p != primary]

        # 2. 尝试每个 provider 直到成功
        last_error = None
        used_fallback = False
        for idx, name in enumerate(chain):
            provider = self._providers.get(name)
            if not provider:
                continue
            if not provider.is_configured():
                logger.debug(f"[router] {name} not configured, skip")
                continue
            if not self._limiter.is_allowed(name):
                self._record_rate_limited(name)
                logger.debug(f"[router] {name} rate limited")
                continue
            try:
                result = await provider.chat(messages, max_tokens, temperature)
                self._record_success(name, result.latency_ms, result.total_tokens)
                if idx > 0:
                    result.fallback_used = True
                return result
            except Exception as e:
                self._record_error(name, str(e))
                last_error = f"{name}: {e}"
                logger.warning(f"[router] {name} failed: {e}, trying fallback")
                continue

        # 3. 全失败
        return ChatResult(
            text="",
            provider="none",
            model="",
            latency_ms=0.0,
            error=last_error or "no provider available",
        )

    def stats(self) -> dict:
        return {
            "providers": {
                name: {
                    "success": s.success,
                    "error": s.error,
                    "rate_limited": s.rate_limited,
                    "avg_latency_ms": round(s.total_latency_ms / max(s.success, 1), 1),
                    "total_tokens": s.total_tokens,
                    "last_error": s.last_error,
                    "last_used": s.last_used,
                }
                for name, s in self._stats.items()
            },
            "config": {
                "fallback_chain": FALLBACK_CHAIN,
                "task_routing": TASK_ROUTING,
                "rate_limit_per_min": PROVIDER_RATE_LIMIT_PER_MIN,
            },
        }


# ============================================================
# 单例
# ============================================================
_instance: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    global _instance
    if _instance is None:
        _instance = ModelRouter()
    return _instance
