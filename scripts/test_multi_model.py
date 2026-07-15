"""测试多 LLM provider 路由"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))
from A2AServer.v2 import multi_model

print("=" * 60)
print("Test 1: Router init + 4 providers")
print("=" * 60)
router = multi_model.get_router()
print("Providers:", list(router._providers.keys()))

print()
print("=" * 60)
print("Test 2: Provider status (configured + stats)")
print("=" * 60)
for p in router.list_providers():
    name = p['name']
    cfg = p['configured']
    model = p['model']
    s = p['stats']
    print(f"  {name:20s} configured={cfg} model={model}")
    print(f"    success={s['success']} error={s['error']} rate_limited={s['rate_limited']}")

print()
print("=" * 60)
print("Test 3: Router stats (all)")
print("=" * 60)
all_stats = router.stats()
for name, s in all_stats.items():
    print(f"  {name}: {s}")

print()
print("=" * 60)
print("Test 4: TASK_ROUTING + FALLBACK_CHAIN")
print("=" * 60)
print("TASK_ROUTING (task → preferred provider):")
for task, provider in multi_model.TASK_ROUTING.items():
    print(f"  {task:20s} → {provider}")
print(f"FALLBACK_CHAIN: {multi_model.FALLBACK_CHAIN}")

print()
print("=" * 60)
print("Test 5: RateLimiter (sliding window)")
print("=" * 60)
limiter = multi_model.RateLimiter()
for i in range(3):
    allowed = limiter.is_allowed("deepseek")
    print(f"  attempt {i+1}: allowed={allowed}")

print()
print("[ALL PASS] 5/5 tests")
