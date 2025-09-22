#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动创建user_sessions表
解决表不存在的问题
"""

import mysql.connector
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def create_user_sessions_table():
    """
    手动创建user_sessions表
    """
    try:
        # 数据库连接配置
        config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', 'root'),
            'database': os.getenv('DB_NAME', 'personal_health_assistant'),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }
        
        print("正在连接到数据库...")
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()
        
        # 检查表是否已存在
        cursor.execute("SHOW TABLES LIKE 'user_sessions'")
        if cursor.fetchone():
            print("user_sessions表已存在，删除后重新创建...")
            cursor.execute("DROP TABLE user_sessions")
        
        # 创建user_sessions表
        create_table_sql = """
        CREATE TABLE user_sessions (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
            user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
            token_hash VARCHAR(255) NOT NULL COMMENT 'Token哈希',
            expires_at TIMESTAMP NOT NULL COMMENT '过期时间',
            ip_address VARCHAR(45) COMMENT 'IP地址',
            user_agent TEXT COMMENT '用户代理',
            is_active TINYINT DEFAULT 1 COMMENT '是否活跃：1-是，0-否',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            INDEX idx_user_id (user_id),
            INDEX idx_token_hash (token_hash),
            INDEX idx_expires_at (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户会话表'
        """
        
        print("正在创建user_sessions表...")
        cursor.execute(create_table_sql)
        
        # 提交事务
        connection.commit()
        print("user_sessions表创建成功！")
        
        # 验证表是否创建成功
        cursor.execute("SHOW TABLES LIKE 'user_sessions'")
        result = cursor.fetchone()
        if result:
            print("✓ 验证成功：user_sessions表已存在")
            
            # 显示表结构
            cursor.execute("DESCRIBE user_sessions")
            columns = cursor.fetchall()
            print("\n表结构：")
            for column in columns:
                print(f"  {column[0]} - {column[1]} - {column[2]}")
        else:
            print("✗ 验证失败：user_sessions表不存在")
            return False
        
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
    print("创建user_sessions表")
    print("=" * 50)
    
    success = create_user_sessions_table()
    
    if success:
        print("\n✓ user_sessions表创建成功！")
    else:
        print("\n✗ user_sessions表创建失败！")