# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : database_config.py
# @Author: Health Assistant Team
# @Desc  : 数据库配置和连接管理

import os
import mysql.connector
from mysql.connector import Error
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """数据库配置类"""
    
    def __init__(self):
        # MySQL数据库配置
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', 'root'),
            'database': os.getenv('DB_NAME', 'personal_health_assistant'),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci',
            'autocommit': False,
            'raise_on_warnings': True,
            'use_unicode': True
        }
        
        # 连接池配置
        self.pool_config = {
            'pool_name': 'health_records_pool',
            'pool_size': 10,
            'pool_reset_session': True
        }
    
    def get_connection_config(self) -> Dict[str, Any]:
        """获取数据库连接配置"""
        return self.config.copy()
    
    def get_pool_config(self) -> Dict[str, Any]:
        """获取连接池配置"""
        config = self.config.copy()
        config.update(self.pool_config)
        return config

class DatabaseManager:
    """数据库管理类"""
    
    def __init__(self):
        self.config = DatabaseConfig()
        self._connection_pool = None
        # 延迟初始化连接池，避免在导入阶段因为数据库未就绪而导致进程退出
        # 如需使用连接池，可在应用启动完成后主动调用 self._init_connection_pool()
    
    def _init_connection_pool(self):
        """初始化连接池"""
        try:
            pool_config = self.config.get_pool_config()
            self._connection_pool = mysql.connector.pooling.MySQLConnectionPool(**pool_config)
            logger.info("数据库连接池初始化成功")
        except Error as e:
            logger.error(f"数据库连接池初始化失败: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        connection = None
        try:
            if self._connection_pool:
                connection = self._connection_pool.get_connection()
            else:
                connection = mysql.connector.connect(**self.config.get_connection_config())
            
            yield connection
            
        except Error as e:
            if connection:
                connection.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    def execute_query(self, query: str, params: tuple = None) -> list:
        """执行查询语句"""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            cursor.close()
            return result
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """执行更新语句"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            affected_rows = cursor.rowcount
            cursor.close()
            return affected_rows
    
    def execute_insert(self, query: str, params: tuple = None) -> int:
        """执行插入语句并返回插入的ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            last_id = cursor.lastrowid
            cursor.close()
            return last_id
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                logger.info("数据库连接测试成功")
                return True
        except Error as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False
    
    def init_database(self):
        """初始化数据库（创建数据库和表）"""
        try:
            # 首先连接到MySQL服务器（不指定数据库）
            temp_config = self.config.get_connection_config()
            database_name = temp_config.pop('database')
            
            with mysql.connector.connect(**temp_config) as conn:
                cursor = conn.cursor()
                
                # 创建数据库
                try:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    logger.info(f"数据库 {database_name} 创建成功或已存在")
                except Error as e:
                    if "database exists" in str(e).lower():
                        logger.info(f"数据库 {database_name} 已存在")
                    else:
                        raise e
                
                cursor.execute(f"USE {database_name}")
                
                # 读取并执行SQL文件
                sql_file_path = r'i:\A2A\3\A2AServer\database\personal_health_assistant.sql'
                
                if os.path.exists(sql_file_path):
                    with open(sql_file_path, 'r', encoding='utf-8') as f:
                        sql_content = f.read()
                    
                    # 分割SQL语句并执行
                    statements = sql_content.split(';')
                    for statement in statements:
                        statement = statement.strip()
                        if statement and not statement.startswith('--'):
                            try:
                                cursor.execute(statement)
                            except Error as e:
                                if "already exists" not in str(e).lower():
                                    logger.warning(f"执行SQL语句时出现警告: {e}")
                    
                    conn.commit()
                    logger.info("数据库表结构初始化成功")
                else:
                    logger.warning(f"SQL文件不存在: {sql_file_path}")
                
                cursor.close()
                
        except Error as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

# 全局数据库管理器实例
db_manager = DatabaseManager()

def get_db_manager() -> DatabaseManager:
    """获取数据库管理器实例"""
    return db_manager

if __name__ == "__main__":
    # 测试数据库连接
    manager = DatabaseManager()
    if manager.test_connection():
        print("数据库连接成功！")
        # 初始化数据库
        try:
            manager.init_database()
            print("数据库初始化完成！")
        except Exception as e:
            print(f"数据库初始化过程中出现问题: {e}")
    else:
        print("数据库连接失败！")