#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查用户数据
"""

import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def check_user_data():
    """检查用户111的数据"""
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 3306)),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'personal_health_assistant')
        )
        
        cursor = conn.cursor()
        
        # 查询用户111的所有记录
        cursor.execute("""
            SELECT username, email, phone, created_at, status 
            FROM users 
            WHERE username = %s 
            ORDER BY created_at DESC
        """, ('111',))
        
        results = cursor.fetchall()
        
        print("=== 用户111的记录 ===")
        if results:
            for i, r in enumerate(results, 1):
                print(f"记录{i}: 用户名={r[0]}, 邮箱={r[1]}, 手机={r[2]}, 创建时间={r[3]}, 状态={r[4]}")
        else:
            print("未找到用户111的记录")
        
        # 查询最近创建的用户
        cursor.execute("""
            SELECT username, email, phone, created_at, status 
            FROM users 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        recent_users = cursor.fetchall()
        
        print("\n=== 最近创建的5个用户 ===")
        for i, r in enumerate(recent_users, 1):
            print(f"用户{i}: 用户名={r[0]}, 邮箱={r[1]}, 手机={r[2]}, 创建时间={r[3]}, 状态={r[4]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"查询失败: {e}")

if __name__ == "__main__":
    check_user_data()