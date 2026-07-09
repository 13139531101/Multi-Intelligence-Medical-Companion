"""阶段4 验收脚本 - v2 bridge 接入测试"""
import os
import sys
import asyncio
from pathlib import Path

# 加载 .env
from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

# 配置 sys.path
PHA_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHA_ROOT / "backend" / "A2AServer" / "src"))

from A2AServer.v2.bridge import (
    is_v2_enabled,
    is_v2_request,
    v2_process_message,
)

print('=' * 70)
print('PHA v2 阶段4 验收 - v2 bridge 接入')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 开关函数测试 ----
print('\n[1] v2 开关函数')
total += 1
if check('is_v2_enabled() 默认 False', is_v2_enabled() is False):
    passed += 1

total += 1
os.environ['PHA_USE_V2'] = 'true'
if check('PHA_USE_V2=true 后 is_v2_enabled()', is_v2_enabled() is True):
    passed += 1
del os.environ['PHA_USE_V2']

class MockRequest:
    def __init__(self, headers):
        self.headers = headers

total += 1
if check('is_v2_request(header X-Use-V2=true)', is_v2_request(MockRequest({'x-use-v2': 'true'}))):
    passed += 1

total += 1
if check('is_v2_request(header X-PHA-Version=v2)', is_v2_request(MockRequest({'x-pha-version': 'v2'}))):
    passed += 1

total += 1
if check('is_v2_request(无 header) 默认 False', is_v2_request(MockRequest({})) is False):
    passed += 1

# ---- 2. v2_process_message 端到端 ----
print('\n[2] v2_process_message 端到端')

async def e2e():
    global total, passed

    # 构造 A2A Message
    from A2AServer.common.A2Atypes import Message, Part, TextPart

    test_msg = Message(
        role='user',
        parts=[TextPart(text='我最近有点头疼，可能是什么原因？')],
        metadata={
            'conversation_id': 'stage4-e2e-001',
            'user_id': 'u_stage4',
        },
    )

    result = await v2_process_message(test_msg)
    total += 1
    if check('v2_process_message 返回 result', 'message' in result):
        passed += 1
    total += 1
    if check('used_v2=True', result.get('used_v2') is True):
        passed += 1
    total += 1
    if check('无 error', result.get('error') is None, f'error={result.get("error")}'):
        passed += 1
    total += 1
    if check(
        'message 已构造',
        result.get('message') is not None,
    ):
        passed += 1
    total += 1
    msg = result.get('message')
    if msg is not None:
        text_len = sum(
            len(getattr(p, 'text', ''))
            for p in msg.parts
            if hasattr(p, 'text')
        )
        if check(f'消息内容非空 (len={text_len})', text_len > 50):
            passed += 1
        # 检查 metadata
        total += 1
        if check(
            'metadata 含 v2_routing',
            msg.metadata and 'v2_routing' in msg.metadata,
            f'agent={msg.metadata.get("agent") if msg.metadata else None}',
        ):
            passed += 1

asyncio.run(e2e())

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段4 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！v2 bridge 接入就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
