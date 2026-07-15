"""
PHA v2 ANP Crawler (阶段38-1)

ANP (Agent Network Protocol) 递归爬虫
类似网络爬虫（web crawler），从一个种子 URL 开始
- 拉取 /agent/ad.json
- 解析里面的 relatedAgents / sameAs / seeAlso
- 递归发现新 agent
- 按 DID 去重，避免循环

类似架构：
- Web crawler  →  HTTP 链接
- ANP crawler  →  DID:WBA 标识的 agent 链接
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict

import httpx

logger = logging.getLogger(__name__)


# ============================================================
# 1. 数据模型
# ============================================================

@dataclass
class ANPAgentNode:
    """ANP 爬虫发现的单个 agent 节点"""
    did: str                              # did:wba:pha.local:health_advisor
    did_wba: str                          # 同上 (DID resolution 后的)
    base_url: str                         # http://health_advisor:10011
    name: str                             # health_advisor
    description: str = ""                 # AI 问诊...
    ad: Dict[str, Any] = field(default_factory=dict)  # 完整 AD
    discovered_at: float = 0.0            # 时间戳
    reachable: bool = True                # 是否可达
    tools_count: int = 0                  # OpenRPC 方法数
    error: Optional[str] = None           # 错误信息

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ANPCrawlResult:
    """一次爬虫的完整结果"""
    started_at: float
    finished_at: float
    duration_ms: float
    seed_count: int
    discovered_count: int
    reachable_count: int
    failed_urls: List[str]
    nodes: List[ANPAgentNode]
    graph: Dict[str, List[str]]  # did -> [related_did, ...]


# ============================================================
# 2. 核心 Crawler
# ============================================================

class ANPCrawler:
    """
    ANP 递归爬虫

    用法:
        crawler = ANPCrawler(max_depth=2, max_nodes=50)
        result = await crawler.crawl([
            "http://health_advisor:10011",
            "http://health_records:10010",
        ])

    工作流程:
        1. BFS 队列：种子 URL
        2. 拉取 /agent/ad.json
        3. 解析 DID
        4. 提取 relatedAgents / sameAs / seeAlso
        5. 递归爬
        6. 按 DID 去重
    """

    def __init__(
        self,
        max_depth: int = 2,
        max_nodes: int = 50,
        timeout: float = 5.0,
        max_concurrent: int = 10,
    ):
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        # 内部状态
        self._visited: Set[str] = set()  # did 集合（去重）
        self._nodes: Dict[str, ANPAgentNode] = {}  # did -> node
        self._graph: Dict[str, List[str]] = {}  # did -> [related_did]
        self._failed: List[str] = []

    async def crawl(self, seed_urls: List[str]) -> ANPCrawlResult:
        """
        从 seed URLs 开始递归爬
        """
        started = time.time()
        self._visited = set()
        self._nodes = {}
        self._graph = {}
        self._failed = []

        # BFS 队列: (url, depth)
        queue: List[tuple] = [(u, 0) for u in seed_urls]

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while queue and len(self._nodes) < self.max_nodes:
                # 批量取一批
                batch = []
                while queue and len(batch) < self.max_concurrent:
                    url, depth = queue.pop(0)
                    if depth > self.max_depth:
                        continue
                    batch.append((url, depth))

                if not batch:
                    break

                # 并发拉
                tasks = [
                    self._fetch_and_parse(client, url, depth, semaphore, queue)
                    for url, depth in batch
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

        finished = time.time()
        return ANPCrawlResult(
            started_at=started,
            finished_at=finished,
            duration_ms=(finished - started) * 1000,
            seed_count=len(seed_urls),
            discovered_count=len(self._nodes),
            reachable_count=sum(1 for n in self._nodes.values() if n.reachable),
            failed_urls=list(self._failed),
            nodes=list(self._nodes.values()),
            graph=dict(self._graph),
        )

    async def _fetch_and_parse(
        self,
        client: httpx.AsyncClient,
        url: str,
        depth: int,
        semaphore: asyncio.Semaphore,
        queue: List,
    ):
        """拉取 + 解析单个 agent"""
        async with semaphore:
            try:
                r = await client.get(f"{url.rstrip('/')}/agent/ad.json")
                if r.status_code != 200:
                    self._failed.append(url)
                    logger.debug("[crawler] %s returned %d", url, r.status_code)
                    return
                ad = r.json()
            except Exception as e:
                self._failed.append(url)
                logger.debug("[crawler] %s failed: %s", url, e)
                # 记录失败节点
                did = self._url_to_did(url)
                if did not in self._visited:
                    self._visited.add(did)
                    self._nodes[did] = ANPAgentNode(
                        did=did,
                        did_wba=did,
                        base_url=url,
                        name=did.split(":")[-1] if ":" in did else did,
                        discovered_at=time.time(),
                        reachable=False,
                        error=str(e),
                    )
                return

        # 解析 AD
        did = ad.get("id") or ad.get("did") or ad.get("did_wba") or self._url_to_did(url)
        if did in self._visited:
            return  # 去重
        self._visited.add(did)

        # 提取 related agents (递归爬)
        related_dids = []
        if depth < self.max_depth:
            for related_url in self._extract_related_urls(ad, url):
                related_did = self._url_to_did(related_url)
                if related_did not in self._visited:
                    related_dids.append(related_did)
                    queue.append((related_url, depth + 1))

        # 统计 tools
        tools_count = 0
        try:
            rpc = await client.get(f"{url.rstrip('/')}/agent/interface.json")
            if rpc.status_code == 200:
                tools_count = len(rpc.json().get("methods", []))
        except Exception:
            pass

        # 构造 node
        self._nodes[did] = ANPAgentNode(
            did=did,
            did_wba=did,
            base_url=url,
            name=ad.get("name") or did.split(":")[-1],
            description=ad.get("description", ""),
            ad=ad,
            discovered_at=time.time(),
            reachable=True,
            tools_count=tools_count,
        )
        self._graph[did] = related_dids
        logger.info("[crawler] discovered %s (%d tools, %d related)",
                    did, tools_count, len(related_dids))

    def _url_to_did(self, url: str) -> str:
        """URL → DID 派生（约定：host = did:wba 的一部分）"""
        if "://" in url:
            base = url.split("://", 1)[1]
        else:
            base = url
        # http://health_advisor:10011 -> did:wba:health_advisor
        host = base.split("/", 1)[0].split(":")[0]
        return f"did:wba:pha.local:{host}"

    def _extract_related_urls(self, ad: Dict[str, Any], base_url: str) -> List[str]:
        """
        从 AD 里提取 related agent URLs

        ANP AD 格式约定:
        - ad["relatedAgents"]: [{url, did, name}, ...]
        - ad["sameAs"]: [url, ...]
        - ad["seeAlso"]: [url, ...]
        """
        urls = []
        # 1. relatedAgents (主要来源)
        for r in ad.get("relatedAgents", []) or []:
            if isinstance(r, dict) and r.get("url"):
                urls.append(r["url"])
        # 2. sameAs (类比 JSON-LD)
        for u in ad.get("sameAs", []) or []:
            if isinstance(u, str):
                urls.append(u)
        # 3. seeAlso
        for u in ad.get("seeAlso", []) or []:
            if isinstance(u, str):
                urls.append(u)
        return urls


# ============================================================
# 3. 持久化 (in-memory cache)
# ============================================================

_CRAWL_CACHE: Dict[str, ANPCrawlResult] = {}
_CACHE_TTL = 300  # 5 分钟


async def crawl_with_cache(
    seed_urls: List[str],
    cache_key: str = "default",
    force_refresh: bool = False,
    **crawler_kwargs,
) -> ANPCrawlResult:
    """带缓存的爬虫（避免每次都重新爬）"""
    global _CRAWL_CACHE

    now = time.time()
    if not force_refresh and cache_key in _CRAWL_CACHE:
        cached = _CRAWL_CACHE[cache_key]
        if now - cached.finished_at < _CACHE_TTL:
            logger.info("[crawler] cache hit for %s (age %.1fs)",
                        cache_key, now - cached.finished_at)
            return cached

    crawler = ANPCrawler(**crawler_kwargs)
    result = await crawler.crawl(seed_urls)
    _CRAWL_CACHE[cache_key] = result
    return result


def clear_crawl_cache():
    global _CRAWL_CACHE
    _CRAWL_CACHE = {}


def get_cached_crawl(cache_key: str = "default") -> Optional[ANPCrawlResult]:
    return _CRAWL_CACHE.get(cache_key)


# ============================================================
# 4. DID Resolution (简版)
# ============================================================

def resolve_did_to_url(did: str) -> Optional[str]:
    """
    DID:WBA → URL 解析

    实际生产应查 DID 文档（类似 DNS）
    这里用约定：did:wba:pha.local:<name> → http://<name>:port
    """
    if not did.startswith("did:wba:pha.local:"):
        return None
    name = did.split(":")[-1]
    # 端口约定
    port_map = {
        "hostapi": 13002,
        "health_advisor": 10011,
        "health_records": 10010,
        "medication_reminder": 10012,
        "visit_summary": 10013,
    }
    port = port_map.get(name, 10000)
    return f"http://{name}:{port}"


__all__ = [
    "ANPAgentNode",
    "ANPCrawlResult",
    "ANPCrawler",
    "crawl_with_cache",
    "clear_crawl_cache",
    "get_cached_crawl",
    "resolve_did_to_url",
]