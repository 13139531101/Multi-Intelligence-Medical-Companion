"""阶段5 验收脚本 - a2a-sdk 0.3.x 协议升级"""
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

# sys.path
PHA_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHA_ROOT / "backend" / "A2AServer" / "src"))

print('=' * 70)
print('PHA v2 阶段5 验收 - a2a-sdk 0.3.x 协议升级')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. a2a-sdk 可用性 ----
print('\n[1] a2a-sdk 0.3.x 可用性')
from A2AServer.v2.a2a_sdk_compat import (
    is_a2a_sdk_available,
    get_protocol_version,
)
total += 1
if check('a2a-sdk 可用', is_a2a_sdk_available()):
    passed += 1
total += 1
if check('protocol version', 'a2a-sdk' in get_protocol_version(), get_protocol_version()):
    passed += 1

# ---- 2. PHA -> a2a-sdk 转换 ----
print('\n[2] PHA Message -> a2a-sdk Message 转换')
from A2AServer.common.A2Atypes import Message, TextPart as PhaTextPart
from A2AServer.v2.a2a_sdk_compat import pha_to_sdk_message, pha_to_sdk_request

pha_msg = Message(
    role='user',
    parts=[PhaTextPart(text='我最近头疼')],
    metadata={'conversation_id': 'stage5-c1', 'user_id': 'u5'},
)

sdk_msg = pha_to_sdk_message(pha_msg)
total += 1
if check('pha_to_sdk_message 返回 Message', sdk_msg is not None):
    passed += 1
if sdk_msg:
    total += 1
    if check('SDK Message role=user', str(sdk_msg.role).endswith('user'), f'role={sdk_msg.role}'):
        passed += 1
    total += 1
    if check('SDK Message parts 非空', len(sdk_msg.parts) > 0, f'parts={len(sdk_msg.parts)}'):
        passed += 1
    total += 1
    if check(
        'SDK Message 含原 metadata',
        sdk_msg.metadata and sdk_msg.metadata.get('conversation_id') == 'stage5-c1',
    ):
        passed += 1

# ---- 3. PHA -> a2a-sdk Request 转换 ----
print('\n[3] PHA TaskSendParams -> a2a-sdk SendMessageRequest 转换')
pha_params = {
    'id': 'test-req-001',
    'sessionId': 'session-abc',
    'message': pha_msg,
    'acceptedOutputModes': ['text', 'text/plain'],
    'metadata': {'test': 'stage5'},
}
sdk_req = pha_to_sdk_request(pha_params)
total += 1
if check('pha_to_sdk_request 返回 Request', sdk_req is not None):
    passed += 1
if sdk_req:
    total += 1
    if check('Request id 一致', str(sdk_req.id) == 'test-req-001'):
        passed += 1
    total += 1
    if check('Request jsonrpc=2.0', sdk_req.jsonrpc == '2.0'):
        passed += 1
    total += 1
    if check('Request method=message/send', sdk_req.method == 'message/send'):
        passed += 1
    total += 1
    if check(
        'Request sdk_msg.contextId 一致',
        str(getattr(sdk_req.params.message, 'context_id', None) or getattr(sdk_req.params.message, 'contextId', None)) == 'session-abc',
        f'contextId={getattr(sdk_req.params.message, "context_id", "n/a")}',
    ):
        passed += 1

# ---- 4. AgentCard 构造 ----
print('\n[4] AgentCard 构造')
from A2AServer.v2.a2a_sdk_compat import build_pha_agent_card

card = build_pha_agent_card()
total += 1
if check('build_pha_agent_card()', card is not None):
    passed += 1
if card:
    total += 1
    if check('Card name', 'PHA' in card.name):
        passed += 1
    total += 1
    if check(
        'Card capabilities.streaming',
        bool(getattr(card.capabilities, 'streaming', False)),
    ):
        passed += 1

# ---- 5. 端到端：a2a-sdk 协议 -> v2 HostGraph ----
print('\n[5] 端到端：a2a-sdk 客户端协议调用')

async def e2e():
    global total, passed

    # 构造 a2a-sdk 标准请求
    from a2a.types import (
        SendMessageRequest, MessageSendParams, Message as SdkMessage,
        TextPart as SdkTextPart, Part as SdkPart, Role as SdkRole,
    )
    import uuid

    sdk_request = SendMessageRequest(
        id=str(uuid.uuid4()),
        params=MessageSendParams(
            message=SdkMessage(
                messageId=str(uuid.uuid4()),
                role=SdkRole.user,
                parts=[SdkPart(root=SdkTextPart(text='我最近头疼，可能是什么原因？'))],
                contextId='stage5-e2e-001',
                metadata={'user_id': 'u_stage5'},
            ),
        ),
    )

    # 把 SDK Message 转为 PHA Message（模拟 server 处理）
    sdk_msg = sdk_request.params.message
    pha_msg = Message(
        role='user',
        parts=[PhaTextPart(text=getattr(sdk_msg.parts[0].root, 'text', ''))],
        metadata={
            **(sdk_request.params.metadata or {}),
            'conversation_id': getattr(
                sdk_request.params.message,
                'context_id',
                getattr(sdk_request.params.message, 'contextId', None),
            ),
        },
    )

    from A2AServer.v2.bridge import v2_process_message
    result = await v2_process_message(pha_msg)
    total += 1
    if check('e2e v2_process_message 无 error', result.get('error') is None):
        passed += 1
    total += 1
    msg = result.get('message')
    if msg:
        text_len = sum(
            len(getattr(p, 'text', ''))
            for p in msg.parts
            if hasattr(p, 'text')
        )
        if check(f'e2e 返回内容 len={text_len}', text_len > 50):
            passed += 1
    else:
        check('e2e 返回内容', False, 'no message')

    # 反向转换：把 v2 返回转 a2a-sdk Message
    if msg:
        from A2AServer.v2.a2a_sdk_compat import sdk_to_pha_message
        back_pha = sdk_to_pha_message(_fake_sdk_message(msg.parts[0].text))
        total += 1
        if check('sdk_to_pha_message 反向转换', back_pha is not None):
            passed += 1


def _fake_sdk_message(text: str):
    """构造一个临时的 SDK Message 用于反向测试"""
    from a2a.types import Message, TextPart, Part, Role
    import uuid
    return Message(
        messageId=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=text or " "))],
    )


asyncio.run(e2e())

# ---- 6. server app 可创建 ----
print('\n[6] a2a-sdk server app 创建')
try:
    from A2AServer.v2.a2a_sdk_server import create_a2a_sdk_app
    app = create_a2a_sdk_app()
    total += 1
    if check('create_a2a_sdk_app() 返回 FastAPI', app is not None):
        passed += 1
    if app:
        total += 1
        if check('app 包含 / 路由', '/'.lower() in [r.path.lower() for r in app.routes]):
            passed += 1
        total += 1
        if check('app 包含 agent-card 路由', any('/.well-known/agent-card.json' in r.path for r in app.routes)):
            passed += 1
except Exception as e:
    check('create_a2a_sdk_app()', False, str(e))

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段5 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段5 完成，a2a-sdk 0.3.x 协议升级就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
