# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : database_config.py
# @Author: Health Assistant Team
# @Desc  : 数据库配置和连接管理

import os
import logging
from contextlib import contextmanager
from typing import Dict, Any, Optional
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """数据库配置类（PostgreSQL）"""

    def __init__(self):
        # PostgreSQL 数据库配置
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'user': os.getenv('DB_USER', 'pha'),
            'password': os.getenv('DB_PASSWORD', 'pha_pwd'),
            'dbname': os.getenv('DB_NAME', os.getenv('POSTGRES_DB', 'personal_health_assistant')),
            'autocommit': False,
        }

    def get_connection_config(self) -> Dict[str, Any]:
        """获取数据库连接配置"""
        return self.config.copy()

class DatabaseManager:
    """数据库管理类（PostgreSQL）"""

    def __init__(self):
        self.config = DatabaseConfig()

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = None
        try:
            cfg = self.config.get_connection_config()
            conn = psycopg.connect(
                host=cfg['host'],
                port=cfg['port'],
                user=cfg['user'],
                password=cfg['password'],
                dbname=cfg['dbname'],
            )
            conn.autocommit = cfg.get('autocommit', False)
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
    def execute_query(self, query: str, params: tuple = None) -> list:
        """执行查询语句，返回字典列表"""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params or ())
                return cur.fetchall()
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """执行更新语句，返回影响行数"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                conn.commit()
                return cur.rowcount
    
    def execute_insert(self, query: str, params: tuple = None) -> Optional[int]:
        """执行插入语句，优先通过 RETURNING 返回插入ID，否则返回影响行数"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                returning = 'RETURNING' in query.upper()
                inserted_id = None
                if returning:
                    row = cur.fetchone()
                    if row and len(row) >= 1:
                        inserted_id = row[0]
                conn.commit()
                return inserted_id if returning else cur.rowcount
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception:
            return False

def get_db_manager():
    """获取数据库管理器实例"""
    return DatabaseManager()
