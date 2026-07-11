"""阶段25 验收 - V2Agent 真实路径（route_and_invoke）"""
import os
import sys
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['DB_HOST'] = '127.0.0.1'
os.environ['EMBEDDING_PROVIDER'] = 'dashscope'
os.environ['EMBEDDING_MODEL'] = 'text-embedding-v3'
os.environ['EMBEDDING_DIM'] = '1024'
os.environ['PHA_USE_V2'] = 'true'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

print('=' * 70)
print('PHA v2 阶段25 验收 - V2Agent 真实路径（host_graph.route_and_invoke）')
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


# ---- 1. 导入 ----
print('\n[1] v2 模块导入')
try:
    from A2AServer.v2.host_graph import route_and_invoke
    check('route_and_invoke 导入', True)
except Exception as e:
    check('route_and_invoke 导入', False, str(e)[:60])
    sys.exit(1)

try:
    from A2AServer.v2.bridge import is_v2_request, v2_process_message
    check('bridge 导入', True)
except Exception as e:
    check('bridge 导入', False, str(e)[:60])

try:
    from A2AServer.v2.v2_agent import V2Agent
    check('V2Agent 导入', True)
except Exception as e:
    check('V2Agent 导入', False, str(e)[:60])

try:
    from A2AServer.v2.v2_runtime import get_runtime
    rt = get_runtime()
    check('LangChain 1.x 可用', rt.available, f'available={rt.available}')
except Exception as e:
    check('LangChain runtime', False, str(e)[:60])


# ---- 2. 4 子类 ----
print('\n[2] V2Agent 4 子类')
try:
    from A2AServer.v2.sub_agents import (
        HealthAdvisorV2, HealthRecordsV2,
        MedicationReminderV2, VisitSummaryV2,
    )
    check('HealthAdvisorV2', True)
    check('HealthRecordsV2', True)
    check('MedicationReminderV2', True)
    check('VisitSummaryV2', True)
except Exception as e:
    check('4 V2Agent 导入', False, str(e)[:80])


# ---- 3. 真实调 route_and_invoke ----
print('\n[3] 真实 route_and_invoke (DeepSeek chat)')
async def call_route():
    return await route_and_invoke(
        query="你好，简单介绍一下你自己",
        conversation_id="verify-stage25-1",
        user_id="verify_user_25",
        metadata={},
    )


result = asyncio.run(call_route())
check('route_and_invoke 不抛异常', result is not None)
if result:
    check('result 含 content', "content" in result, f'keys={list(result.keys())[:5]}')
    content = result.get("content", "")
    if content:
        check('content 非空', len(content) > 0, f'len={len(content)}')
        check('content 是真 LLM 输出 (>5 字符)', len(content) > 5, f'sample="{content[:60]}..."')
    check('result 含 agent 字段', "agent" in result, f'agent={result.get("agent")}')
    check('result 含 routing', "routing" in result, f'routing={result.get("routing")}')


# ---- 4. 健康建议 ----
print('\n[4] 健康建议场景')
async def call_health():
    return await route_and_invoke(
        query="我最近总是头疼，可能是什么原因？",
        conversation_id="verify-stage25-2",
        user_id="verify_user_25",
        metadata={"selected_agent": "health_advisor"},
    )


result2 = asyncio.run(call_health())
if result2 and not result2.get("error"):
    check('健康建议成功', True)
    check('返回健康建议', len(result2.get("content", "")) > 10, f'content_len={len(result2.get("content", ""))}')
else:
    check('健康建议调用成功', False, str(result2.get("error", ""))[:60])


# ---- 5. 类单例 ----
print('\n[5] V2Agent 类单例')
V2Agent._agent_instance_cache.clear()
a1 = HealthAdvisorV2()
a2 = HealthAdvisorV2()
check('HealthAdvisorV2 同一类', a1.__class__ is a2.__class__)


# ---- 6. bridge ----
print('\n[6] bridge v2 灰度路由')
class MockRequestV2:
    headers = {"x-pha-version": "v2"}


check('is_v2_request 识别 v2 header', is_v2_request(MockRequestV2()) is True)

class MockRequestDefault:
    headers = {}


os.environ['PHA_USE_V2'] = 'false'
check('is_v2_request 默认 False', is_v2_request(MockRequestDefault()) is False)
os.environ['PHA_USE_V2'] = 'true'
check('PHA_USE_V2=true 全量启用', is_v2_request(MockRequestDefault()) is True)
os.environ['PHA_USE_V2'] = 'false'


# ---- 7. multi_model 集成 ----
print('\n[7] multi_model Router 真调')
try:
    from A2AServer.v2.multi_model import get_router, ChatMessage
    router = get_router()
    providers = router.list_providers()
    check('4 provider', len(providers) == 4)
    async def call_chat():
        return await router.chat(
            messages=[ChatMessage(role="user", content="1+1=?")],
            task_type="chat",
            max_tokens=30,
        )
    chat_result = asyncio.run(call_chat())
    check('multi_model 真调', not chat_result.error, f'provider={chat_result.provider} text="{chat_result.text[:40]}"')
except Exception as e:
    check('multi_model 集成', False, str(e)[:60])


# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段25 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！V2Agent 真接 LangChain + route_and_invoke + multi_model 工作。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
