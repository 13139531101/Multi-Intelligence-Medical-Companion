#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能路由API测试脚本
测试统一的智能体调用接口
"""

import requests
import json
import time

# API基础URL
BASE_URL = "http://localhost:13002"


def run_smart_chat(message):
    """
    测试智能路由接口
    """
    url = f"{BASE_URL}/smart_chat"
    payload = {
        "message": message
    }

    try:
        response = requests.post(url, json=payload)
        print(f"\n测试消息: {message}")
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return result
        else:
            print(f"错误: {response.text}")
            return None

    except Exception as e:
        print(f"请求失败: {str(e)}")
        return None


def run_ping():
    """
    测试服务器连接
    """
    try:
        response = requests.get(f"{BASE_URL}/ping")
        if response.status_code == 200:
            print("✅ 服务器连接正常")
            return True
        else:
            print(f"❌ 服务器响应异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到服务器: {str(e)}")
        return False


def main():
    print("=== 智能路由API测试 ===")

    # 测试服务器连接
    if not run_ping():
        print("请确保API服务器正在运行 (python api.py)")
        return

    # 测试不同类型的消息
    test_messages = [
        "我想查看我的健康档案",
        "我最近有头痛症状，需要一些建议",
        "帮我设置用药提醒",
        "生成我上次就诊的摘要",
        "你好，我需要帮助"  # 默认路由测试
    ]

    results = []
    for message in test_messages:
        result = run_smart_chat(message)
        if result:
            results.append(result)
        time.sleep(1)  # 避免请求过快

    print("\n=== 测试总结 ===")
    for i, result in enumerate(results):
        if result and result.get('success'):
            print(f"✅ 测试 {i+1}: {result.get('selected_agent')}")
        else:
            print(f"❌ 测试 {i+1}: 失败")


if __name__ == "__main__":
    main()
