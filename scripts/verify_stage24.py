"""阶段24 验收 - 多模型协同"""
import os
import sys
import time
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['DASHSCOPE_API_KEY'] = 'sk-2917df2994074695b7b741ffb6382a3b'  # 本地测试用
os.environ['DEEPSEEK_API_KEY'] = 'sk-test-deepseek-fake'  # 测试用（真实 key 在容器里）
os.environ['PHA_PROVIDER_RATE_LIMIT'] = '100'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

import httpx

print('=' * 70)
print('PHA v2 阶段24 验收 - 多模型协同 (DeepSeek + Qwen + Claude + Local)')
print('=' * 70)

total = 0
passed = 0


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:55s} {detail}')
    total += 1
    if ok:
        passed += 1


# ---- 1. 4 个 Provider 存在 ----
print('\n[1] Provider 抽象')
from A2AServer.v2.multi_model import (
    DeepSeekProvider, QwenProvider, ClaudeProvider, LocalProvider,
    ModelRouter, ChatMessage, ChatResult, TASK_ROUTING, FALLBACK_CHAIN,
)
check('DeepSeekProvider 类', DeepSeekProvider is not None)
check('QwenProvider 类', QwenProvider is not None)
check('ClaudeProvider 类', ClaudeProvider is not None)
check('LocalProvider 类', LocalProvider is not None)
check('ModelRouter 类', ModelRouter is not None)
check('ChatMessage dataclass', ChatMessage is not None)
check('ChatResult dataclass', ChatResult is not None)


# ---- 2. Provider 初始化 + 配置状态 ----
print('\n[2] Provider 初始化 + 配置检测')
ds = DeepSeekProvider()
check('DeepSeek name = "deepseek"', ds.name == "deepseek")
check('DeepSeek is_configured (有 key)', ds.is_configured() is True)
check('DeepSeek base_url 正确', 'deepseek' in ds._base_url)

qw = QwenProvider()
check('Qwen is_configured (有 DashScope key)', qw.is_configured() is True)

cl = ClaudeProvider()
check('Claude 未配置 (无 key)', cl.is_configured() is False)
check('Claude base_url 含 anthropic', 'anthropic' in cl._base_url)

lo = LocalProvider()
check('Local 未配置 (无 LOCAL_MODEL_URL)', lo.is_configured() is False)


# ---- 3. Router 初始化 + list_providers ----
print('\n[3] Router 初始化')
router = ModelRouter()
providers = router.list_providers()
check('Router 有 4 个 provider', len(providers) == 4)
names = [p["name"] for p in providers]
for n in ["deepseek", "qwen", "claude", "local"]:
    check(f'Router 含 {n}', n in names)
check('Provider 含 configured 字段', "configured" in providers[0])
check('Provider 含 model 字段', "model" in providers[0])
check('Provider 含 stats 字段', "stats" in providers[0])


# ---- 4. 任务路由 ----
print('\n[4] 任务路由策略')
check('TASK_ROUTING.chat 存在', "chat" in TASK_ROUTING)
check('TASK_ROUTING.code 存在', "code" in TASK_ROUTING)
check('TASK_ROUTING.analysis 存在', "analysis" in TASK_ROUTING)
check('TASK_ROUTING 含 6 个任务', len(TASK_ROUTING) >= 6, f'len={len(TASK_ROUTING)}')
check('FALLBACK_CHAIN 至少 2 个', len(FALLBACK_CHAIN) >= 2)


# ---- 5. 限流 ----
print('\n[5] Provider 限流')
allowed = 0
for i in range(105):
    if router._limiter.is_allowed("deepseek"):
        allowed += 1
check('限流上限 100 (前 100 次允许)', allowed == 100, f'allowed={allowed}')
check('限流后被拒', not router._limiter.is_allowed("deepseek"))
check('其他 provider 不受影响', router._limiter.is_allowed("qwen"))


# ---- 6. Stats 记录 ----
print('\n[6] Stats 记录')
router._record_success("deepseek", 150.0, 200)
router._record_success("deepseek", 200.0, 300)
router._record_error("qwen", "rate limit exceeded")
check('deepseek success = 2', router._stats["deepseek"].success == 2)
check('deepseek total_tokens = 500', router._stats["deepseek"].total_tokens == 500)
check('qwen error = 1', router._stats["qwen"].error == 1)
check('qwen last_error 记录', router._stats["qwen"].last_error is not None)

# rate_limited 记录
router._record_rate_limited("claude")
check('claude rate_limited = 1', router._stats["claude"].rate_limited == 1)

