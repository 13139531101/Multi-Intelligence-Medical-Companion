import os
import mysql.connector
from mysql.connector import pooling
from typing import Dict, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryDatabaseConfig:
    """记忆系统数据库配置和连接管理"""
    
    def __init__(self):
        self.config = {
            'host': os.getenv('MEMORY_DB_HOST', 'localhost'),
            'port': int(os.getenv('MEMORY_DB_PORT', 3306)),
            'user': os.getenv('MEMORY_DB_USER', 'root'),
            'password': os.getenv('MEMORY_DB_PASSWORD', ''),
            'database': os.getenv('MEMORY_DB_NAME', 'agent_memory'),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci',
            'autocommit': True,
            'time_zone': '+00:00'
        }
        
        self.pool_config = {
            'pool_name': 'memory_pool',
            'pool_size': int(os.getenv('MEMORY_DB_POOL_SIZE', 10)),
            'pool_reset_session': True,
            'buffered': True
        }
        
        self._connection_pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化数据库连接池"""
        try:
            pool_config = {**self.config, **self.pool_config}
            self._connection_pool = pooling.MySQLConnectionPool(**pool_config)
            logger.info("记忆系统数据库连接池初始化成功")
        except Exception as e:
            logger.error(f"记忆系统数据库连接池初始化失败: {e}")
            raise
    
    def get_connection(self):
        """获取数据库连接"""
        try:
            return self._connection_pool.get_connection()
        except Exception as e:
            logger.error(f"获取数据库连接失败: {e}")
            raise
    
    def create_tables(self):
        """创建记忆系统所需的数据库表"""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # 创建记忆主表
            cursor.execute(self._get_memories_table_sql())
            logger.info("记忆主表创建成功")
            
            # 创建记忆向量表
            cursor.execute(self._get_memory_embeddings_table_sql())
            logger.info("记忆向量表创建成功")
            
            # 创建记忆关联表
            cursor.execute(self._get_memory_associations_table_sql())
            logger.info("记忆关联表创建成功")
            
            # 创建记忆标签表
            cursor.execute(self._get_memory_tags_table_sql())
            logger.info("记忆标签表创建成功")
            
            connection.commit()
            logger.info("所有记忆系统表创建完成")
            
        except Exception as e:
            logger.error(f"创建数据库表失败: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                connection.close()
    
    def _get_memories_table_sql(self) -> str:
        """获取记忆主表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memories (
            memory_id VARCHAR(36) PRIMARY KEY,
            agent_id VARCHAR(50) NOT NULL,
            user_id VARCHAR(50) NOT NULL,
            memory_type ENUM('short_term', 'working', 'long_term', 'meta') NOT NULL,
            content_text TEXT,
            content_structured JSON,
            metadata JSON,
            importance_score FLOAT DEFAULT 0.5,
            access_count INT DEFAULT 0,
            last_accessed TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NULL,
            INDEX idx_agent_user (agent_id, user_id),
            INDEX idx_type_importance (memory_type, importance_score),
            INDEX idx_created_at (created_at),
            INDEX idx_expires_at (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    
    def _get_memory_embeddings_table_sql(self) -> str:
        """获取记忆向量表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            memory_id VARCHAR(36) PRIMARY KEY,
            embedding_model VARCHAR(50) NOT NULL,
            embedding_vector JSON NOT NULL,
            vector_dimension INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    
    def _get_memory_associations_table_sql(self) -> str:
        """获取记忆关联表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memory_associations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            source_memory_id VARCHAR(36) NOT NULL,
            target_memory_id VARCHAR(36) NOT NULL,
            relation_type VARCHAR(50) NOT NULL,
            strength FLOAT DEFAULT 0.5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
            FOREIGN KEY (target_memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
            UNIQUE KEY unique_association (source_memory_id, target_memory_id, relation_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    
    def _get_memory_tags_table_sql(self) -> str:
        """获取记忆标签表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memory_tags (
            id INT AUTO_INCREMENT PRIMARY KEY,
            memory_id VARCHAR(36) NOT NULL,
            tag VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
            UNIQUE KEY unique_memory_tag (memory_id, tag)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    
    def check_connection(self) -> bool:
        """检查数据库连接是否正常"""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"数据库连接检查失败: {e}")
            return False
        finally:
            if connection:
                connection.close()
    
    def get_table_info(self) -> Dict[str, Any]:
        """获取数据库表信息"""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            tables_info = {}
            tables = ['memories', 'memory_embeddings', 'memory_associations', 'memory_tags']
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                tables_info[table] = {'count': count}
            
            return tables_info
        except Exception as e:
            logger.error(f"获取表信息失败: {e}")
            return {}
        finally:
            if connection:
                connection.close()