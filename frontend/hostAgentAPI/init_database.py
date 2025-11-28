#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
用于创建personal_health_assistant数据库的所有表结构
"""

import psycopg
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def init_database():
    """
    初始化数据库，创建所有必需的表
    """
    try:
        config = {
            'host': os.getenv('DB_HOST', 'postgres'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'user': os.getenv('DB_USER', 'pha'),
            'password': os.getenv('DB_PASSWORD', 'pha_pass'),
            'dbname': os.getenv('DB_NAME', os.getenv('POSTGRES_DB', 'personal_health_assistant')),
        }
        print("正在连接到PostgreSQL服务器...")
        connection = psycopg.connect(**config)
        cursor = connection.cursor()
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL UNIQUE,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                salt VARCHAR(32) NOT NULL,
                email VARCHAR(100) UNIQUE,
                phone VARCHAR(20) UNIQUE,
                avatar_url VARCHAR(255),
                last_login_at TIMESTAMP NULL,
                login_count INTEGER DEFAULT 0,
                status SMALLINT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_medications (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                drug_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                start_date DATE,
                end_date DATE,
                notes TEXT,
                is_active SMALLINT DEFAULT 1,
                is_deleted SMALLINT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        cursor.execute(
            """
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
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS health_records (
                id UUID PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                record_type TEXT NOT NULL,
                summary TEXT,
                content TEXT,
                importance TEXT NOT NULL DEFAULT 'medium',
                tags JSONB,
                metadata JSONB,
                record_date DATE,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_attachments (
                id UUID PRIMARY KEY,
                record_id UUID REFERENCES health_records(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                mime_type TEXT,
                upload_time TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                reminder_time TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS medication_reminders (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                medication_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                start_date DATE,
                end_date DATE,
                reminder_times JSONB NOT NULL,
                notes TEXT,
                is_active SMALLINT DEFAULT 1,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        cursor.execute("ALTER TABLE medication_reminders ADD COLUMN IF NOT EXISTS reminder_id INTEGER")
        cursor.execute("ALTER TABLE medication_reminders ADD COLUMN IF NOT EXISTS medication_id INTEGER")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_logs (
                id SERIAL PRIMARY KEY,
                reminder_id INTEGER NOT NULL,
                scheduled_time TIMESTAMPTZ NOT NULL,
                actual_time TIMESTAMPTZ,
                completion_time TIMESTAMPTZ,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS visit_summaries (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                summary_id VARCHAR(64) UNIQUE,
                visit_date DATE,
                summary_content TEXT,
                generated_by VARCHAR(50),
                diagnosis TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS consultations (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                consultation_id VARCHAR(64) UNIQUE,
                session_id VARCHAR(64),
                question TEXT,
                answer TEXT,
                tags JSONB,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        
        connection.commit()
        print("数据库初始化完成！")
        
        print("\n验证表结构...")
        key_tables = ['users', 'user_sessions', 'health_records']
        for table in key_tables:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
                (table,)
            )
            exists = cursor.fetchone()[0]
            if exists:
                print(f"✓ 表 {table} 创建成功")
            else:
                print(f"✗ 表 {table} 创建失败")
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
    print("个人智能健康助手 - 数据库初始化脚本")
    print("=" * 50)
    
    success = init_database()
    
    if success:
        print("\n✓ 数据库初始化成功！现在可以启动API服务器了。")
    else:
        print("\n✗ 数据库初始化失败！请检查错误信息并重试。")