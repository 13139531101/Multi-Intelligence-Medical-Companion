"""debug [smart_chat][PHA v2] setup failed: 5"""
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, 'backend/A2AServer/src')

from unittest.mock import MagicMock
from A2AServer.v2.bridge import is_v2_request, v2_process_message

# mock FastAPI Request
class MockRequest:
    headers = {"x-pha-version": "v2"}


print('is_v2_request:', is_v2_request(MockRequest()))
print('v2_process_message 类型:', type(v2_process_message))

# 真实调用看错误
import asyncio
from A2AServer.common.A2Atypes import Message, TextPart

msg = Message(
    role="user",
    parts=[TextPart(text="我头疼")],
    metadata={"conversation_id": "debug-1", "user_id": "u-debug"},
)

import traceback
try:
    r = asyncio.run(v2_process_message(msg))
    print('result:', r)
except Exception as e:
    traceback.print_exc()
    print(f'异常类型: {type(e).__name__}')
    print(f'异常值: {e!r}')