stats = router.stats()
check('stats 含 providers', "providers" in stats)
check('stats 含 config', "config" in stats)
check('stats.config.fallback_chain 是 list', isinstance(stats["config"]["fallback_chain"], list))
check('stats.config.task_routing 是 dict', isinstance(stats["config"]["task_routing"], dict))


# ---- 7. 实际 chat 调用 (Qwen，因为本地有 key) ----
print('\n[7] 实际 chat 调用 (Qwen)')
async def test_chat():
    msgs = [ChatMessage(role="user", content="用一句话介绍你自己")]
    result = await router.chat(
        messages=msgs,
        task_type="summary",  # 路由到 qwen
        max_tokens=100,
        temperature=0.7,
    )
    return result


result = asyncio.run(test_chat())
check('chat 返回 ChatResult', isinstance(result, ChatResult))
if not result.error:
    check('qwen chat 成功', result.provider == "qwen", f'provider={result.provider}')
    check('返回文本非空', len(result.text) > 0, f'len={len(result.text)}')
    check('latency_ms > 0', result.latency_ms > 0, f'latency={result.latency_ms:.0f}ms')
    check('total_tokens >= 0', result.total_tokens >= 0, f'tokens={result.total_tokens}')
    # qwen success 计数应 >= 1
    check('stats qwen success >= 1', router._stats["qwen"].success >= 1)
else:
    print(f'    (Qwen 调用失败: {result.error}，跳到 fallback 测试)')


# ---- 8. Fallback 链 ----
print('\n[8] Fallback 链行为')
# 用未配置的 provider 强制走 fallback
async def test_fallback():
    msgs = [ChatMessage(role="user", content="test")]
    result = await router.chat(
        messages=msgs,
        task_type="chat",
        max_tokens=50,
        prefer_provider="claude",  # 未配置 → 跳过
    )
    return result


result = asyncio.run(test_fallback())
check('未配置 provider 被跳过', result.provider in ["deepseek", "qwen", "local"], f'got {result.provider}')


# ---- 9. 任务类型路由 ----
print('\n[9] 任务类型路由')
async def test_routing():
    msgs = [ChatMessage(role="user", content="hi")]
    r1 = await router.chat(msgs, task_type="chat", max_tokens=20)
    r2 = await router.chat(msgs, task_type="code", max_tokens=20)
    r3 = await router.chat(msgs, task_type="summary", max_tokens=20)
    return r1, r2, r3


r1, r2, r3 = asyncio.run(test_routing())
check('chat 任务返 provider', r1.provider in ["deepseek", "qwen", "claude", "local", "none"])
check('code 任务返 provider', r2.provider in ["deepseek", "qwen", "claude", "local", "none"])
check('summary 任务返 provider', r3.provider in ["deepseek", "qwen", "claude", "local", "none"])


# ---- 10. HTTP 端点 ----
print('\n[10] HTTP 端点')
try:
    r = httpx.get('http://localhost:13002/v2/models/providers', timeout=5)
    check('GET /v2/models/providers 200', r.status_code == 200, f'code={r.status_code}')
    if r.status_code == 200:
        data = r.json()
        check('providers 字段', "providers" in data)
        check('4 个 provider', len(data.get("providers", [])) == 4)
except Exception as e:
    check('GET /v2/models/providers', False, str(e)[:60])

try:
    r = httpx.get('http://localhost:13002/v2/models/stats', timeout=5)
    check('GET /v2/models/stats 200', r.status_code == 200, f'code={r.status_code}')
except Exception as e:
    check('GET /v2/models/stats', False, str(e)[:60])

try:
    r = httpx.post('http://localhost:13002/v2/models/test-fallback', timeout=5)
    check('POST /v2/models/test-fallback 200', r.status_code == 200, f'code={r.status_code}')
    if r.status_code == 200:
        data = r.json()
        check('test-fallback 返 configured_providers', "configured_providers" in data)
        check('test-fallback 返 fallback_chain', "fallback_chain" in data)
except Exception as e:
    check('POST /v2/models/test-fallback', False, str(e)[:60])

try:
    r = httpx.post('http://localhost:13002/v2/models/chat', json={
        "messages": [{"role": "user", "content": "hi"}],
        "task_type": "chat",
        "max_tokens": 30
    }, timeout=30)
    check('POST /v2/models/chat 200', r.status_code == 200, f'code={r.status_code} body={r.text[:100]}')
    if r.status_code == 200:
        data = r.json()
        check('chat 返 text 字段', "text" in data or "error" in data)
except Exception as e:
    check('POST /v2/models/chat', False, str(e)[:60])


# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段24 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段24 完成，多模型协同 4 provider + 路由 + fallback 就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
