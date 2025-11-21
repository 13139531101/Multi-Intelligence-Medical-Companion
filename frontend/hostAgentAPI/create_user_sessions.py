#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动创建user_sessions表
解决表不存在的问题
"""

import psycopg
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def create_user_sessions_table():
    """
    手动创建user_sessions表
    """
    try:
        config = {
            'host': os.getenv('DB_HOST', 'postgres'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'user': os.getenv('DB_USER', 'pha'),
            'password': os.getenv('DB_PASSWORD', 'pha_pass'),
            'dbname': os.getenv('DB_NAME', os.getenv('POSTGRES_DB', 'personal_health_assistant')),
        }
        print("正在连接到数据库...")
        connection = psycopg.connect(**config)
        cursor = connection.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS user_sessions")
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            token_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            ip_address VARCHAR(45),
            user_agent TEXT,
            is_active SMALLINT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        print("正在创建user_sessions表...")
        cursor.execute(create_table_sql)
        
        connection.commit()
        print("user_sessions表创建成功！")
        
        cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='user_sessions')")
        exists = cursor.fetchone()[0]
        if exists:
            print("✓ 验证成功：user_sessions表已存在")
            cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='user_sessions' ORDER BY ordinal_position")
            columns = cursor.fetchall()
            print("\n表结构：")
            for column in columns:
                print(f"  {column[0]} - {column[1]}")
        else:
            print("✗ 验证失败：user_sessions表不存在")
            return False
        
        return True
        
    except Exception as e:
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
    print("创建user_sessions表")
    print("=" * 50)
    
    success = create_user_sessions_table()
    
    if success:
        print("\n✓ user_sessions表创建成功！")
    else:
        print("\n✗ user_sessions表创建失败！")