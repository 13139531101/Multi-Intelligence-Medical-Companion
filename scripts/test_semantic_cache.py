"""阶段39-3: LLM 响应缓存测试"""
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

from A2AServer.v2.semantic_cache import (
    SemanticCache, get_cache, hash_messages, hash_messages_similar,
    normalize_messages, cached_chat,
)


# Test 1: hash_messages
print("=" * 60)
print("Test 1: hash_messages (精确 hash)")
print("=" * 60)
msgs1 = [{"role": "user", "content": "你好"}]
msgs2 = [{"role": "user", "content": "你好"}]
msgs3 = [{"role": "user", "content": "你好！"}]
h1 = hash_messages(msgs1)
h2 = hash_messages(msgs2)
h3 = hash_messages(msgs3)
print(f"  h1: {h1}")
print(f"  h2: {h2} (should equal h1)")
print(f"  h3: {h3} (should differ)")
assert h1 == h2
assert h1 != h3
print("[PASS] Test 1")


# Test 2: normalize_messages
print()
print("=" * 60)
print("Test 2: normalize_messages (去空格)")
print("=" * 60)
msgs_a = [{"role": "user", "content": "你好  世界"}]
msgs_b = [{"role": "user", "content": "你好 世界"}]
msgs_c = [{"role": "user", "content": "你好 世界\n"}]
norm_a = normalize_messages(msgs_a)
norm_b = normalize_messages(msgs_b)
norm_c = normalize_messages(msgs_c)
print(f"  a: {norm_a!r}")
print(f"  b: {norm_b!r}")
print(f"  c: {norm_c!r}")
assert norm_a == norm_b == norm_c
print("[PASS] Test 2")


# Test 3: SemanticCache set/get (精确)
print()
print("=" * 60)
print("Test 3: SemanticCache.set + get (精确)")
print("=" * 60)
cache = SemanticCache(max_size=10, ttl_sec=60)
msgs = [{"role": "user", "content": "什么是 LLM？"}]
cache.set(msgs, "LLM 是大语言模型", "deepseek", "deepseek-chat", task_type="chat")
entry = cache.get(msgs, task_type="chat")
print(f"  retrieved: {entry.text if entry else None}")
assert entry is not None
assert entry.text == "LLM 是大语言模型"
assert entry.provider == "deepseek"
print(f"  hit_count: {entry.hit_count}")
stats = cache.stats()
print(f"  stats: {stats}")
assert stats["hits"] == 1
assert stats["misses"] == 0
print("[PASS] Test 3")


# Test 4: SemanticCache get (miss)
print()
print("=" * 60)
print("Test 4: SemanticCache.get (miss)")
print("=" * 60)
cache = SemanticCache()
miss_msgs = [{"role": "user", "content": "完全不同的 question"}]
entry = cache.get(miss_msgs)
print(f"  miss entry: {entry}")
assert entry is None
print("[PASS] Test 4")


# Test 5: 相似 hash 命中（忽略 temperature）
print()
print("=" * 60)
print("Test 5: 相似 hash 命中（忽略 temp/tokens）")
print("=" * 60)
cache = SemanticCache()
msgs = [{"role": "user", "content": "Python 是什么"}]
cache.set(msgs, "Python 是编程语言", "deepseek", "deepseek-chat",
          task_type="chat", max_tokens=1024, temperature=0.5)
# 不同的 temp/tokens 应该命中（相似 key）
entry = cache.get(msgs, task_type="chat", max_tokens=2048, temperature=0.7)
print(f"  similar hit: {entry is not None}")
print(f"  text: {entry.text if entry else None}")
assert entry is not None
assert entry.text == "Python 是编程语言"
print("[PASS] Test 5")


# Test 6: LRU eviction
print()
print("=" * 60)
print("Test 6: LRU eviction (max_size=6)")
print("=" * 60)
# 因为我们存 2 个 key (精确 + 相似)，max_size 要按 2 倍
cache = SemanticCache(max_size=6, ttl_sec=60)
for i in range(5):
    cache.set([{"role": "user", "content": f"q{i}"}], f"a{i}", "p", "m")
stats = cache.stats()
print(f"  stats after 5 sets: size={stats['size']}, evictions={stats['evictions']}, stores={stats['stores']}")
# 5 sets × 2 keys = 10 entries → max_size=6 → 4 evictions
assert stats["stores"] == 5
assert stats["evictions"] == 4
assert stats["size"] == 6
print("[PASS] Test 6")


# Test 7: TTL expiration
print()
print("=" * 60)
print("Test 7: TTL expiration")
print("=" * 60)
cache = SemanticCache(max_size=10, ttl_sec=1)
msgs = [{"role": "user", "content": "测试过期"}]
cache.set(msgs, "test answer", "p", "m")
assert cache.get(msgs) is not None
time.sleep(2)
entry = cache.get(msgs)
print(f"  after 2s: {entry}")
assert entry is None
stats = cache.stats()
print(f"  expirations: {stats['expirations']} (2 keys → 2 evictions)")
# 2 keys (精确+相似) → 2 expirations
assert stats["expirations"] == 2
print("[PASS] Test 7")


# Test 8: cached_chat (集成函数)
print()
print("=" * 60)
print("Test 8: cached_chat (集成 wrapper)")
print("=" * 60)
get_cache().clear()

call_count = {"n": 0}

def fake_chat(messages, task_type, max_tokens, temperature):
    call_count["n"] += 1
    from dataclasses import dataclass
    @dataclass
    class R:
        text: str
        provider: str
        model: str
        prompt_tokens: int = 10
        completion_tokens: int = 5
        latency_ms: float = 100.0
        fallback_used: bool = False
        error: str = None
    return R(text=f"answer {call_count['n']}", provider="p", model="m")

import asyncio

async def run_test():
    msgs = [{"role": "user", "content": "集成测试"}]
    # 第一次：miss → 调 fake
    r1 = cached_chat(msgs, fake_chat)
    # 第二次：hit → 不调 fake
    r2 = cached_chat(msgs, fake_chat)
    # 第三次：hit → 不调 fake
    r3 = cached_chat(msgs, fake_chat)
    print(f"  call_count: {call_count['n']} (should be 1)")
    print(f"  r1.text: {r1.text}")
    print(f"  r2.text: {r2.text} (should be same)")
    print(f"  r3.text: {r3.text} (should be same)")
    assert call_count["n"] == 1
    assert r1.text == r2.text == r3.text
    assert "(cached)" in r2.provider

asyncio.run(run_test())
print("[PASS] Test 8")


print()
print("=" * 60)
print("[ALL PASS] 8/8 tests")
print("=" * 60)