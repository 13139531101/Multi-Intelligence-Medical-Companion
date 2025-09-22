import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from AgentMemorySystem.database_config import MemoryDatabaseConfig
from AgentMemorySystem.memory_storage import MemoryStorage
from AgentMemorySystem.memory_retrieval import MemoryRetrieval
from AgentMemorySystem.memory_manager import MemoryManager
from AgentMemorySystem.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class AgentMemorySystem:
    """智能体记忆系统主接口类
    
    提供统一的记忆管理API，整合存储、检索、管理等功能
    """
    
    def __init__(self, db_config: MemoryDatabaseConfig = None):
        """初始化记忆系统
        
        Args:
            db_config: 数据库配置，如果为None则使用默认配置
        """
        self.db_config = db_config or MemoryDatabaseConfig()
        self.storage = MemoryStorage(self.db_config)
        self.retrieval = MemoryRetrieval(self.db_config)
        self.manager = MemoryManager(self.db_config)
        self.embedding_service = EmbeddingService()
        
        # 初始化数据库表
        self._initialize_database()

    async def initialize(self):
        """兼容调用方的异步初始化方法；确保数据库与嵌入服务就绪"""
        try:
            # 确认数据库连接与表结构
            if not self.db_config.check_connection():
                logger.error("数据库连接失败")
                return False
            self.db_config.create_tables()
            # 触发一次模型信息读取，确保嵌入模型已加载
            try:
                _ = self.embedding_service.get_model_info()
            except Exception as e:
                logger.warning(f"获取嵌入模型信息时出现问题: {e}")
            logger.info("记忆系统异步初始化完成")
            return True
        except Exception as e:
            logger.error(f"记忆系统异步初始化失败: {e}")
            return False

    def _initialize_database(self):
        """初始化数据库表结构"""
        try:
            if not self.db_config.check_connection():
                logger.error("数据库连接失败")
                return
            
            self.db_config.create_tables()
            logger.info("记忆系统数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
    
    # ==================== 记忆存储接口 ====================
    
    def store_memory(self, agent_id: str, user_id: str, content: Dict[str, Any],
                    memory_type: str = 'long_term', importance: float = 0.5,
                    tags: List[str] = None, expires_hours: int = None) -> str:
        """存储新记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            content: 记忆内容 {'text': str, 'structured_data': dict, 'metadata': dict}
            memory_type: 记忆类型 ('short_term', 'working', 'long_term', 'meta')
            importance: 重要性评分 (0.0-1.0)
            tags: 标签列表
            expires_hours: 过期时间（小时），None表示永不过期
            
        Returns:
            str: 记忆ID
        """
        try:
            memory_id = self.storage.store_memory(
                agent_id=agent_id,
                user_id=user_id,
                content=content,
                memory_type=memory_type,
                importance=importance,
                tags=tags,
                expires_hours=expires_hours
            )
            
            # 异步构建关联（可选）
            if memory_type in ['long_term', 'working']:
                try:
                    self.manager.build_associations(memory_id)
                except Exception as e:
                    logger.warning(f"构建记忆关联失败: {e}")
            
            return memory_id
            
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")
            raise
    
    def update_memory(self, memory_id: str, content: Dict[str, Any] = None,
                     importance: float = None, tags: List[str] = None) -> bool:
        """更新记忆
        
        Args:
            memory_id: 记忆ID
            content: 新的记忆内容
            importance: 新的重要性评分
            tags: 新的标签列表
            
        Returns:
            bool: 更新是否成功
        """
        return self.storage.update_memory(memory_id, content, importance, tags)
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            bool: 删除是否成功
        """
        return self.storage.delete_memory(memory_id)
    
    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取单个记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            Dict: 记忆数据，如果不存在返回None
        """
        return self.storage.get_memory(memory_id)
    
    # ==================== 记忆检索接口 ====================
    
    def search_memories(self, query: str, agent_id: str, user_id: str,
                       memory_types: List[str] = None, limit: int = 10,
                       min_similarity: float = 0.5) -> List[Dict[str, Any]]:
        """语义搜索记忆
        
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
        return self.retrieval.search_by_content(
            query, agent_id, user_id, memory_types, limit, min_similarity
        )
    
    def get_recent_memories(self, agent_id: str, user_id: str, hours: int = 24,
                          memory_types: List[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            hours: 时间范围（小时）
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 最近记忆列表
        """
        return self.retrieval.get_recent_memories(agent_id, user_id, hours, memory_types, limit)
    
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
        return self.retrieval.get_important_memories(
            agent_id, user_id, min_importance, memory_types, limit
        )
    
    def search_by_tags(self, tags: List[str], agent_id: str, user_id: str,
                      match_all: bool = False, memory_types: List[str] = None,
                      limit: int = 50) -> List[Dict[str, Any]]:
        """基于标签搜索记忆
        
        Args:
            tags: 标签列表
            agent_id: 智能体ID
            user_id: 用户ID
            match_all: 是否匹配所有标签
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 检索结果列表
        """
        return self.retrieval.search_by_tags(
            tags, agent_id, user_id, match_all, memory_types, limit
        )
    
    def search_by_time_range(self, start_time: datetime, end_time: datetime,
                           agent_id: str, user_id: str, memory_types: List[str] = None,
                           limit: int = 50) -> List[Dict[str, Any]]:
        """基于时间范围搜索记忆
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            agent_id: 智能体ID
            user_id: 用户ID
            memory_types: 记忆类型过滤
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 检索结果列表
        """
        return self.retrieval.search_by_time_range(
            start_time, end_time, agent_id, user_id, memory_types, limit
        )
    
    def get_related_memories(self, memory_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取相关记忆
        
        Args:
            memory_id: 基准记忆ID
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 相关记忆列表
        """
        return self.retrieval.search_related_memories(memory_id, limit)
    
    # ==================== 记忆管理接口 ====================
    
    def evaluate_memory_importance(self, memory_id: str) -> float:
        """评估记忆重要性
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            float: 重要性评分 (0.0-1.0)
        """
        return self.manager.evaluate_importance(memory_id)
    
    def compress_memories(self, agent_id: str, user_id: str,
                         memory_type: str = 'long_term') -> int:
        """压缩记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            memory_type: 要压缩的记忆类型
            
        Returns:
            int: 压缩的记忆数量
        """
        return self.manager.compress_memories(agent_id, user_id, memory_type)
    
    def cleanup_expired_memories(self) -> int:
        """清理过期记忆
        
        Returns:
            int: 清理的记忆数量
        """
        return self.manager.cleanup_expired()
    
    def cleanup_low_importance_memories(self, agent_id: str, user_id: str,
                                       threshold: float = 0.2, max_age_days: int = 30) -> int:
        """清理低重要性记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            threshold: 重要性阈值
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的记忆数量
        """
        return self.manager.cleanup_low_importance(agent_id, user_id, threshold, max_age_days)
    
    def build_memory_associations(self, memory_id: str) -> List[str]:
        """构建记忆关联
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            List[str]: 新建关联的记忆ID列表
        """
        return self.manager.build_associations(memory_id)
    
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
        return self.manager.analyze_memory_patterns(agent_id, user_id, days)
    
    # ==================== 智能体特化接口 ====================
    
    def store_conversation_memory(self, agent_id: str, user_id: str,
                                 user_message: str, agent_response: str,
                                 context: Dict[str, Any] = None) -> str:
        """存储对话记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            user_message: 用户消息
            agent_response: 智能体回复
            context: 对话上下文
            
        Returns:
            str: 记忆ID
        """
        content = {
            'text': f"用户: {user_message}\n智能体: {agent_response}",
            'structured_data': {
                'user_message': user_message,
                'agent_response': agent_response,
                'conversation_type': 'dialogue'
            },
            'metadata': context or {}
        }
        
        return self.store_memory(
            agent_id=agent_id,
            user_id=user_id,
            content=content,
            memory_type='working',
            importance=0.6,
            tags=['对话', '交互'],
            expires_hours=168  # 7天后过期
        )
    
    def store_health_record_memory(self, agent_id: str, user_id: str,
                                  record_type: str, record_data: Dict[str, Any],
                                  importance: float = 0.8) -> str:
        """存储健康档案记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            record_type: 记录类型（如：体检报告、诊断记录等）
            record_data: 记录数据
            importance: 重要性评分
            
        Returns:
            str: 记忆ID
        """
        content = {
            'text': f"{record_type}: {record_data.get('summary', '')}",
            'structured_data': record_data,
            'metadata': {
                'record_type': record_type,
                'data_source': 'health_records_agent'
            }
        }
        
        tags = ['健康档案', record_type]
        if record_data.get('urgent'):
            tags.append('紧急')
        
        return self.store_memory(
            agent_id=agent_id,
            user_id=user_id,
            content=content,
            memory_type='long_term',
            importance=importance,
            tags=tags
        )
    
    def store_medication_memory(self, agent_id: str, user_id: str,
                               medication_info: Dict[str, Any],
                               reminder_type: str = 'schedule') -> str:
        """存储用药记忆
        
        Args:
            agent_id: 智能体ID
            user_id: 用户ID
            medication_info: 用药信息
            reminder_type: 提醒类型
            
        Returns:
            str: 记忆ID
        """
        content = {
            'text': f"用药提醒: {medication_info.get('medication_name', '')}",
            'structured_data': medication_info,
            'metadata': {
                'reminder_type': reminder_type,
                'data_source': 'medication_agent'
            }
        }
        
        tags = ['用药提醒', medication_info.get('medication_name', ''), reminder_type]
        
        # 根据用药重要性设置过期时间
        expires_hours = None
        if reminder_type == 'schedule':
            expires_hours = 24 * 30  # 30天后过期
        
        return self.store_memory(
            agent_id=agent_id,
            user_id=user_id,
            content=content,
            memory_type='working',
            importance=0.7,
            tags=tags,
            expires_hours=expires_hours
        )
    
    # ==================== 系统状态接口 ====================
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态
        
        Returns:
            Dict: 系统状态信息
        """
        try:
            # 检查数据库连接
            db_status = self.db_config.check_connection()
            
            # 获取表信息
            table_info = self.db_config.get_table_info()
            
            # 获取嵌入服务信息
            embedding_info = self.embedding_service.get_model_info()
            
            return {
                'database_connected': db_status,
                'table_statistics': table_info,
                'embedding_service': embedding_info,
                'system_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {
                'database_connected': False,
                'error': str(e),
                'system_time': datetime.now().isoformat()
            }
    
    def perform_maintenance(self, agent_id: str = None, user_id: str = None) -> Dict[str, Any]:
        """执行系统维护
        
        Args:
            agent_id: 特定智能体ID（可选）
            user_id: 特定用户ID（可选）
            
        Returns:
            Dict: 维护结果
        """
        results = {
            'expired_cleaned': 0,
            'low_importance_cleaned': 0,
            'memories_compressed': 0,
            'associations_built': 0
        }
        
        try:
            # 清理过期记忆
            results['expired_cleaned'] = self.cleanup_expired_memories()
            
            # 如果指定了智能体和用户，执行特定维护
            if agent_id and user_id:
                # 清理低重要性记忆
                results['low_importance_cleaned'] = self.cleanup_low_importance_memories(
                    agent_id, user_id
                )
                
                # 压缩记忆
                results['memories_compressed'] = self.compress_memories(agent_id, user_id)
            
            logger.info(f"系统维护完成: {results}")
            return results
            
        except Exception as e:
            logger.error(f"系统维护失败: {e}")
            results['error'] = str(e)
            return results