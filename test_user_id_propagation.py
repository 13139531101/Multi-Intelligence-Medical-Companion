#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 user_id 传递链路
模拟小程序 -> A2AServer -> 用药提醒智能体 的完整请求
"""

import requests
import json
import time

# 配置
MEDICATION_REMINDER_URL = "http://127.0.0.1:10012"
TEST_USER_ID = "test_user_12345"

def test_medication_reminder_user_id():
    """测试用药提醒智能体的 user_id 传递"""
    
    # 构造 JSON-RPC 请求
    request_body = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {
            "id": f"task_{int(time.time())}",
            "sessionId": f"session_{int(time.time())}",
            "acceptedOutputModes": ["text", "data"],
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "帮我查看今天的用药提醒"}],
                "metadata": {
                    "user_id": TEST_USER_ID,
                    "message_id": f"msg_{int(time.time())}"
                }
            },
            "metadata": {
                "user_id": TEST_USER_ID
            }
        },
        "id": f"req_{int(time.time())}"
    }
    
    print(f"发送请求到: {MEDICATION_REMINDER_URL}")
    print(f"测试 user_id: {TEST_USER_ID}")
    print(f"请求体中的 message.metadata.user_id: {request_body['params']['message']['metadata']['user_id']}")
    print(f"请求体中的 params.metadata.user_id: {request_body['params']['metadata']['user_id']}")
    print("-" * 60)
    
    try:
        response = requests.post(
            MEDICATION_REMINDER_URL,
            json=request_body,
            headers={"Content-Type": "application/json"},
            timeout=60,
            stream=True
        )
        
        print(f"HTTP 状态码: {response.status_code}")
        print("-" * 60)
        
        # 读取流式响应
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    if data_str == '[DONE]':
                        print("\n[DONE] 响应结束")
                        break
                    try:
                        data = json.loads(data_str)
                        # 检查返回内容中是否有 user_id=111
                        content = json.dumps(data, ensure_ascii=False)
                        if '"user_id": "111"' in content or '"user_id":"111"' in content:
                            print(f"[ERROR] 响应中仍然包含 user_id=111!")
                        print(f"[RESPONSE] {data_str[:500]}...")
                    except json.JSONDecodeError:
                        print(f"[RAW] {data_str[:200]}")
                        
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")

if __name__ == "__main__":
    test_medication_reminder_user_id()
