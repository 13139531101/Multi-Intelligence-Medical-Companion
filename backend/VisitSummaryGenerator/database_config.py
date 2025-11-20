import os
from typing import Dict, Any, Optional
import logging
from datetime import datetime
import psycopg
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

class MemoryDatabaseConfig:
    """记忆系统数据库配置和连接管理"""
    
    def __init__(self):
        self.config = {
            'host': os.getenv('MEMORY_DB_HOST', 'localhost'),
            'port': int(os.getenv('MEMORY_DB_PORT', 5432)),
            'user': os.getenv('MEMORY_DB_USER', 'postgres'),
            'password': os.getenv('MEMORY_DB_PASSWORD', ''),
            'database': os.getenv('MEMORY_DB_NAME', 'agent_memory'),
            'autocommit': True,
        }
        
        self.pool_config = {
            'pool_name': 'memory_pool',
            'pool_size': int(os.getenv('MEMORY_DB_POOL_SIZE', 10)),
        }
        
        self._connection_pool = None
        self._enabled = False
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化数据库连接池（PostgreSQL）"""
        try:
            # 优先使用 DSN：MEMORY_DATABASE_URL 或 DATABASE_URL
            dsn = os.getenv('MEMORY_DATABASE_URL') or os.getenv('DATABASE_URL')

            if not dsn:
                # 由离散参数拼接 DSN
                user = self.config['user']
                password = self.config['password']
                host = self.config['host']
                port = self.config['port']
                database = self.config['database']
                auth = f"{user}:{password}" if password else f"{user}"
                dsn = f"postgresql://{auth}@{host}:{port}/{database}"

            self._connection_pool = ConnectionPool(dsn, max_size=max(self.pool_config['pool_size'], 1))
            self._enabled = True
            logger.info("记忆系统 PostgreSQL 连接池初始化成功")
        except Exception as e:
            logger.error(f"记忆系统 PostgreSQL 连接池初始化失败: {e}")
            logger.warning("记忆系统将以无数据库模式运行（仅日志与内存特性可用）")
            self._connection_pool = None
            self._enabled = False
            # 不抛出异常，允许上层继续启动
    
    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_connection(self):
        """获取数据库连接"""
        if not self._enabled or self._connection_pool is None:
            raise RuntimeError("Memory DB is disabled: connection pool not initialized")
        try:
            conn = self._connection_pool.getconn()
            try:
                conn.autocommit = False
            except Exception:
                pass
            return conn
        except Exception as e:
            logger.error(f"获取数据库连接失败: {e}")
            raise

    def _put_connection(self, connection):
        try:
            if connection and self._connection_pool:
                self._connection_pool.putconn(connection)
        except Exception as e:
            logger.error(f"归还数据库连接失败: {e}")
    
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
                self._put_connection(connection)
    
    def _get_memories_table_sql(self) -> str:
        """获取记忆主表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memories (
            memory_id VARCHAR(36) PRIMARY KEY,
            agent_id VARCHAR(50) NOT NULL,
            user_id VARCHAR(50) NOT NULL,
            memory_type VARCHAR(20) NOT NULL,
            content_text TEXT,
            content_structured JSONB,
            metadata JSONB,
            importance_score REAL DEFAULT 0.5,
            access_count INTEGER DEFAULT 0,
            last_accessed TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMPTZ NULL
        );
        """
    
    def _get_memory_embeddings_table_sql(self) -> str:
        """获取记忆向量表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            memory_id VARCHAR(36) PRIMARY KEY,
            embedding_model VARCHAR(50) NOT NULL,
            embedding_vector JSONB NOT NULL,
            vector_dimension INTEGER NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE
        );
        """
    
    def _get_memory_associations_table_sql(self) -> str:
        """获取记忆关联表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memory_associations (
            id BIGSERIAL PRIMARY KEY,
            source_memory_id VARCHAR(36) NOT NULL,
            target_memory_id VARCHAR(36) NOT NULL,
            relation_type VARCHAR(50) NOT NULL,
            strength REAL DEFAULT 0.5,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
            FOREIGN KEY (target_memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
            UNIQUE (source_memory_id, target_memory_id, relation_type)
        );
        """
    
    def _get_memory_tags_table_sql(self) -> str:
        """获取记忆标签表的创建SQL"""
        return """
        CREATE TABLE IF NOT EXISTS memory_tags (
            id BIGSERIAL PRIMARY KEY,
            memory_id VARCHAR(36) NOT NULL,
            tag VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
            UNIQUE (memory_id, tag)
        );
        """
    
    def check_connection(self) -> bool:
        """检查数据库连接是否正常"""
        if not self._enabled:
            return False
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
                self._put_connection(connection)
    
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