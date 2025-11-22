#!/usr/bin/env python3
"""
健康档案管理器记忆集成服务

这个模块为健康档案管理器提供记忆系统的集成服务，
包括记忆的存储、检索、管理等功能。
"""

import os
import sys
import logging
import asyncio
from typing import Optional, Dict, List, Any, Union
from datetime import datetime, timedelta
import json

# 添加记忆系统路径
# 将 backend 根目录加入 sys.path，保证 memory_system 和 AgentMemorySystem 包的导入
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

try:
    from memory_system import AgentMemorySystem
    from AgentMemorySystem.database_config import MemoryDatabaseConfig
except ImportError as e:
    logging.error(f"无法导入记忆系统: {e}")
    AgentMemorySystem = None
    MemoryDatabaseConfig = None

from HealthRecordsManager.memory_config import health_records_memory_config

# 配置日志
logger = logging.getLogger(__name__)

class HealthRecordsMemoryService:
    """健康档案管理器记忆服务类"""
    
    def __init__(self):
        """初始化记忆服务"""
        self.config = health_records_memory_config
        self.memory_system: Optional[AgentMemorySystem] = None
        self.agent_id = self.config.agent_id
        self.is_initialized = False
        self._init_lock = asyncio.Lock()
    
    async def initialize(self) -> bool:
        """初始化记忆系统"""
        async with self._init_lock:
            if self.is_initialized:
                return True
            
            try:
                if AgentMemorySystem is None or MemoryDatabaseConfig is None:
                    logger.error("记忆系统模块未正确导入")
                    return False
                
                # 创建数据库配置对象
                db_config = MemoryDatabaseConfig()
                
                # 初始化记忆系统
                self.memory_system = AgentMemorySystem(db_config=db_config)
                
                await self.memory_system.initialize()
                self.is_initialized = True
                logger.info("健康档案记忆系统初始化成功")
                return True
                    
            except Exception as e:
                logger.error(f"记忆系统初始化失败: {e}")
                return False
    
    def is_available(self) -> bool:
        """检查记忆系统是否可用"""
        return self.is_initialized and self.memory_system is not None
    
    async def store_health_record(self, 
                                user_id: str,
                                record_type: str,
                                record_data: Dict[str, Any],
                                summary: str = "",
                                importance: Optional[float] = None,
                                tags: Optional[List[str]] = None,
                                urgent: bool = False,
                                expires_hours: Optional[int] = None) -> Optional[str]:
        """存储健康记录记忆"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法存储健康记录")
            return None
        
        try:
            # 计算重要性评分
            if importance is None:
                is_critical_type = self.config.is_critical_record_type(record_type)
                has_critical_tags = any(self.config.is_critical_tag(tag) for tag in (tags or []))
                importance = self.config.calculate_importance_score(
                    base_score=0.7,  # 健康记录默认较高重要性
                    is_urgent=urgent,
                    is_critical_type=is_critical_type,
                    has_critical_tags=has_critical_tags
                )
            
            # 获取默认标签
            default_tags = self.config.get_default_tags_for_record_type(record_type)
            all_tags = list(set(default_tags + (tags or [])))
            
            if urgent:
                all_tags.append("紧急")
            
            # 设置过期时间
            if expires_hours is None:
                auto_expire_days = self.config.get_auto_expire_days(record_type)
                if auto_expire_days:
                    expires_hours = auto_expire_days * 24
            
            # 存储记忆
            memory_id = self.memory_system.store_health_record_memory(
                agent_id=self.agent_id,
                user_id=user_id,
                record_type=record_type,
                record_data={
                    **record_data,
                    "summary": summary,
                    "urgent": urgent,
                    "stored_at": datetime.now().isoformat()
                },
                importance=importance
            )
            
            logger.info(f"成功存储健康记录记忆: {record_type} (ID: {memory_id})")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储健康记录记忆失败: {e}")
            return None
    
    async def store_ocr_result(self,
                             user_id: str,
                             document_type: str,
                             ocr_text: str,
                             extracted_info: Dict[str, Any],
                             confidence: float = 0.8,
                             file_path: Optional[str] = None) -> Optional[str]:
        """存储OCR识别结果记忆"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法存储OCR结果")
            return None
        
        try:
            # 将结构化数据与可能包含复杂类型的对象转换为可JSON序列化的基本类型
            def _make_json_safe(obj):
                try:
                    import json
                    from pydantic import BaseModel  # 可选
                except Exception:
                    BaseModel = tuple()

                if obj is None:
                    return None
                if isinstance(obj, (str, int, float, bool)):
                    return obj
                if isinstance(obj, (list, tuple, set)):
                    return [ _make_json_safe(x) for x in list(obj) ]
                if isinstance(obj, dict):
                    return { str(k): _make_json_safe(v) for k, v in obj.items() }
                # Pydantic模型
                try:
                    if isinstance(obj, BaseModel):
                        return _make_json_safe(obj.dict())
                except Exception:
                    pass
                # 若本身可被json.dumps处理，直接返回
                try:
                    import json as _json
                    _json.dumps(obj)
                    return obj
                except Exception:
                    # 兜底：转为字符串，避免 "Python type Form cannot be converted" 等错误
                    return str(obj)

            # 构建记忆内容
            content = {
                'text': f"OCR识别结果: {document_type}\n{str(ocr_text)[:500]}...",
                'structured_data': {
                    'document_type': document_type,
                    'ocr_text': str(ocr_text),
                    'extracted_info': _make_json_safe(extracted_info or {}),
                    'confidence': confidence,
                    'file_path': file_path,
                    'processing_time': datetime.now().isoformat()
                },
                'metadata': {
                    'data_source': 'ocr_tool',
                    'document_type': document_type,
                    'confidence': confidence
                }
            }
            
            # 根据置信度设置重要性
            importance = min(0.9, confidence + 0.1)
            
            # 设置标签
            tags = ['OCR识别', document_type, '文档处理']
            if confidence > 0.9:
                tags.append('高置信度')
            elif confidence < 0.6:
                tags.append('低置信度')
            
            # 存储记忆（OCR结果30天后过期）
            memory_id = self.memory_system.store_memory(
                agent_id=self.agent_id,
                user_id=user_id,
                content=content,
                memory_type='working',
                importance=importance,
                tags=tags,
                expires_hours=720  # 30天
            )
            
            logger.info(f"成功存储OCR结果记忆: {document_type} (ID: {memory_id})")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储OCR结果记忆失败: {e}")
            return None
    
    async def search_health_memories(self,
                                   user_id: str,
                                   query: str,
                                   record_types: Optional[List[str]] = None,
                                   time_range_days: Optional[int] = None,
                                   min_importance: float = 0.0,
                                   limit: int = 20) -> List[Dict[str, Any]]:
        """搜索健康记忆"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法搜索健康记忆")
            return []
        
        try:
            # 执行语义搜索
            memories = self.memory_system.search_memories(
                query=query,
                agent_id=self.agent_id,
                user_id=user_id,
                memory_types=['long_term', 'working'],
                limit=limit * 2,  # 获取更多结果用于过滤
                min_similarity=0.3
            )
            
            # 过滤结果
            filtered_memories = []
            for memory in memories:
                # 重要性过滤
                if memory.get('importance', 0) < min_importance:
                    continue
                
                # 记录类型过滤
                if record_types:
                    memory_tags = memory.get('tags', [])
                    if not any(rt in memory_tags for rt in record_types):
                        continue
                
                # 时间范围过滤
                if time_range_days:
                    created_at = memory.get('created_at', '')
                    if created_at:
                        try:
                            created_date = datetime.fromisoformat(created_at)
                            if (datetime.now() - created_date).days > time_range_days:
                                continue
                        except:
                            continue
                
                filtered_memories.append(memory)
                
                if len(filtered_memories) >= limit:
                    break
            
            logger.info(f"搜索健康记忆: 查询='{query}', 找到={len(filtered_memories)}条")
            return filtered_memories
            
        except Exception as e:
            logger.error(f"搜索健康记忆失败: {e}")
            return []
    
    async def get_health_history(self,
                               user_id: str,
                               record_type: Optional[str] = None,
                               days: int = 365,
                               include_trends: bool = False) -> Dict[str, Any]:
        """获取用户健康历史记录"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法获取健康历史")
            return {"error": "记忆系统不可用"}
        
        try:
            # 获取时间范围内的记忆
            start_time = datetime.now() - timedelta(days=days)
            end_time = datetime.now()
            
            memories = self.memory_system.search_by_time_range(
                start_time=start_time,
                end_time=end_time,
                agent_id=self.agent_id,
                user_id=user_id,
                memory_types=['long_term', 'working'],
                limit=200
            )
            
            # 按记录类型过滤
            if record_type:
                memories = [
                    m for m in memories 
                    if record_type in m.get('tags', [])
                ]
            
            # 按时间排序
            memories.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            result = {
                "success": True,
                "user_id": user_id,
                "time_range_days": days,
                "record_type": record_type,
                "total_records": len(memories),
                "records": memories
            }
            
            # 如果需要趋势分析
            if include_trends and memories:
                trends = self._analyze_health_trends(memories)
                result["trends"] = trends
            
            logger.info(f"获取健康历史: 用户={user_id}, 记录数={len(memories)}")
            return result
            
        except Exception as e:
            logger.error(f"获取健康历史失败: {e}")
            return {"error": str(e)}
    
    async def get_health_insights(self,
                                user_id: str,
                                focus_area: Optional[str] = None,
                                analysis_period_days: int = 90) -> Dict[str, Any]:
        """获取健康洞察"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法获取健康洞察")
            return {"error": "记忆系统不可用"}
        
        try:
            # 获取分析周期内的记忆
            start_time = datetime.now() - timedelta(days=analysis_period_days)
            end_time = datetime.now()
            
            memories = self.memory_system.search_by_time_range(
                start_time=start_time,
                end_time=end_time,
                agent_id=self.agent_id,
                user_id=user_id,
                memory_types=['long_term', 'working'],
                limit=200
            )
            
            # 如果指定了关注领域，进行过滤
            if focus_area:
                memories = [
                    m for m in memories
                    if focus_area.lower() in str(m.get('content', {})).lower()
                ]
            
            # 分析记忆模式
            patterns = self.memory_system.analyze_memory_patterns(
                agent_id=self.agent_id,
                user_id=user_id,
                days=analysis_period_days
            )
            
            # 生成洞察
            insights = self._generate_health_insights(memories, patterns, focus_area)
            
            result = {
                "success": True,
                "user_id": user_id,
                "focus_area": focus_area,
                "analysis_period_days": analysis_period_days,
                "total_memories_analyzed": len(memories),
                "insights": insights,
                "patterns": patterns
            }
            
            logger.info(f"获取健康洞察: 用户={user_id}, 分析记录数={len(memories)}")
            return result
            
        except Exception as e:
            logger.error(f"获取健康洞察失败: {e}")
            return {"error": str(e)}
    
    async def store_conversation_memory(self,
                                      user_id: str,
                                      conversation_data: Dict[str, Any],
                                      importance: float = 0.6) -> Optional[str]:
        """存储对话记忆"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法存储对话记忆")
            return None
        
        try:
            memory_id = self.memory_system.store_conversation_memory(
                agent_id=self.agent_id,
                user_id=user_id,
                conversation_data=conversation_data,
                importance=importance
            )
            
            logger.info(f"成功存储对话记忆 (ID: {memory_id})")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储对话记忆失败: {e}")
            return None
    
    async def cleanup_memories(self,
                             user_id: Optional[str] = None,
                             cleanup_type: str = "expired",
                             dry_run: bool = True) -> Dict[str, Any]:
        """清理记忆数据"""
        if not self.is_available():
            logger.warning("记忆系统不可用，无法清理记忆")
            return {"error": "记忆系统不可用"}
        
        try:
            results = {
                "success": True,
                "cleanup_type": cleanup_type,
                "dry_run": dry_run,
                "cleaned_count": 0,
                "details": []
            }
            
            if cleanup_type == "expired":
                if not dry_run:
                    cleaned = self.memory_system.cleanup_expired_memories()
                    results["cleaned_count"] = cleaned
                    results["details"].append(f"清理了 {cleaned} 条过期记忆")
                else:
                    results["details"].append("试运行：将清理过期记忆")
            
            elif cleanup_type == "low_importance" and user_id:
                if not dry_run:
                    cleaned = self.memory_system.cleanup_low_importance_memories(
                        agent_id=self.agent_id,
                        user_id=user_id,
                        threshold=0.3,
                        max_age_days=180
                    )
                    results["cleaned_count"] = cleaned
                    results["details"].append(f"清理了 {cleaned} 条低重要性记忆")
                else:
                    results["details"].append("试运行：将清理低重要性记忆")
            
            elif cleanup_type == "duplicates" and user_id:
                if not dry_run:
                    compressed = self.memory_system.compress_memories(
                        agent_id=self.agent_id,
                        user_id=user_id,
                        memory_type='long_term'
                    )
                    results["cleaned_count"] = compressed
                    results["details"].append(f"压缩了 {compressed} 条重复记忆")
                else:
                    results["details"].append("试运行：将压缩重复记忆")
            
            logger.info(f"记忆清理操作: {cleanup_type}, 干运行={dry_run}")
            return results
            
        except Exception as e:
            logger.error(f"清理记忆失败: {e}")
            return {"error": str(e)}
    
    def _analyze_health_trends(self, memories: List[Dict]) -> Dict[str, Any]:
        """分析健康趋势"""
        trends = {
            "record_frequency": {},
            "common_topics": {},
            "time_distribution": {},
            "importance_trend": []
        }
        
        for memory in memories:
            # 记录频率分析
            tags = memory.get('tags', [])
            for tag in tags:
                if tag != '健康档案':  # 排除通用标签
                    trends["record_frequency"][tag] = trends["record_frequency"].get(tag, 0) + 1
            
            # 时间分布分析
            created_at = memory.get('created_at', '')
            if created_at:
                try:
                    date = datetime.fromisoformat(created_at).date()
                    month_key = date.strftime('%Y-%m')
                    trends["time_distribution"][month_key] = trends["time_distribution"].get(month_key, 0) + 1
                except:
                    pass
            
            # 重要性趋势
            importance = memory.get('importance', 0)
            trends["importance_trend"].append({
                "date": created_at,
                "importance": importance
            })
        
        return trends
    
    def _generate_health_insights(self, memories: List[Dict], patterns: Dict, focus_area: str = None) -> List[str]:
        """生成健康洞察"""
        insights = []
        
        if not memories:
            insights.append("暂无足够的健康记录数据进行分析")
            return insights
        
        # 记录数量洞察
        total_records = len(memories)
        insights.append(f"分析期间共有 {total_records} 条健康记录")
        
        # 记录类型分析
        record_types = {}
        for memory in memories:
            tags = memory.get('tags', [])
            for tag in tags:
                if tag != '健康档案':
                    record_types[tag] = record_types.get(tag, 0) + 1
        
        if record_types:
            most_common = max(record_types.items(), key=lambda x: x[1])
            insights.append(f"最常见的记录类型是 '{most_common[0]}'，共 {most_common[1]} 条记录")
        
        # 重要性分析
        importance_scores = [m.get('importance', 0) for m in memories]
        if importance_scores:
            avg_importance = sum(importance_scores) / len(importance_scores)
            high_importance_count = len([s for s in importance_scores if s > 0.7])
            insights.append(f"平均重要性评分: {avg_importance:.2f}")
            insights.append(f"高重要性记录 (>0.7): {high_importance_count} 条")
        
        # 时间趋势分析
        if len(memories) > 1:
            recent_week = [m for m in memories if 
                          (datetime.now() - datetime.fromisoformat(m.get('created_at', datetime.now().isoformat()))).days <= 7]
            if recent_week:
                insights.append(f"最近一周新增 {len(recent_week)} 条记录")
        
        # 关注领域特定洞察
        if focus_area:
            focus_memories = [
                m for m in memories
                if focus_area.lower() in str(m.get('content', {})).lower()
            ]
            if focus_memories:
                insights.append(f"关于 '{focus_area}' 的记录共 {len(focus_memories)} 条")
            else:
                insights.append(f"未找到关于 '{focus_area}' 的相关记录")
        
        return insights
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取记忆系统状态"""
        if not self.is_available():
            return {
                "available": False,
                "initialized": self.is_initialized,
                "error": "记忆系统不可用"
            }
        
        try:
            status = self.memory_system.get_system_status()
            status["available"] = True
            status["initialized"] = self.is_initialized
            status["agent_id"] = self.agent_id
            return status
        except Exception as e:
            return {
                "available": False,
                "initialized": self.is_initialized,
                "error": str(e)
            }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"HealthRecordsMemoryService(agent_id={self.agent_id}, available={self.is_available()})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()

# 全局记忆服务实例
health_records_memory_service = HealthRecordsMemoryService()

# 导出
__all__ = [
    "HealthRecordsMemoryService",
    "health_records_memory_service"
]