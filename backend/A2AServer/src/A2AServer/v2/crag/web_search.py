"""
PHA v2 CRAG Web Search Provider 抽象 + 实现

抽象接口：
- WebSearchProvider (ABC) : search(query, num_results) -> list[WebResult]

实现（按优先级）：
1. DuckDuckGoProvider  — 免费，无需 key（默认）
2. TavilyProvider      — 需要 TAVILY_API_KEY，质量最高
3. SerpApiProvider     — 需要 SERPAPI_KEY，Bing 底层

选择逻辑：
- 环境变量 PHA_WEB_SEARCH_PROVIDER 优先
- 否则按 key 可用性自动选择
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================
@dataclass
class WebResult:
    """Web 搜索结果"""
    title: str
    url: str
    snippet: str
    score: float = 0.0  # 搜索引擎返回的相关性分数


# ============================================================
# Provider 抽象
# ============================================================
class WebSearchProvider(ABC):
    """Web 搜索提供者抽象"""

    name: str = "abstract"

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[WebResult]:
        """
        搜索并返回结果

        Args:
            query: 搜索 query
            num_results: 返回数量上限

        Returns:
            WebResult 列表（按相关性排序）
        """
        ...

    async def close(self) -> None:
        """关闭资源（子类可覆盖）"""
        pass


# ============================================================
# DuckDuckGo Provider（免费，无需 key）
# ============================================================
class DuckDuckGoProvider(WebSearchProvider):
    """
    DuckDuckGo 搜索实现

    使用 duckduckgo_search pip 包，无需 API key。
    适合开发/测试环境，生产环境建议用 Tavily。
    """

    name = "duckduckgo"

    def __init__(self):
        self._ddgs = None
        # 延迟导入，避免包不存在时直接报错
        self._DDGS = None

    def _ensure_ddgs(self):
        if self._DDGS is None:
            try:
                from duckduckgo_search import DDGS
                self._DDGS = DDGS
            except ImportError:
                raise ImportError(
                    "duckduckgo-search 未安装。请运行: pip install duckduckgo-search>=5.0"
                )

    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[WebResult]:
        self._ensure_ddgs()

        # DuckDuckGo 搜索是同步的，在线程池中执行避免阻塞
        import asyncio
        loop = asyncio.get_event_loop()

        def _sync_search():
            self._ddgs = self._DDGS()
            results = []
            try:
                for r in self._ddgs.text(query, max_results=num_results):
                    results.append(WebResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("body", ""),
                        score=0.8,  # DuckDuckGo 不提供分数，用默认值
                    ))
            finally:
                self._ddgs = None
            return results

        try:
            results = await loop.run_in_executor(None, _sync_search)
            logger.info("[crag][duckduckgo] query=%s got=%d", query[:30], len(results))
            return results
        except Exception as e:
            logger.warning("[crag][duckduckgo] search failed: %s", e)
            return []


# ============================================================
# Tavily Provider（需要 key，质量最高）
# ============================================================
class TavilyProvider(WebSearchProvider):
    """
    Tavily AI 搜索实现

    需要 TAVILY_API_KEY 环境变量。
    Tavily 是专门为 AI 设计的搜索 API，返回结构化高质量结果。
    """

    name = "tavily"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("TAVILY_API_KEY", "")
        self._base_url = "https://api.tavily.com/search"

    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[WebResult]:
        if not self._api_key:
            logger.warning("[crag][tavily] TAVILY_API_KEY not set, falling back to empty")
            return []

        import httpx

        body = {
            "query": query,
            "search_depth": "basic",
            "max_results": num_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    self._base_url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
                r.raise_for_status()
                data = r.json()

            results = []
            for item in data.get("results", [])[:num_results]:
                results.append(WebResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    score=item.get("score", 0.8),
                ))
            logger.info("[crag][tavily] query=%s got=%d", query[:30], len(results))
            return results
        except httpx.HTTPStatusError as e:
            logger.warning("[crag][tavily] HTTP error: %s", e)
            return []
        except Exception as e:
            logger.warning("[crag][tavily] search failed: %s", e)
            return []


# ============================================================
# SerpApi Provider（Bing 底层，需要 key）
# ============================================================
class SerpApiProvider(WebSearchProvider):
    """
    SerpAPI (Google/Bing) 搜索实现

    需要 SERPAPI_KEY 环境变量。
    底层是 Google Custom Search 或 Bing Web Search。
    """

    name = "serpapi"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("SERPAPI_KEY", "")
        self._base_url = "https://serpapi.com/search"

    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[WebResult]:
        if not self._api_key:
            logger.warning("[crag][serpapi] SERPAPI_KEY not set")
            return []

        import httpx

        params = {
            "q": query,
            "api_key": self._api_key,
            "num": num_results,
            "engine": "google",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(self._base_url, params=params)
                r.raise_for_status()
                data = r.json()

            results = []
            for item in data.get("organic_results", [])[:num_results]:
                results.append(WebResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    score=item.get("inline_images", [{}]) and 0.8 or 0.7,
                ))
            logger.info("[crag][serpapi] query=%s got=%d", query[:30], len(results))
            return results
        except Exception as e:
            logger.warning("[crag][serpapi] search failed: %s", e)
            return []


# ============================================================
# Provider 工厂
# ============================================================
_provider_cache: Optional[WebSearchProvider] = None


def get_web_search_provider() -> WebSearchProvider:
    """
    获取 WebSearchProvider 单例

    选择顺序：
    1. PHA_WEB_SEARCH_PROVIDER 环境变量指定
    2. 按 key 可用性自动选择（Tavily > SerpApi > DuckDuckGo）
    3. 默认 DuckDuckGo
    """
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache

    provider_name = os.getenv("PHA_WEB_SEARCH_PROVIDER", "").lower()

    if provider_name == "tavily":
        provider = TavilyProvider()
        if not os.getenv("TAVILY_API_KEY"):
            logger.warning("[crag] Tavily selected but TAVILY_API_KEY not set, falling back to DuckDuckGo")
            provider = None
    elif provider_name == "serpapi":
        provider = SerpApiProvider()
        if not os.getenv("SERPAPI_KEY"):
            logger.warning("[crag] SerpAPI selected but SERPAPI_KEY not set, falling back to DuckDuckGo")
            provider = None
    elif provider_name == "duckduckgo" or not provider_name:
        # 默认或显式指定 duckduckgo
        provider = DuckDuckGoProvider()
    else:
        logger.warning("[crag] Unknown provider %s, using DuckDuckGo", provider_name)
        provider = DuckDuckGoProvider()

    _provider_cache = provider
    logger.info("[crag] WebSearchProvider: %s", provider.name)
    return provider


def reset_web_search_provider() -> None:
    """重置 provider 缓存（用于测试或热更新配置）"""
    global _provider_cache
    if _provider_cache is not None:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_provider_cache.close())
        except RuntimeError:
            pass
    _provider_cache = None
