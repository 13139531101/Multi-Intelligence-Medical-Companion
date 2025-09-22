#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试微信小程序连接问题
微信小程序不能访问localhost/127.0.0.1，需要使用真实IP地址
"""

import requests
import socket
import json

def get_local_ip():
    """获取本机IP地址"""
    try:
        # 连接到一个远程地址来获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def test_localhost_access():
    """测试localhost访问"""
    print("=== 测试localhost访问 ===")
    try:
        response = requests.get("http://127.0.0.1:13000/ping", timeout=5)
        if response.status_code == 200:
            print("✓ localhost访问正常")
            return True
        else:
            print(f"✗ localhost访问失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ localhost访问异常: {e}")
        return False

def test_ip_access(ip):
    """测试IP地址访问"""
    print(f"\n=== 测试IP地址访问: {ip} ===")
    try:
        response = requests.get(f"http://{ip}:13000/ping", timeout=5)
        if response.status_code == 200:
            print(f"✓ IP地址 {ip} 访问正常")
            return True
        else:
            print(f"✗ IP地址 {ip} 访问失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ IP地址 {ip} 访问异常: {e}")
        return False

def test_auth_endpoints(base_url):
    """测试认证接口"""
    print(f"\n=== 测试认证接口: {base_url} ===")
    
    # 测试登录
    login_data = {
        "username": "111",
        "password": "111111"
    }
    
    try:
        response = requests.post(f"{base_url}/auth/login", json=login_data, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'access_token' in data:
                print("✓ 登录接口正常，返回access_token")
                return True
            else:
                print("✗ 登录接口响应格式异常")
                return False
        else:
            print(f"✗ 登录接口失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ 登录接口异常: {e}")
        return False

def generate_wechat_config(ip):
    """生成微信小程序配置建议"""
    print(f"\n=== 微信小程序配置建议 ===")
    print("微信小程序不能访问localhost/127.0.0.1地址")
    print("需要修改以下配置：")
    print("\n1. 修改 frontend/wechat_mini_program/utils/api.js:")
    print(f'   const SERVER_URL = "http://{ip}:13000";')
    print("\n2. 在微信开发者工具中：")
    print("   - 打开'详情' -> '本地设置'")
    print("   - 勾选'不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书'")
    print("\n3. 确保防火墙允许端口13000的访问")
    print("\n4. 如果仍有问题，可能需要：")
    print("   - 配置HTTPS（生产环境必需）")
    print("   - 在微信公众平台配置服务器域名")

def main():
    print("微信小程序连接问题诊断工具\n")
    
    # 测试localhost访问
    localhost_ok = test_localhost_access()
    
    # 获取本机IP
    local_ip = get_local_ip()
    if local_ip:
        print(f"\n本机IP地址: {local_ip}")
        
        # 测试IP访问
        ip_ok = test_ip_access(local_ip)
        
        if localhost_ok and ip_ok:
            # 测试认证接口
            test_auth_endpoints(f"http://{local_ip}:13000")
            
        # 生成配置建议
        generate_wechat_config(local_ip)
    else:
        print("\n✗ 无法获取本机IP地址")
    
    print("\n=== 总结 ===")
    if localhost_ok:
        print("✓ API服务器运行正常")
    else:
        print("✗ API服务器可能未启动或端口被占用")
        
    if local_ip and not test_ip_access(local_ip):
        print("✗ 可能需要配置防火墙或网络设置")
        print("  建议：在Windows防火墙中允许端口13000的入站连接")

if __name__ == "__main__":
    main()