#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试前端修复后的注册和登录功能
"""

import requests
import json

# API基础URL
BASE_URL = "http://127.0.0.1:13002"


def test_register_response_format():
    """测试注册接口的响应格式"""
    print("=== 测试注册接口响应格式 ===")

    # 测试注册新用户
    register_data = {
        "username": "test_user_123",
        "password": "password123",
        "email": "test123@example.com",
        "phone": "13800138000"
    }

    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
        print(f"注册请求状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("注册成功响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

            # 检查是否包含access_token
            if 'access_token' in data:
                print("✓ 响应包含 access_token 字段")
            else:
                print("✗ 响应缺少 access_token 字段")

        elif response.status_code == 400:
            data = response.json()
            print("注册失败响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"注册请求异常: {e}")


def test_login_response_format():
    """测试登录接口的响应格式"""
    print("\n=== 测试登录接口响应格式 ===")

    # 测试登录已存在用户
    login_data = {
        "username": "111",
        "password": "111111"
    }

    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"登录请求状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("登录成功响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

            # 检查关键字段
            required_fields = ['access_token', 'user_id', 'username', 'email', 'phone']
            for field in required_fields:
                if field in data:
                    print(f"✓ 响应包含 {field} 字段")
                else:
                    print(f"✗ 响应缺少 {field} 字段")

        elif response.status_code == 400 or response.status_code == 401:
            data = response.json()
            print("登录失败响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"登录请求异常: {e}")


def test_error_response_format():
    """测试错误响应格式"""
    print("\n=== 测试错误响应格式 ===")

    # 测试重复注册
    register_data = {
        "username": "111",  # 已存在的用户名
        "password": "password123",
        "email": "test@example.com",
        "phone": "13800138001"
    }

    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
        print(f"重复注册状态码: {response.status_code}")

        if response.status_code == 400:
            data = response.json()
            print("错误响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

            if 'detail' in data:
                print(f"✓ 错误信息: {data['detail']}")
            else:
                print("✗ 响应缺少 detail 字段")

    except Exception as e:
        print(f"错误测试异常: {e}")


if __name__ == "__main__":
    test_register_response_format()
    test_login_response_format()
    test_error_response_format()

    print("\n=== 总结 ===")
    print("前端修复要点:")
    print("1. 注册成功判断: 检查 response.access_token 而不是 response.success")
    print("2. 登录成功判断: 检查 response.access_token 而不是 response.success")
    print("3. 错误处理: 从 error.data.detail 获取具体错误信息")
    print("4. Token保存: 使用 response.access_token 而不是 response.token")
