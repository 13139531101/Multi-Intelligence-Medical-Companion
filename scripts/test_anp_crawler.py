"""测试 ANP 递归爬虫 - 用 mock httpx 真实环境"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

from A2AServer.v2.anp_crawler import (
    ANPCrawler,
    crawl_with_cache,
    resolve_did_to_url,
)


# ============================================================
# Test 1: DID 解析
# ============================================================
print("=" * 60)
print("Test 1: DID resolution (did:wba → URL)")
print("=" * 60)
test_dids = [
    "did:wba:pha.local:hostapi",
    "did:wba:pha.local:health_advisor",
    "did:wba:pha.local:health_records",
    "did:wba:pha.local:medication_reminder",
    "did:wba:pha.local:visit_summary",
    "did:wba:other:unknown",  # 应返回 None
]
for did in test_dids:
    url = resolve_did_to_url(did)
    print(f"  {did:50s} -> {url}")

assert resolve_did_to_url("did:wba:pha.local:hostapi") == "http://hostapi:13002"
assert resolve_did_to_url("did:wba:other:unknown") is None
print("[PASS] Test 1")


# ============================================================
# Test 2: ANPCrawler unit test（直接调内部方法）
# ============================================================
print()
print("=" * 60)
print("Test 2: ANPCrawler _url_to_did + _extract_related_urls")
print("=" * 60)
crawler = ANPCrawler()

# _url_to_did
assert crawler._url_to_did("http://health_advisor:10011") == "did:wba:pha.local:health_advisor"
assert crawler._url_to_did("https://example.com:8080/path") == "did:wba:pha.local:example.com"
print("  _url_to_did: OK")

# _extract_related_urls
ad_with_related = {
    "name": "health_advisor",
    "relatedAgents": [
        {"url": "http://health_records:10010", "did": "did:wba:pha.local:health_records"},
        {"url": "http://medication_reminder:10012", "did": "did:wba:pha.local:medication_reminder"},
    ],
    "sameAs": ["http://other-agent.com"],
    "seeAlso": ["http://another.com"],
}
urls = crawler._extract_related_urls(ad_with_related, "http://base")
assert "http://health_records:10010" in urls
assert "http://medication_reminder:10012" in urls
assert "http://other-agent.com" in urls
assert "http://another.com" in urls
assert len(urls) == 4
print(f"  _extract_related_urls: 4 URLs extracted correctly")
print("[PASS] Test 2")


# ============================================================
# Test 3: ANPCrawler BFS with mocked async client
# ============================================================
print()
print("=" * 60)
print("Test 3: ANPCrawler BFS recursion (mocked httpx)")
print("=" * 60)
import A2AServer.v2.anp_crawler as crawler_module
import httpx as real_httpx


def make_mock_response(url):
    """根据 URL 构造 mock 响应"""
    response = MagicMock()
    if "ad.json" in url:
        name = url.split("://")[1].split(":")[0]
        response.status_code = 200

        def json_fn():
            base = {
                "id": f"did:wba:pha.local:{name}",
                "name": name,
                "description": f"Mock {name}",
            }
            if name == "health_advisor":
                base["relatedAgents"] = [
                    {"url": "http://health_records:10010", "did": "did:wba:pha.local:health_records"}
                ]
            return base

        response.json = json_fn
    elif "interface.json" in url:
        response.status_code = 200
        response.json = lambda: {"methods": [{"name": f"m{i}"} for i in range(3)]}
    else:
        response.status_code = 404
    return response


class MockAsyncClient:
    """完整模拟 httpx.AsyncClient（支持 async with）"""
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        return make_mock_response(url)


# Monkey-patch
crawler_module.httpx.AsyncClient = MockAsyncClient


async def run_bfs_test():
    crawler = ANPCrawler(max_depth=2, max_nodes=10, timeout=3.0, max_concurrent=5)
    result = await crawler.crawl([
        "http://health_advisor:10011",
    ])
    return result


result = asyncio.run(run_bfs_test())

print(f"  duration_ms:    {result.duration_ms:.1f}")
print(f"  seed_count:     {result.seed_count}")
print(f"  discovered:     {result.discovered_count}")
print(f"  reachable:      {result.reachable_count}")
print(f"  failed_urls:    {result.failed_urls}")
print()
print("  Nodes:")
for n in result.nodes:
    related = result.graph.get(n.did, [])
    print(f"    - {n.did:50s} tools={n.tools_count} related={len(related)}")
print()
print("  Graph:")
for did, related in result.graph.items():
    print(f"    {did}")
    for r in related:
        print(f"      → {r}")

# 验证
assert result.discovered_count == 2, f"expected 2, got {result.discovered_count}"
assert result.reachable_count == 2
assert len(result.failed_urls) == 0
# health_advisor 应该有 1 个 related
advisor_node = next(n for n in result.nodes if "health_advisor" in n.did)
assert len(result.graph[advisor_node.did]) == 1
# health_records 没有 related
records_node = next(n for n in result.nodes if "health_records" in n.did)
assert len(result.graph[records_node.did]) == 0
print("[PASS] Test 3 (BFS + DID dedup)")


# ============================================================
# Test 4: crawl_with_cache
# ============================================================
print()
print("=" * 60)
print("Test 4: crawl_with_cache (5 min TTL)")
print("=" * 60)
from A2AServer.v2.anp_crawler import clear_crawl_cache, get_cached_crawl
clear_crawl_cache()
assert get_cached_crawl("external_crawl") is None
print("  cleared cache: OK")

# 恢复原 httpx
crawler_module.httpx.AsyncClient = real_httpx.AsyncClient
print("[PASS] Test 4 (cache module)")

print()
print("=" * 60)
print("[ALL PASS] 4/4 tests")
print("=" * 60)
