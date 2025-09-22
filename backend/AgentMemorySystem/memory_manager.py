import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import statistics

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

class MemoryManager:
    """记忆管理模块 - 负责记忆的维护、优化和分析"""
    
    def __init__(self, db_config: MemoryDatabaseConfig = None):
        self.db_config = db_config or MemoryDatabaseConfig()
        self.embedding_service = EmbeddingService()
    
    def evaluate_importance(self, memory_id: str) -> float:
        """评估记忆的重要性
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            float: 重要性评分 (0.0-1.0)
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 获取记忆信息
            select_sql = """
                SELECT m.*, 
                       COUNT(ma.id) as association_count,
                       COUNT(mt.id) as tag_count
                FROM memories m
                LEFT JOIN memory_associations ma ON (
                    ma.source_memory_id = m.memory_id OR ma.target_memory_id = m.memory_id
                )
                LEFT JOIN memory_tags mt ON mt.memory_id = m.memory_id
                WHERE m.memory_id = %s
                GROUP BY m.memory_id
            """
            
            cursor.execute(select_sql, (memory_id,))
            memory = cursor.fetchone()
            
            if not memory:
                return 0.0
            
            # 计算重要性评分
            importance_score = self._calculate_importance_score(memory)
            
            # 更新数据库中的重要性评分
            update_sql = "UPDATE memories SET importance_score = %s WHERE memory_id = %s"
            cursor.execute(update_sql, (importance_score, memory_id))
            
            connection.commit()
            return importance_score
            
        except Exception as e:
            logger.error(f"评估记忆重要性失败: {e}")
            return 0.0
        finally:
            if connection:
                connection.close()
    
    def _calculate_importance_score(self, memory: Dict[str, Any]) -> float:
        """计算记忆重要性评分的内部方法"""
        try:
            score = 0.0
            
            # 基础重要性 (30%)
            base_score = memory.get('importance_score', 0.5)
            score += base_score * 0.3
            
            # 访问频率 (25%)
            access_count = memory.get('access_count', 0)
            access_score = min(1.0, access_count / 10.0)  # 10次访问为满分
            score += access_score * 0.25
            
            # 时间衰减 (20%)
            created_at = memory.get('created_at')
            if created_at:
                days_old = (datetime.now() - created_at).days
                time_score = max(0.1, 1.0 - (days_old / 365.0))  # 一年后衰减到0.1
                score += time_score * 0.2
            else:
                score += 0.1 * 0.2
            
            # 关联度 (15%)
            association_count = memory.get('association_count', 0)
            association_score = min(1.0, association_count / 5.0)  # 5个关联为满分
            score += association_score * 0.15
            
            # 标签丰富度 (10%)
            tag_count = memory.get('tag_count', 0)
            tag_score = min(1.0, tag_count / 3.0)  # 3个标签为满分
            score += tag_score * 0.1
            
            return min(1.0, max(0.0, score))
            
        except Exception as e:
            logger.error(f"计算重要性评分失败: {e}")
            return 0.5
    
    def compress_memories(self, agent_id: str, user_id: str, 
                         memory_type: str = 'long_term') -> int:
        """压缩和整合记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            memory_type: 要压缩的记忆类型
            
        Returns:
            int: 压缩的记忆数量
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 获取候选压缩记忆
            candidates = self._get_compression_candidates(cursor, agent_id, user_id, memory_type)
            
            if len(candidates) < 2:
                return 0
            
            # 按相似度分组
            groups = self._group_similar_memories(candidates)
            
            compressed_count = 0
            for group in groups:
                if len(group) >= 2:
                    compressed_memory = self._merge_memory_group(cursor, group)
                    if compressed_memory:
                        compressed_count += len(group) - 1  # 减去合并后的记忆
            
            connection.commit()
            logger.info(f"压缩完成，共压缩 {compressed_count} 条记忆")
            return compressed_count
            
        except Exception as e:
            logger.error(f"压缩记忆失败: {e}")
            if connection:
                connection.rollback()
            return 0
        finally:
            if connection:
                connection.close()
    
    def cleanup_expired(self) -> int:
        """清理过期记忆
        
        Returns:
            int: 清理的记忆数量
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor()
            
            # 删除过期记忆
            delete_sql = "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= NOW()"
            cursor.execute(delete_sql)
            
            deleted_count = cursor.rowcount
            connection.commit()
            
            logger.info(f"清理过期记忆完成，共清理 {deleted_count} 条记忆")
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理过期记忆失败: {e}")
            if connection:
                connection.rollback()
            return 0
        finally:
            if connection:
                connection.close()
    
    def cleanup_low_importance(self, agent_id: str, user_id: str, 
                              threshold: float = 0.2, max_age_days: int = 30) -> int:
        """清理低重要性的旧记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            threshold: 重要性阈值
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的记忆数量
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor()
            
            # 计算时间阈值
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            
            # 删除低重要性的旧记忆
            delete_sql = """
                DELETE FROM memories 
                WHERE agent_id = %s AND user_id = %s 
                AND importance_score < %s 
                AND created_at < %s
                AND memory_type != 'meta'
            """
            
            cursor.execute(delete_sql, (agent_id, user_id, threshold, cutoff_date))
            
            deleted_count = cursor.rowcount
            connection.commit()
            
            logger.info(f"清理低重要性记忆完成，共清理 {deleted_count} 条记忆")
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理低重要性记忆失败: {e}")
            if connection:
                connection.rollback()
            return 0
        finally:
            if connection:
                connection.close()
    
    def build_associations(self, memory_id: str) -> List[str]:
        """为记忆构建关联关系
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            List[str]: 新建关联的记忆ID列表
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 获取目标记忆
            target_memory = self._get_memory_with_embedding(cursor, memory_id)
            if not target_memory:
                return []
            
            # 获取候选关联记忆
            candidates = self._get_association_candidates(cursor, target_memory)
            
            new_associations = []
            for candidate in candidates:
                # 计算关联强度
                strength = self._calculate_association_strength(target_memory, candidate)
                
                if strength > 0.6:  # 关联强度阈值
                    # 创建关联
                    if self._create_association(cursor, memory_id, candidate['memory_id'], 
                                              'semantic_similarity', strength):
                        new_associations.append(candidate['memory_id'])
            
            connection.commit()
            logger.info(f"为记忆 {memory_id} 建立了 {len(new_associations)} 个关联")
            return new_associations
            
        except Exception as e:
            logger.error(f"构建记忆关联失败: {e}")
            if connection:
                connection.rollback()
            return []
        finally:
            if connection:
                connection.close()
    
    def analyze_memory_patterns(self, agent_id: str, user_id: str, 
                               days: int = 30) -> Dict[str, Any]:
        """分析记忆模式
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            days: 分析天数
            
        Returns:
            Dict: 分析结果
        """
        connection = None
        try:
            connection = self.db_config.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # 时间范围
            start_date = datetime.now() - timedelta(days=days)
            
            # 获取记忆统计
            stats_sql = """
                SELECT 
                    memory_type,
                    COUNT(*) as count,
                    AVG(importance_score) as avg_importance,
                    AVG(access_count) as avg_access,
                    MAX(created_at) as latest_created
                FROM memories
                WHERE agent_id = %s AND user_id = %s AND created_at >= %s
                GROUP BY memory_type
            """
            
            cursor.execute(stats_sql, (agent_id, user_id, start_date))
            type_stats = cursor.fetchall()
            
            # 获取标签统计
            tag_stats_sql = """
                SELECT mt.tag, COUNT(*) as count
                FROM memory_tags mt
                JOIN memories m ON mt.memory_id = m.memory_id
                WHERE m.agent_id = %s AND m.user_id = %s AND m.created_at >= %s
                GROUP BY mt.tag
                ORDER BY count DESC
                LIMIT 10
            """
            
            cursor.execute(tag_stats_sql, (agent_id, user_id, start_date))
            tag_stats = cursor.fetchall()
            
            # 获取时间分布
            time_stats_sql = """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as count
                FROM memories
                WHERE agent_id = %s AND user_id = %s AND created_at >= %s
                GROUP BY DATE(created_at)
                ORDER BY date
            """
            
            cursor.execute(time_stats_sql, (agent_id, user_id, start_date))
            time_stats = cursor.fetchall()
            
            return {
                'period_days': days,
                'type_statistics': type_stats,
                'top_tags': tag_stats,
                'daily_distribution': time_stats,
                'analysis_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"分析记忆模式失败: {e}")
            return {}
        finally:
            if connection:
                connection.close()
    
    def _get_compression_candidates(self, cursor, agent_id: str, user_id: str, 
                                   memory_type: str) -> List[Dict[str, Any]]:
        """获取压缩候选记忆"""
        select_sql = """
            SELECT m.*, e.embedding_vector
            FROM memories m
            LEFT JOIN memory_embeddings e ON m.memory_id = e.memory_id
            WHERE m.agent_id = %s AND m.user_id = %s AND m.memory_type = %s
            AND m.importance_score < 0.6
            AND m.access_count < 3
            AND m.created_at < DATE_SUB(NOW(), INTERVAL 7 DAY)
            ORDER BY m.created_at
        """
        
        cursor.execute(select_sql, (agent_id, user_id, memory_type))
        return cursor.fetchall()
    
    def _group_similar_memories(self, memories: List[Dict[str, Any]], 
                               similarity_threshold: float = 0.8) -> List[List[Dict[str, Any]]]:
        """将相似记忆分组"""
        groups = []
        used_indices = set()
        
        for i, memory1 in enumerate(memories):
            if i in used_indices or not memory1.get('embedding_vector'):
                continue
            
            group = [memory1]
            used_indices.add(i)
            
            embedding1 = json.loads(memory1['embedding_vector'])
            
            for j, memory2 in enumerate(memories[i+1:], i+1):
                if j in used_indices or not memory2.get('embedding_vector'):
                    continue
                
                embedding2 = json.loads(memory2['embedding_vector'])
                similarity = self.embedding_service.calculate_similarity(embedding1, embedding2)
                
                if similarity >= similarity_threshold:
                    group.append(memory2)
                    used_indices.add(j)
            
            if len(group) >= 2:
                groups.append(group)
        
        return groups
    
    def _merge_memory_group(self, cursor, group: List[Dict[str, Any]]) -> Optional[str]:
        """合并记忆组"""
        try:
            # 选择最重要的记忆作为主记忆
            main_memory = max(group, key=lambda x: x['importance_score'])
            others = [m for m in group if m['memory_id'] != main_memory['memory_id']]
            
            # 合并内容
            merged_content = self._merge_memory_content(main_memory, others)
            
            # 更新主记忆
            update_sql = """
                UPDATE memories 
                SET content_text = %s, content_structured = %s, 
                    importance_score = %s, updated_at = CURRENT_TIMESTAMP
                WHERE memory_id = %s
            """
            
            cursor.execute(update_sql, (
                merged_content['text'],
                json.dumps(merged_content['structured_data'], ensure_ascii=False),
                merged_content['importance'],
                main_memory['memory_id']
            ))
            
            # 删除其他记忆
            for other in others:
                delete_sql = "DELETE FROM memories WHERE memory_id = %s"
                cursor.execute(delete_sql, (other['memory_id'],))
            
            return main_memory['memory_id']
            
        except Exception as e:
            logger.error(f"合并记忆组失败: {e}")
            return None
    
    def _merge_memory_content(self, main_memory: Dict[str, Any], 
                             others: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并记忆内容"""
        # 合并文本内容
        texts = [main_memory.get('content_text', '')]
        texts.extend([m.get('content_text', '') for m in others])
        merged_text = ' | '.join(filter(None, texts))
        
        # 合并结构化数据
        merged_structured = {}
        if main_memory.get('content_structured'):
            try:
                merged_structured.update(json.loads(main_memory['content_structured']))
            except:
                pass
        
        for other in others:
            if other.get('content_structured'):
                try:
                    other_structured = json.loads(other['content_structured'])
                    merged_structured.update(other_structured)
                except:
                    pass
        
        # 计算新的重要性
        importances = [main_memory.get('importance_score', 0.5)]
        importances.extend([m.get('importance_score', 0.5) for m in others])
        merged_importance = statistics.mean(importances)
        
        return {
            'text': merged_text,
            'structured_data': merged_structured,
            'importance': merged_importance
        }
    
    def _get_memory_with_embedding(self, cursor, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取带嵌入的记忆"""
        select_sql = """
            SELECT m.*, e.embedding_vector
            FROM memories m
            LEFT JOIN memory_embeddings e ON m.memory_id = e.memory_id
            WHERE m.memory_id = %s
        """
        
        cursor.execute(select_sql, (memory_id,))
        return cursor.fetchone()
    
    def _get_association_candidates(self, cursor, target_memory: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取关联候选记忆"""
        select_sql = """
            SELECT m.*, e.embedding_vector
            FROM memories m
            LEFT JOIN memory_embeddings e ON m.memory_id = e.memory_id
            WHERE m.agent_id = %s AND m.user_id = %s 
            AND m.memory_id != %s
            AND e.embedding_vector IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM memory_associations ma
                WHERE (ma.source_memory_id = %s AND ma.target_memory_id = m.memory_id)
                OR (ma.target_memory_id = %s AND ma.source_memory_id = m.memory_id)
            )
            ORDER BY m.importance_score DESC
            LIMIT 20
        """
        
        cursor.execute(select_sql, (
            target_memory['agent_id'], target_memory['user_id'], target_memory['memory_id'],
            target_memory['memory_id'], target_memory['memory_id']
        ))
        return cursor.fetchall()
    
    def _calculate_association_strength(self, memory1: Dict[str, Any], 
                                       memory2: Dict[str, Any]) -> float:
        """计算关联强度"""
        try:
            if not memory1.get('embedding_vector') or not memory2.get('embedding_vector'):
                return 0.0
            
            embedding1 = json.loads(memory1['embedding_vector'])
            embedding2 = json.loads(memory2['embedding_vector'])
            
            return self.embedding_service.calculate_similarity(embedding1, embedding2)
            
        except Exception as e:
            logger.error(f"计算关联强度失败: {e}")
            return 0.0
    
    def _create_association(self, cursor, source_id: str, target_id: str, 
                           relation_type: str, strength: float) -> bool:
        """创建记忆关联"""
        try:
            insert_sql = """
                INSERT INTO memory_associations 
                (source_memory_id, target_memory_id, relation_type, strength)
                VALUES (%s, %s, %s, %s)
            """
            
            cursor.execute(insert_sql, (source_id, target_id, relation_type, strength))
            return True
            
        except Exception as e:
            logger.error(f"创建记忆关联失败: {e}")
            return False