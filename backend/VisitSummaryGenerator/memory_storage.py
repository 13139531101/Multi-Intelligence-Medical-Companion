import uuid
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from psycopg.rows import dict_row

# 确保当前目录在路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from .database_config import MemoryDatabaseConfig
    from .embedding_service import EmbeddingService
except ImportError:
    import importlib.util
    
    # 导入 database_config
    spec = importlib.util.spec_from_file_location("database_config", os.path.join(current_dir, "database_config.py"))
    database_config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(database_config_module)
    MemoryDatabaseConfig = database_config_module.MemoryDatabaseConfig
    
    # 导入 embedding_service
    spec = importlib.util.spec_from_file_location("embedding_service", os.path.join(current_dir, "embedding_service.py"))
    embedding_service_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(embedding_service_module)
    EmbeddingService = embedding_service_module.EmbeddingService

logger = logging.getLogger(__name__)

class MemoryStorage:
    """记忆存储模块 - 负责记忆的存储、更新和删除"""
    
    def __init__(self, db_config: MemoryDatabaseConfig = None):
        self.db_config = db_config or MemoryDatabaseConfig()
        self.embedding_service = EmbeddingService()
    
    def store_memory(self, agent_id: str, user_id: str, content: Dict[str, Any], 
                    memory_type: str = 'long_term', importance: float = 0.5,
                    tags: List[str] = None, expires_hours: int = None) -> str:
        """存储新的记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            content: 记忆内容，包含text和structured_data
            memory_type: 记忆类型 (short_term, working, long_term, meta)
            importance: 重要性评分 (0.0-1.0)
            tags: 标签列表
            expires_hours: 过期时间（小时），None表示永不过期
            
        Returns:
            str: 记忆ID
        """
        connection = None
        try:
            memory_id = str(uuid.uuid4())
            connection = self.db_config.get_connection()
            cursor = connection.cursor()
            
            # 准备记忆数据
            content_text = content.get('text', '')
            content_structured = content.get('structured_data', {})
            metadata = content.get('metadata', {})
            
            # 计算过期时间
            expires_at = None
            if expires_hours:
                expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            # 插入记忆主记录
            insert_memory_sql = """
                INSERT INTO memories (
                    memory_id, agent_id, user_id, memory_type, content_text,
                    content_structured, metadata, importance_score, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor.execute(insert_memory_sql, (
                memory_id, agent_id, user_id, memory_type, content_text,
                json.dumps(content_structured, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                importance, expires_at
            ))
            
            # 生成并存储向量嵌入
            if content_text:
                embedding = self.embedding_service.generate_embedding(content_text)
                if embedding:
                    self._store_embedding(cursor, memory_id, embedding)
            
            # 存储标签
            if tags:
                self._store_tags(cursor, memory_id, tags)
            
            connection.commit()
            logger.info(f"记忆存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
                self.db_config.put_connection(connection)
    
    def update_memory(self, memory_id: str, content: Dict[str, Any] = None,
                     importance: float = None, tags: List[str] = None) -> bool:
        """更新记忆内容
        
        Args:
            memory_id: 记忆ID
            content: 新的记忆内容
            importance: 新的重要性评分
            tags: 新的标签列表
            
        Returns:
            bool: 更新是否成功
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor()
            
            # 构建更新SQL
            update_fields = []
            update_values = []
            
            if content:
                if 'text' in content:
                    update_fields.append('content_text = %s')
                    update_values.append(content['text'])
                    
                    # 重新生成向量嵌入
                    embedding = self.embedding_service.generate_embedding(content['text'])
                    if embedding:
                        self._update_embedding(cursor, memory_id, embedding)
                
                if 'structured_data' in content:
                    update_fields.append('content_structured = %s')
                    update_values.append(json.dumps(content['structured_data'], ensure_ascii=False))
                
                if 'metadata' in content:
                    update_fields.append('metadata = %s')
                    update_values.append(json.dumps(content['metadata'], ensure_ascii=False))
            
            if importance is not None:
                update_fields.append('importance_score = %s')
                update_values.append(importance)
            
            if update_fields:
                update_fields.append('updated_at = CURRENT_TIMESTAMP')
                update_values.append(memory_id)
                
                update_sql = f"UPDATE memories SET {', '.join(update_fields)} WHERE memory_id = %s"
                cursor.execute(update_sql, update_values)
            
            # 更新标签
            if tags is not None:
                self._update_tags(cursor, memory_id, tags)
            
            connection.commit()
            logger.info(f"记忆更新成功: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新记忆失败: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
                self.db_config.put_connection(connection)
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            bool: 删除是否成功
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor()
            
            # 删除记忆（级联删除相关数据）
            delete_sql = "DELETE FROM memories WHERE memory_id = %s"
            cursor.execute(delete_sql, (memory_id,))
            
            connection.commit()
            logger.info(f"记忆删除成功: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
                self.db_config.put_connection(connection)
    
    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取单个记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            Dict: 记忆数据，如果不存在返回None
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(row_factory=dict_row)
            
            # 获取记忆主数据
            select_sql = """
                SELECT * FROM memories WHERE memory_id = %s
            """
            cursor.execute(select_sql, (memory_id,))
            memory = cursor.fetchone()
            
            if not memory:
                return None
            
            # 更新访问计数和时间
            self._update_access_info(cursor, memory_id)
            
            # 获取标签
            memory['tags'] = self._get_memory_tags(cursor, memory_id)
            
            # 解析JSON字段
            if memory['content_structured']:
                memory['content_structured'] = json.loads(memory['content_structured'])
            if memory['metadata']:
                memory['metadata'] = json.loads(memory['metadata'])
            
            connection.commit()
            return memory
            
        except Exception as e:
            logger.error(f"获取记忆失败: {e}")
            return None
        finally:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
                self.db_config.put_connection(connection)
    
    def batch_store_memories(self, memories: List[Dict[str, Any]]) -> List[str]:
        """批量存储记忆
        
        Args:
            memories: 记忆列表，每个记忆包含agent_id, user_id, content等字段
            
        Returns:
            List[str]: 成功存储的记忆ID列表
        """
        stored_ids = []
        for memory_data in memories:
            try:
                memory_id = self.store_memory(
                    agent_id=memory_data['agent_id'],
                    user_id=memory_data['user_id'],
                    content=memory_data['content'],
                    memory_type=memory_data.get('memory_type', 'long_term'),
                    importance=memory_data.get('importance', 0.5),
                    tags=memory_data.get('tags'),
                    expires_hours=memory_data.get('expires_hours')
                )
                stored_ids.append(memory_id)
            except Exception as e:
                logger.error(f"批量存储记忆失败: {e}")
                continue
        
        return stored_ids
    
    def _store_embedding(self, cursor, memory_id: str, embedding: List[float]):
        """存储向量嵌入"""
        insert_embedding_sql = """
            INSERT INTO memory_embeddings (
                memory_id, embedding_model, embedding_vector, vector_dimension
            ) VALUES (%s, %s, %s, %s)
        """
        
        cursor.execute(insert_embedding_sql, (
            memory_id,
            self.embedding_service.model_name,
            json.dumps(embedding),
            len(embedding)
        ))
    
    def _update_embedding(self, cursor, memory_id: str, embedding: List[float]):
        """更新向量嵌入"""
        update_embedding_sql = """
            UPDATE memory_embeddings 
            SET embedding_vector = %s, vector_dimension = %s
            WHERE memory_id = %s
        """
        
        cursor.execute(update_embedding_sql, (
            json.dumps(embedding),
            len(embedding),
            memory_id
        ))
    
    def _store_tags(self, cursor, memory_id: str, tags: List[str]):
        """存储标签"""
        for tag in tags:
            insert_tag_sql = """
                INSERT INTO memory_tags (memory_id, tag)
                VALUES (%s, %s)
                ON CONFLICT (memory_id, tag) DO NOTHING
            """
            cursor.execute(insert_tag_sql, (memory_id, tag))
    
    def _update_tags(self, cursor, memory_id: str, tags: List[str]):
        """更新标签"""
        # 删除旧标签
        delete_tags_sql = "DELETE FROM memory_tags WHERE memory_id = %s"
        cursor.execute(delete_tags_sql, (memory_id,))
        
        # 插入新标签
        if tags:
            self._store_tags(cursor, memory_id, tags)
    
    def _get_memory_tags(self, cursor, memory_id: str) -> List[str]:
        """获取记忆标签"""
        select_tags_sql = "SELECT tag FROM memory_tags WHERE memory_id = %s"
        cursor.execute(select_tags_sql, (memory_id,))
        return [row['tag'] for row in cursor.fetchall()]
    
    def _update_access_info(self, cursor, memory_id: str):
        """更新访问信息"""
        update_access_sql = """
            UPDATE memories 
            SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP
            WHERE memory_id = %s
        """
        cursor.execute(update_access_sql, (memory_id,))
