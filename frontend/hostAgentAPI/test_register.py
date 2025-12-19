#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import random
import string

def generate_random_user():
    """生成随机用户数据"""
    random_suffix = ''.join(random.choices(string.digits, k=6))
    return {
        "username": f"testuser_{random_suffix}",
        "password": "123456",
        "email": f"test_{random_suffix}@example.com",
        "phone": f"138{random_suffix}1234"
    }

def test_register():
    """测试用户注册功能"""
    url = "http://localhost:13002/auth/register"
    
    # 生成随机用户数据
    user_data = generate_random_user()
    print(f"测试注册用户: {json.dumps(user_data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, json=user_data)
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ 注册成功！")
            result = response.json()
            print(f"用户ID: {result.get('user', {}).get('user_id')}")
            print(f"访问令牌: {result.get('access_token')[:20]}...")
        elif response.status_code == 400:
            print("\n❌ 注册失败 - 用户数据验证错误")
        else:
            print(f"\n❌ 注册失败 - 状态码: {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")

def test_duplicate_register():
    """测试重复注册（应该失败）"""
    url = "http://localhost:13002/auth/register"
    
    # 使用已存在的用户数据
    user_data = {
        "username": "111",
        "password": "111111",
        "email": "111111111@qq.com",
        "phone": "13139531101"
    }
    
    print(f"\n测试重复注册: {json.dumps(user_data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, json=user_data)
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 400:
            print("\n✅ 正确拒绝重复注册！")
        else:
            print(f"\n❌ 意外的响应状态码: {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")

if __name__ == "__main__":
    print("=== 用户注册功能测试 ===")
    
    # 测试正常注册
    print("\n1. 测试正常注册")
    test_register()
    
    # 测试重复注册
    print("\n2. 测试重复注册")
    test_duplicate_register()
    
    print("\n=== 测试完成 ===")
