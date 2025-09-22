import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

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

class MemoryRetrieval:
    """记忆检索模块 - 负责记忆的查询和检索"""
    
    def __init__(self, db_config: MemoryDatabaseConfig = None):
        self.db_config = db_config or MemoryDatabaseConfig()
        self.embedding_service = EmbeddingService()
    
    def search_by_content(self, query: str, agent_id: str, user_id: str, 
                         memory_types: List[str] = None, limit: int = 10,
                         min_similarity: float = 0.5) -> List[Dict[str, Any]]:
        """基于内容语义相似度检索记忆
        
        Args:
            query: 查询文本
            agent_id: 智能体ID
            user_id: 用户ID
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            min_similarity: 最小相似度阈值
            
        Returns:
            List[Dict]: 检索结果列表，按相似度降序排列
        """
        if not query.strip():
            return []
        
        connection = None
        try:
            # 生成查询嵌入
            query_embedding = self.embedding_service.generate_embedding(query)
            if not query_embedding:
                logger.warning("无法生成查询嵌入，使用文本匹配")
                return self._search_by_text_match(query, agent_id, user_id, memory_types, limit)
            
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 构建基础查询
            base_conditions = "m.agent_id = %s AND m.user_id = %s"
            params = [agent_id, user_id]
            
            # 添加记忆类型过滤
            if memory_types:
                placeholders = ','.join(['%s'] * len(memory_types))
                base_conditions += f" AND m.memory_type IN ({placeholders})"
                params.extend(memory_types)
            
            # 添加过期时间过滤
            base_conditions += " AND (m.expires_at IS NULL OR m.expires_at > NOW())"
            
            # 获取候选记忆和嵌入
            select_sql = f"""
                SELECT m.*, e.embedding_vector
                FROM memories m
                LEFT JOIN memory_embeddings e ON m.memory_id = e.memory_id
                WHERE {base_conditions}
                AND m.content_text IS NOT NULL AND m.content_text != ''
                ORDER BY m.importance_score DESC, m.created_at DESC
                LIMIT %s
            """
            
            params.append(limit * 3)  # 获取更多候选项进行相似度计算
            cursor.execute(select_sql, params)
            candidates = cursor.fetchall()
            
            if not candidates:
                return []
            
            # 计算相似度并排序
            results = []
            for candidate in candidates:
                if candidate['embedding_vector']:
                    try:
                        candidate_embedding = json.loads(candidate['embedding_vector'])
                        similarity = self.embedding_service.calculate_similarity(
                            query_embedding, candidate_embedding
                        )
                        
                        if similarity >= min_similarity:
                            # 解析JSON字段
                            candidate = self._parse_memory_json_fields(candidate)
                            candidate['similarity_score'] = similarity
                            
                            # 获取标签
                            candidate['tags'] = self._get_memory_tags(cursor, candidate['memory_id'])
                            
                            results.append(candidate)
                    except Exception as e:
                        logger.error(f"处理候选记忆失败: {e}")
                        continue
            
            # 按相似度降序排序
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            # 更新访问信息
            for result in results[:limit]:
                self._update_access_info(cursor, result['memory_id'])
            
            connection.commit()
            return results[:limit]
            
        except Exception as e:
            logger.error(f"语义检索失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    def search_by_time_range(self, start_time: datetime, end_time: datetime,
                           agent_id: str, user_id: str, memory_types: List[str] = None,
                           limit: int = 50) -> List[Dict[str, Any]]:
        """基于时间范围检索记忆
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            agent_id: 智能体ID
            user_id: 用户ID
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 检索结果列表，按时间降序排列
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 构建查询条件
            conditions = "agent_id = %s AND user_id = %s AND created_at BETWEEN %s AND %s"
            params = [agent_id, user_id, start_time, end_time]
            
            # 添加记忆类型过滤
            if memory_types:
                placeholders = ','.join(['%s'] * len(memory_types))
                conditions += f" AND memory_type IN ({placeholders})"
                params.extend(memory_types)
            
            # 添加过期时间过滤
            conditions += " AND (expires_at IS NULL OR expires_at > NOW())"
            
            select_sql = f"""
                SELECT * FROM memories
                WHERE {conditions}
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            params.append(limit)
            cursor.execute(select_sql, params)
            results = cursor.fetchall()
            
            # 处理结果
            for result in results:
                result = self._parse_memory_json_fields(result)
                result['tags'] = self._get_memory_tags(cursor, result['memory_id'])
                self._update_access_info(cursor, result['memory_id'])
            
            connection.commit()
            return results
            
        except Exception as e:
            logger.error(f"时间范围检索失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    def search_by_tags(self, tags: List[str], agent_id: str, user_id: str,
                      match_all: bool = False, memory_types: List[str] = None,
                      limit: int = 50) -> List[Dict[str, Any]]:
        """基于标签检索记忆
        
        Args:
            tags: 标签列表
            agent_id: 智能体ID
            user_id: 用户ID
            match_all: 是否匹配所有标签（True）或任意标签（False）
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 检索结果列表
        """
        if not tags:
            return []
        
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 构建标签查询
            if match_all:
                # 匹配所有标签
                tag_conditions = """
                    SELECT memory_id FROM memory_tags 
                    WHERE tag IN ({}) 
                    GROUP BY memory_id 
                    HAVING COUNT(DISTINCT tag) = %s
                """.format(','.join(['%s'] * len(tags)))
                tag_params = tags + [len(tags)]
            else:
                # 匹配任意标签
                tag_conditions = """
                    SELECT DISTINCT memory_id FROM memory_tags 
                    WHERE tag IN ({})
                """.format(','.join(['%s'] * len(tags)))
                tag_params = tags
            
            # 构建主查询
            base_conditions = "m.agent_id = %s AND m.user_id = %s"
            params = [agent_id, user_id]
            
            # 添加记忆类型过滤
            if memory_types:
                placeholders = ','.join(['%s'] * len(memory_types))
                base_conditions += f" AND m.memory_type IN ({placeholders})"
                params.extend(memory_types)
            
            # 添加过期时间过滤
            base_conditions += " AND (m.expires_at IS NULL OR m.expires_at > NOW())"
            
            select_sql = f"""
                SELECT m.* FROM memories m
                WHERE {base_conditions}
                AND m.memory_id IN ({tag_conditions})
                ORDER BY m.importance_score DESC, m.created_at DESC
                LIMIT %s
            """
            
            all_params = params + tag_params + [limit]
            cursor.execute(select_sql, all_params)
            results = cursor.fetchall()
            
            # 处理结果
            for result in results:
                result = self._parse_memory_json_fields(result)
                result['tags'] = self._get_memory_tags(cursor, result['memory_id'])
                self._update_access_info(cursor, result['memory_id'])
            
            connection.commit()
            return results
            
        except Exception as e:
            logger.error(f"标签检索失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    def get_recent_memories(self, agent_id: str, user_id: str, hours: int = 24,
                          memory_types: List[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            hours: 时间范围（小时）
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 最近记忆列表
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        return self.search_by_time_range(
            start_time, end_time, agent_id, user_id, memory_types, limit
        )
    
    def get_important_memories(self, agent_id: str, user_id: str, 
                             min_importance: float = 0.7, memory_types: List[str] = None,
                             limit: int = 20) -> List[Dict[str, Any]]:
        """获取重要记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            min_importance: 最小重要性阈值
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 重要记忆列表
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 构建查询条件
            conditions = "agent_id = %s AND user_id = %s AND importance_score >= %s"
            params = [agent_id, user_id, min_importance]
            
            # 添加记忆类型过滤
            if memory_types:
                placeholders = ','.join(['%s'] * len(memory_types))
                conditions += f" AND memory_type IN ({placeholders})"
                params.extend(memory_types)
            
            # 添加过期时间过滤
            conditions += " AND (expires_at IS NULL OR expires_at > NOW())"
            
            select_sql = f"""
                SELECT * FROM memories
                WHERE {conditions}
                ORDER BY importance_score DESC, access_count DESC, created_at DESC
                LIMIT %s
            """
            
            params.append(limit)
            cursor.execute(select_sql, params)
            results = cursor.fetchall()
            
            # 处理结果
            for result in results:
                result = self._parse_memory_json_fields(result)
                result['tags'] = self._get_memory_tags(cursor, result['memory_id'])
                self._update_access_info(cursor, result['memory_id'])
            
            connection.commit()
            return results
            
        except Exception as e:
            logger.error(f"重要记忆检索失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    def search_related_memories(self, memory_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索相关记忆
        
        Args:
            memory_id: 基准记忆ID
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 相关记忆列表
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 获取关联记忆
            select_associations_sql = """
                SELECT m.*, ma.relation_type, ma.strength
                FROM memories m
                JOIN memory_associations ma ON (
                    (ma.source_memory_id = %s AND ma.target_memory_id = m.memory_id) OR
                    (ma.target_memory_id = %s AND ma.source_memory_id = m.memory_id)
                )
                WHERE m.memory_id != %s
                AND (m.expires_at IS NULL OR m.expires_at > NOW())
                ORDER BY ma.strength DESC, m.importance_score DESC
                LIMIT %s
            """
            
            cursor.execute(select_associations_sql, (memory_id, memory_id, memory_id, limit))
            results = cursor.fetchall()
            
            # 处理结果
            for result in results:
                result = self._parse_memory_json_fields(result)
                result['tags'] = self._get_memory_tags(cursor, result['memory_id'])
            
            return results
            
        except Exception as e:
            logger.error(f"相关记忆检索失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    def _search_by_text_match(self, query: str, agent_id: str, user_id: str,
                             memory_types: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """基于文本匹配的备用检索方法"""
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 构建查询条件
            conditions = "agent_id = %s AND user_id = %s AND content_text LIKE %s"
            params = [agent_id, user_id, f"%{query}%"]
            
            # 添加记忆类型过滤
            if memory_types:
                placeholders = ','.join(['%s'] * len(memory_types))
                conditions += f" AND memory_type IN ({placeholders})"
                params.extend(memory_types)
            
            # 添加过期时间过滤
            conditions += " AND (expires_at IS NULL OR expires_at > NOW())"
            
            select_sql = f"""
                SELECT * FROM memories
                WHERE {conditions}
                ORDER BY importance_score DESC, created_at DESC
                LIMIT %s
            """
            
            params.append(limit)
            cursor.execute(select_sql, params)
            results = cursor.fetchall()
            
            # 处理结果
            for result in results:
                result = self._parse_memory_json_fields(result)
                result['tags'] = self._get_memory_tags(cursor, result['memory_id'])
                result['similarity_score'] = 0.5  # 默认相似度
            
            return results
            
        except Exception as e:
            logger.error(f"文本匹配检索失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    def _parse_memory_json_fields(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """解析记忆的JSON字段"""
        try:
            if memory.get('content_structured'):
                memory['content_structured'] = json.loads(memory['content_structured'])
            if memory.get('metadata'):
                memory['metadata'] = json.loads(memory['metadata'])
        except Exception as e:
            logger.error(f"解析JSON字段失败: {e}")
        
        return memory
    
    def _get_memory_tags(self, cursor, memory_id: str) -> List[str]:
        """获取记忆标签"""
        try:
            select_tags_sql = "SELECT tag FROM memory_tags WHERE memory_id = %s"
            cursor.execute(select_tags_sql, (memory_id,))
            return [row['tag'] for row in cursor.fetchall()]
        except Exception:
            return []
    
    def _update_access_info(self, cursor, memory_id: str):
        """更新访问信息"""
        try:
            update_access_sql = """
                UPDATE memories 
                SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP
                WHERE memory_id = %s
            """
            cursor.execute(update_access_sql, (memory_id,))
        except Exception as e:
            logger.error(f"更新访问信息失败: {e}")