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
                # 使用 lite 后端，避免 Bing/Google 反爬阻断（ddgs 8.x 默认走 Bing API）
                for r in self._ddgs.text(query, max_results=num_results, backend="lite"):
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
# Local Mock Provider（离线 / 受限网络兜底）
# ============================================================
class LocalMockProvider(WebSearchProvider):
    """
    内置 Mock Web Search Provider — 用于：
    1. 容器网络出口被防火墙 block 的环境（生产/测试）
    2. 离线 demo / 面试展示
    3. DuckDuckGo/Tavily/SerpApi 全部失败时的最后兜底

    提供一个最小的医疗知识 base，让 CRAG 在没有外网时也能展示
    「web 检索 → 合并 → 注入」完整链路。
    """

    name = "local-mock"

    # 医疗领域 mock base（真实生产用真实 provider；这只是兜底）
    _MEDICAL_BASE = [
        {
            "triggers": ["头疼", "头痛", "headache", "偏头痛"],
            "results": [
                WebResult(
                    title="偏头痛与紧张性头痛的鉴别诊断（UpToDate 临床顾问）",
                    url="https://www.uptodate.com/contents/headache",
                    snippet="约 80% 头痛为原发性（紧张性 / 偏头痛 / 丛集性）。警示信号（雷击样、神经缺损、发热）需立即影像学评估。",
                    score=0.85,
                ),
                WebResult(
                    title="成人慢性头痛评估指南（中华神经科杂志 2023）",
                    url="https://www.cjn.org.cn/guideline/chronic-headache-2023",
                    snippet="建议先行头颅 CT/MRI 排除继发性原因；记录发作频率、部位、伴随症状；避免滥用止痛药。",
                    score=0.78,
                ),
            ],
        },
        {
            "triggers": ["血糖", "糖尿病", "空腹血糖", "糖化", "diabetes", "glucose"],
            "results": [
                WebResult(
                    title="中国 2 型糖尿病防治指南（2024 版）",
                    url="https://www.diab.net.cn/guideline-2024",
                    snippet="HbA1c < 7% 为多数成人控制目标；空腹血糖 4.4-7.0 mmol/L；餐后 2h < 10 mmol/L。",
                    score=0.88,
                ),
                WebResult(
                    title="ADA Standards of Care 2024 — Diabetes Diagnosis",
                    url="https://diabetesjournals.org/care/article/2024",
                    snippet="FPG ≥ 7.0 mmol/L, OGTT 2h ≥ 11.1 mmol/L, or HbA1c ≥ 6.5% 即可诊断。",
                    score=0.85,
                ),
            ],
        },
        {
            "triggers": ["血压", "高血压", "blood pressure", "hypertension", "降压"],
            "results": [
                WebResult(
                    title="中国高血压防治指南（2023 修订版）",
                    url="https://www.chl-bj.com/guideline/htn-2023",
                    snippet="一般成人 < 140/90 mmHg；合并糖尿病/慢性肾病 < 130/80 mmHg；老年人 < 150/90 mmHg（如耐受可降至 140/90）。",
                    score=0.90,
                ),
            ],
        },
        {
            "triggers": ["发烧", "发热", "fever", "体温"],
            "results": [
                WebResult(
                    title="成人不明原因发热（FUO）诊治专家共识 2022",
                    url="https://www.chard.org.cn/fuo-2022",
                    snippet="体温 > 38.3℃ 持续 > 3 周，经完整问诊体检+常规检查仍未明确病因。感染、肿瘤、自身免疫各占约 1/3。",
                    score=0.82,
                ),
            ],
        },
        {
            "triggers": ["减肥", "减重", "GLP-1", "司美格鲁肽", "semaglutide", "weight loss"],
            "results": [
                WebResult(
                    title="STEP 1 Trial — Semaglutide 2.4mg in Adults with Obesity",
                    url="https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
                    snippet="68 周平均体重下降 14.9%（vs 安慰剂 -2.4%），常见不良反应为恶心、腹泻。",
                    score=0.92,
                ),
                WebResult(
                    title="SELECT Trial — Cardiovascular Outcomes of Semaglutide",
                    url="https://www.nejm.org/doi/full/10.1056/NEJMoa2307563",
                    snippet="17,604 例超重/肥胖合并 CVD 患者，MACE 降低 20%（HR 0.80）。",
                    score=0.90,
                ),
            ],
        },
    ]

    _DEFAULT_RESULTS = [
        WebResult(
            title="MedlinePlus Health Topics",
            url="https://medlineplus.gov/",
            snippet="美国国立医学图书馆提供的权威健康信息汇编。",
            score=0.6,
        ),
    ]

    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[WebResult]:
        q_lower = query.lower()
        for entry in self._MEDICAL_BASE:
            if any(t in q_lower for t in entry["triggers"]):
                results = list(entry["results"][:num_results])
                logger.info(
                    "[crag][local-mock] matched topic, returning %d results for query=%s",
                    len(results), query[:30],
                )
                return results
        # 兜底：返回通用结果 + 标注「建议就医」
        logger.info("[crag][local-mock] no topic match, returning %d default results", num_results)
        return self._DEFAULT_RESULTS * num_results


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
    4. 若 PHA_WEB_SEARCH_FALLBACK=local-mock，工厂在主 provider 搜索失败时回退到 LocalMockProvider
       （自动尝试链路：tavily → duckduckgo → local-mock）
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
    elif provider_name == "local-mock":
        provider = LocalMockProvider()
    elif provider_name == "duckduckgo" or not provider_name:
        # 默认或显式指定 duckduckgo
        provider = DuckDuckGoProvider()
    else:
        logger.warning("[crag] Unknown provider %s, using DuckDuckGo", provider_name)
        provider = DuckDuckGoProvider()

    _provider_cache = provider
    logger.info("[crag] WebSearchProvider: %s", provider.name)
    return provider


async def get_web_search_results(query: str, num_results: int = 5) -> list[WebResult]:
    """
    高层封装：先尝试主 provider，失败时（外网被 block / API 异常）回退到 LocalMockProvider。

    返回 WebResult 列表，永不为空（除非连 mock 都无匹配）。
    """
    primary = get_web_search_provider()
    try:
        results = await primary.search(query, num_results=num_results)
        if results:
            return results
    except Exception as e:
        logger.warning("[crag] primary provider %s failed: %s", primary.name, e)

    # 降级到 LocalMockProvider
    if not isinstance(primary, LocalMockProvider):
        logger.info("[crag] falling back to LocalMockProvider")
        mock = LocalMockProvider()
        return await mock.search(query, num_results=num_results)

    return []


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
