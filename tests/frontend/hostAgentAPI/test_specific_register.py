#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试特定注册请求
"""

import requests
import json

# API基础URL
BASE_URL = "http://127.0.0.1:13002"


def test_specific_register():
    """测试特定的注册请求"""
    print("=== 测试特定注册请求 ===")

    # 测试数据 - 与日志中的请求完全相同
    test_data = {
        "username": "11111",
        "password": "111111",
        "email": "111111111@qq.com",
        "phone": "13139531101"
    }

    print(f"测试注册数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=test_data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")

        if response.status_code == 400:
            error_detail = response.json().get('detail', '未知错误')
            print(f"\n❌ 注册失败原因: {error_detail}")
        elif response.status_code == 200:
            print("\n✅ 注册成功！")
        else:
            print(f"\n⚠️ 未预期的状态码: {response.status_code}")

    except Exception as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    test_specific_register()
