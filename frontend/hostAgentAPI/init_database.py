#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
用于创建personal_health_assistant数据库的所有表结构
"""

import mysql.connector
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def init_database():
    """
    初始化数据库，创建所有必需的表
    """
    try:
        # 数据库连接配置
        config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', 'root'),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }
        
        print("正在连接到MySQL服务器...")
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()
        
        # 创建数据库（如果不存在）
        db_name = os.getenv('DB_NAME', 'personal_health_assistant')
        print(f"正在创建数据库: {db_name}")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE {db_name}")
        
        # 读取并执行SQL文件
        sql_file_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'personal_health_assistant.sql')
        
        if not os.path.exists(sql_file_path):
            print(f"错误: SQL文件不存在: {sql_file_path}")
            return False
            
        print(f"正在读取SQL文件: {sql_file_path}")
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_content = file.read()
        
        # 分割SQL语句并执行
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        print("正在执行SQL语句...")
        for i, statement in enumerate(sql_statements):
            if statement and not statement.startswith('--'):
                try:
                    cursor.execute(statement)
                    print(f"执行语句 {i+1}/{len(sql_statements)}: 成功")
                except mysql.connector.Error as e:
                    if "already exists" in str(e) or "duplicate" in str(e).lower():
                        print(f"执行语句 {i+1}/{len(sql_statements)}: 跳过（已存在）")
                    else:
                        print(f"执行语句 {i+1}/{len(sql_statements)}: 错误 - {e}")
        
        # 提交事务
        connection.commit()
        print("数据库初始化完成！")
        
        # 验证关键表是否存在
        print("\n验证表结构...")
        key_tables = ['users', 'user_sessions', 'user_profiles', 'health_records', 'user_medications', 'reminders']
        
        for table in key_tables:
            cursor.execute(f"SHOW TABLES LIKE '{table}'")
            result = cursor.fetchone()
            if result:
                print(f"✓ 表 {table} 创建成功")
            else:
                print(f"✗ 表 {table} 创建失败")
        
        return True
        
    except mysql.connector.Error as e:
        print(f"数据库错误: {e}")
        return False
    except Exception as e:
        print(f"其他错误: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()
            print("数据库连接已关闭")

if __name__ == "__main__":
    print("=" * 50)
    print("个人智能健康助手 - 数据库初始化脚本")
    print("=" * 50)
    
    success = init_database()
    
    if success:
        print("\n✓ 数据库初始化成功！现在可以启动API服务器了。")
    else:
        print("\n✗ 数据库初始化失败！请检查错误信息并重试。")