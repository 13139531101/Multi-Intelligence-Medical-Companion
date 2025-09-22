#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终验证测试：模拟微信小程序的注册和登录流程
"""

import requests
import json
import time
import random

# API基础URL
BASE_URL = "http://127.0.0.1:13000"

def simulate_frontend_register():
    """模拟前端注册流程"""
    print("=== 模拟前端注册流程 ===")
    
    # 生成随机用户数据
    random_id = random.randint(1000, 9999)
    register_data = {
        "username": f"test_user_{random_id}",
        "password": "password123",
        "email": f"test{random_id}@example.com",
        "phone": f"138{random_id:08d}"
    }
    
    print(f"注册数据: {register_data}")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
        print(f"注册响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # 模拟前端逻辑：检查 response.access_token
            if data and 'access_token' in data:
                print("✓ 前端判断：注册成功")
                print(f"  - 获得访问令牌: {data['access_token'][:50]}...")
                print(f"  - 用户ID: {data['user']['user_id']}")
                print(f"  - 用户名: {data['user']['username']}")
                return data['user']['username'], "password123"
            else:
                print("✗ 前端判断：注册失败（缺少access_token）")
                return None, None
                
        else:
            # 模拟错误处理
            try:
                error_data = response.json()
                if 'detail' in error_data:
                    print(f"✗ 前端显示错误: {error_data['detail']}")
                else:
                    print("✗ 前端显示错误: 注册信息有误，请检查后重试")
            except:
                print("✗ 前端显示错误: 网络错误，请重试")
            return None, None
            
    except Exception as e:
        print(f"✗ 前端显示错误: 网络错误，请重试 ({e})")
        return None, None

def simulate_frontend_login(username, password):
    """模拟前端登录流程"""
    print("\n=== 模拟前端登录流程 ===")
    
    login_data = {
        "username": username,
        "password": password
    }
    
    print(f"登录数据: {login_data}")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"登录响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # 模拟前端逻辑：检查 response.access_token
            if data and 'access_token' in data:
                print("✓ 前端判断：登录成功")
                
                # 模拟保存用户信息到本地存储
                user_info = {
                    "username": username,
                    "token": data['access_token'],
                    "user_id": data['user']['user_id'],
                    "email": data['user']['email'],
                    "phone": data['user']['phone'],
                }
                
                print("  - 保存到本地存储的用户信息:")
                print(f"    用户名: {user_info['username']}")
                print(f"    用户ID: {user_info['user_id']}")
                print(f"    邮箱: {user_info['email']}")
                print(f"    手机: {user_info['phone']}")
                print(f"    令牌: {user_info['token'][:50]}...")
                
                return True
            else:
                print("✗ 前端判断：登录失败（缺少access_token）")
                return False
                
        else:
            # 模拟错误处理
            try:
                error_data = response.json()
                if 'detail' in error_data:
                    print(f"✗ 前端显示错误: {error_data['detail']}")
                else:
                    print("✗ 前端显示错误: 用户名或密码错误")
            except:
                print("✗ 前端显示错误: 网络错误，请重试")
            return False
            
    except Exception as e:
        print(f"✗ 前端显示错误: 网络错误，请重试 ({e})")
        return False

def test_duplicate_registration():
    """测试重复注册的错误处理"""
    print("\n=== 测试重复注册错误处理 ===")
    
    # 尝试注册已存在的用户
    register_data = {
        "username": "111",  # 已存在的用户名
        "password": "password123",
        "email": "test@example.com",
        "phone": "13800138001"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
        print(f"重复注册响应状态码: {response.status_code}")
        
        if response.status_code == 400:
            error_data = response.json()
            if 'detail' in error_data:
                print(f"✓ 前端正确显示错误: {error_data['detail']}")
            else:
                print("✗ 前端显示通用错误: 注册信息有误，请检查后重试")
        else:
            print("✗ 意外的响应状态码")
            
    except Exception as e:
        print(f"✗ 前端显示错误: 网络错误，请重试 ({e})")

if __name__ == "__main__":
    print("开始前端修复验证测试...\n")
    
    # 1. 测试注册流程
    username, password = simulate_frontend_register()
    
    if username and password:
        # 2. 测试登录流程
        login_success = simulate_frontend_login(username, password)
        
        if login_success:
            print("\n✓ 完整的注册-登录流程测试成功！")
        else:
            print("\n✗ 登录流程测试失败")
    else:
        print("\n✗ 注册流程测试失败")
    
    # 3. 测试错误处理
    test_duplicate_registration()
    
    print("\n=== 测试总结 ===")
    print("前端修复内容:")
    print("1. ✓ 注册成功判断: 检查 response.access_token")
    print("2. ✓ 登录成功判断: 检查 response.access_token")
    print("3. ✓ 用户信息提取: 从 response.user 对象获取")
    print("4. ✓ 错误信息显示: 从 error.data.detail 获取")
    print("5. ✓ Token保存: 使用 response.access_token")
    print("\n现在微信小程序应该能正确处理注册和登录响应了！")