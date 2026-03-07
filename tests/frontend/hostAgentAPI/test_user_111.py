#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试用户111的注册和登录
"""

import requests
import json

# API基础URL
BASE_URL = "http://127.0.0.1:13002"


def test_register_existing_user():
    """测试注册已存在的用户111"""
    print("=== 测试注册已存在的用户111 ===")

    # 测试数据 - 与日志中的请求完全相同
    test_data = {
        "username": "111",
        "password": "111111",
        "email": "1111111111@qq.com",
        "phone": "13139531101"
    }

    print(f"注册数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=test_data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应内容: {response.text}")

        if response.status_code == 400:
            try:
                error_detail = response.json().get('detail', '未知错误')
                print(f"\n❌ 注册失败原因: {error_detail}")
            except Exception:
                print(f"\n❌ 无法解析错误响应: {response.text}")
        elif response.status_code == 200:
            print("\n✅ 注册成功！")
        else:
            print(f"\n⚠️ 未预期的状态码: {response.status_code}")

    except Exception as e:
        print(f"注册请求失败: {e}")


def test_login_user_111():
    """测试用户111登录"""
    print("\n=== 测试用户111登录 ===")

    # 登录数据
    login_data = {
        "username": "111",
        "password": "111111"
    }

    print(f"登录数据: {json.dumps(login_data, indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应内容: {response.text}")

        if response.status_code == 200:
            try:
                data = response.json()
                print("\n✅ 登录成功！")
                print(f"用户ID: {data.get('user', {}).get('user_id', 'N/A')}")
                print(f"访问令牌: {data.get('access_token', 'N/A')[:50]}...")
            except Exception:
                print(f"\n✅ 登录成功但无法解析响应: {response.text}")
        elif response.status_code == 401:
            try:
                error_detail = response.json().get('detail', '未知错误')
                print(f"\n❌ 登录失败原因: {error_detail}")
            except Exception:
                print(f"\n❌ 无法解析错误响应: {response.text}")
        else:
            print(f"\n⚠️ 未预期的状态码: {response.status_code}")

    except Exception as e:
        print(f"登录请求失败: {e}")


if __name__ == "__main__":
    test_register_existing_user()
    test_login_user_111()
