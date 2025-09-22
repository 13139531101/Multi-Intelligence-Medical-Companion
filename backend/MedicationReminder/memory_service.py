#!/usr/bin/env python3
"""
用药提醒智能体记忆服务
为用药提醒智能体提供记忆系统的集成服务
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# 添加 backend 根目录到 sys.path，保证 memory_system 和 AgentMemorySystem 的导入
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

from MedicationReminder.memory_config import MedicationReminderMemoryConfig

# 配置日志
logger = logging.getLogger(__name__)

class MedicationReminderMemoryService:
    """用药提醒智能体记忆服务类"""
    
    def __init__(self, config: Optional[MedicationReminderMemoryConfig] = None):
        """初始化记忆服务"""
        self.config = config or MedicationReminderMemoryConfig()
        self.memory_system: Optional[AgentMemorySystem] = None
        self.is_initialized = False
        
        # 验证配置
        config_errors = self.config.validate_config()
        if config_errors:
            logger.error(f"配置验证失败: {config_errors}")
            raise ValueError(f"配置错误: {'; '.join(config_errors)}")
    
    async def initialize(self) -> bool:
        """初始化记忆系统"""
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
            logger.info("用药提醒记忆系统初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"记忆系统初始化失败: {e}")
            self.is_initialized = False
            return False
    
    async def store_medication_record(self, 
                                    user_id: str,
                                    medication_name: str,
                                    dosage: str,
                                    frequency: str,
                                    start_date: str = None,
                                    end_date: str = None,
                                    doctor_name: str = None,
                                    notes: str = None,
                                    additional_data: Dict[str, Any] = None) -> Optional[str]:
        """存储用药记录"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法存储用药记录")
            return None
        
        try:
            # 构建记录内容
            record_content = {
                "user_id": user_id,
                "medication_name": medication_name,
                "dosage": dosage,
                "frequency": frequency,
                "start_date": start_date or datetime.now().isoformat(),
                "end_date": end_date,
                "doctor_name": doctor_name,
                "notes": notes,
                "created_at": datetime.now().isoformat()
            }
            
            if additional_data:
                record_content.update(additional_data)
            
            # 生成标签
            tags = self.config.get_default_tags("medication_record", record_content)
            
            # 计算重要性评分
            importance_score = self.config.calculate_importance_score("medication_record", record_content)
            
            # 元数据
            metadata = {
                "user_id": user_id,
                "medication_name": medication_name,
                "record_type": "medication_record",
                "is_critical": self.config.is_critical_medication(medication_name)
            }
            
            # 存储记录
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(record_content, ensure_ascii=False),
                memory_type="medication_record",
                tags=tags,
                importance_score=importance_score,
                metadata=metadata
            )
            
            logger.info(f"用药记录存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储用药记录失败: {e}")
            return None
    
    async def search_medication_history(self, 
                                      query: str,
                                      user_id: str = None,
                                      medication_name: str = None,
                                      limit: int = 10) -> List[Dict[str, Any]]:
        """搜索用药历史"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法搜索用药历史")
            return []
        
        try:
            # 构建搜索过滤器
            filters = {"memory_type": "medication_record"}
            if user_id:
                filters["user_id"] = user_id
            if medication_name:
                filters["medication_name"] = medication_name
            
            # 搜索记忆
            memories = await self.memory_system.search_memories(
                query=query,
                limit=limit,
                filters=filters
            )
            
            # 处理结果
            results = []
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                    results.append({
                        "memory_id": memory.id,
                        "medication_name": content.get("medication_name", ""),
                        "dosage": content.get("dosage", ""),
                        "frequency": content.get("frequency", ""),
                        "start_date": content.get("start_date", ""),
                        "end_date": content.get("end_date", ""),
                        "doctor_name": content.get("doctor_name", ""),
                        "notes": content.get("notes", ""),
                        "created_at": content.get("created_at", ""),
                        "similarity_score": memory.similarity_score,
                        "importance_score": memory.importance_score
                    })
                except json.JSONDecodeError:
                    continue
            
            logger.info(f"搜索到{len(results)}条用药历史记录")
            return results
            
        except Exception as e:
            logger.error(f"搜索用药历史失败: {e}")
            return []
    
    async def store_adherence_record(self,
                                   user_id: str,
                                   medication_name: str,
                                   adherence_rate: float,
                                   missed_doses: int = 0,
                                   reasons: List[str] = None,
                                   period: str = None,
                                   notes: str = None) -> Optional[str]:
        """存储服药依从性记录"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法存储依从性记录")
            return None
        
        try:
            # 构建记录内容
            adherence_content = {
                "user_id": user_id,
                "medication_name": medication_name,
                "adherence_rate": adherence_rate,
                "missed_doses": missed_doses,
                "reasons": reasons or [],
                "period": period or "weekly",
                "notes": notes,
                "adherence_category": self.config.get_adherence_category(adherence_rate),
                "recorded_at": datetime.now().isoformat()
            }
            
            # 生成标签
            tags = self.config.get_default_tags("adherence_record", adherence_content)
            
            # 计算重要性评分
            importance_score = self.config.calculate_importance_score("adherence_record", adherence_content)
            
            # 元数据
            metadata = {
                "user_id": user_id,
                "medication_name": medication_name,
                "adherence_rate": adherence_rate,
                "adherence_category": adherence_content["adherence_category"]
            }
            
            # 存储记录
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(adherence_content, ensure_ascii=False),
                memory_type="adherence_record",
                tags=tags,
                importance_score=importance_score,
                metadata=metadata
            )
            
            logger.info(f"依从性记录存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储依从性记录失败: {e}")
            return None
    
    async def store_medication_profile(self,
                                     user_id: str,
                                     allergies: List[str] = None,
                                     drug_interactions: List[str] = None,
                                     preferences: Dict[str, Any] = None,
                                     medical_conditions: List[str] = None,
                                     emergency_contacts: List[Dict[str, str]] = None) -> Optional[str]:
        """存储用户用药档案"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法存储用药档案")
            return None
        
        try:
            # 构建档案内容
            profile_content = {
                "user_id": user_id,
                "allergies": allergies or [],
                "drug_interactions": drug_interactions or [],
                "preferences": preferences or {},
                "medical_conditions": medical_conditions or [],
                "emergency_contacts": emergency_contacts or [],
                "last_updated": datetime.now().isoformat()
            }
            
            # 生成标签
            tags = self.config.get_default_tags("medication_profile", profile_content)
            
            # 计算重要性评分
            importance_score = self.config.calculate_importance_score("medication_profile", profile_content)
            
            # 元数据
            metadata = {
                "user_id": user_id,
                "profile_type": "medication_profile",
                "has_allergies": len(profile_content["allergies"]) > 0,
                "has_interactions": len(profile_content["drug_interactions"]) > 0
            }
            
            # 存储档案
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(profile_content, ensure_ascii=False),
                memory_type="medication_profile",
                tags=tags,
                importance_score=importance_score,
                metadata=metadata
            )
            
            logger.info(f"用药档案存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储用药档案失败: {e}")
            return None
    
    async def get_medication_insights(self,
                                    user_id: str,
                                    analysis_type: str = "recommendations",
                                    time_period_days: int = 30) -> Dict[str, Any]:
        """获取用药洞察和建议"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法获取用药洞察")
            return {"error": "记忆系统未初始化"}
        
        try:
            insights = {
                "user_id": user_id,
                "analysis_type": analysis_type,
                "time_period_days": time_period_days,
                "generated_at": datetime.now().isoformat(),
                "insights": [],
                "recommendations": [],
                "warnings": []
            }
            
            # 获取用户的记忆数据
            if analysis_type in ["adherence", "all"]:
                adherence_insights = await self._analyze_adherence_patterns(user_id, time_period_days)
                insights["insights"].extend(adherence_insights)
            
            if analysis_type in ["interactions", "all"]:
                interaction_warnings = await self._check_drug_interactions(user_id)
                insights["warnings"].extend(interaction_warnings)
            
            if analysis_type in ["patterns", "all"]:
                pattern_insights = await self._analyze_medication_patterns(user_id, time_period_days)
                insights["insights"].extend(pattern_insights)
            
            if analysis_type in ["recommendations", "all"]:
                recommendations = await self._generate_personalized_recommendations(user_id)
                insights["recommendations"].extend(recommendations)
            
            logger.info(f"为用户{user_id}生成了{len(insights['insights'])}条洞察")
            return insights
            
        except Exception as e:
            logger.error(f"获取用药洞察失败: {e}")
            return {"error": str(e)}
    
    async def store_appointment_record(self,
                                     user_id: str,
                                     appointment_date: str,
                                     doctor_name: str,
                                     department: str = None,
                                     purpose: str = None,
                                     outcome: str = None,
                                     next_appointment: str = None,
                                     medications_prescribed: List[str] = None,
                                     notes: str = None) -> Optional[str]:
        """存储复诊预约记录"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法存储预约记录")
            return None
        
        try:
            # 构建记录内容
            appointment_content = {
                "user_id": user_id,
                "appointment_date": appointment_date,
                "doctor_name": doctor_name,
                "department": department,
                "purpose": purpose,
                "outcome": outcome,
                "next_appointment": next_appointment,
                "medications_prescribed": medications_prescribed or [],
                "notes": notes,
                "created_at": datetime.now().isoformat()
            }
            
            # 生成标签
            tags = self.config.get_default_tags("appointment_record", appointment_content)
            
            # 计算重要性评分
            importance_score = self.config.calculate_importance_score("appointment_record", appointment_content)
            
            # 元数据
            metadata = {
                "user_id": user_id,
                "doctor_name": doctor_name,
                "appointment_date": appointment_date,
                "has_prescriptions": len(appointment_content["medications_prescribed"]) > 0
            }
            
            # 存储记录
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(appointment_content, ensure_ascii=False),
                memory_type="appointment_record",
                tags=tags,
                importance_score=importance_score,
                metadata=metadata
            )
            
            logger.info(f"预约记录存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"存储预约记录失败: {e}")
            return None
    
    async def cleanup_memories(self, user_id: str = None, older_than_days: int = 365) -> int:
        """清理过期记忆"""
        if not self.is_initialized:
            logger.warning("记忆系统未初始化，无法清理记忆")
            return 0
        
        try:
            # 构建过滤器
            filters = {}
            if user_id:
                filters["user_id"] = user_id
            
            # 执行清理
            cleanup_date = datetime.now() - timedelta(days=older_than_days)
            cleaned_count = await self.memory_system.cleanup_memories(
                older_than=cleanup_date,
                filters=filters
            )
            
            logger.info(f"清理了{cleaned_count}条过期记忆")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理记忆失败: {e}")
            return 0
    
    # 私有辅助方法
    async def _analyze_adherence_patterns(self, user_id: str, time_period_days: int) -> List[Dict[str, Any]]:
        """分析依从性模式"""
        try:
            # 获取依从性记录
            adherence_memories = await self.memory_system.search_memories(
                query=f"user_id:{user_id} adherence",
                filters={"memory_type": "adherence_record", "user_id": user_id},
                limit=50
            )
            
            insights = []
            if adherence_memories:
                total_rate = 0
                poor_adherence_count = 0
                medication_adherence = {}
                
                for memory in adherence_memories:
                    try:
                        content = json.loads(memory.content)
                        rate = content.get("adherence_rate", 0)
                        med_name = content.get("medication_name", "")
                        
                        total_rate += rate
                        if rate < 0.8:
                            poor_adherence_count += 1
                        
                        if med_name not in medication_adherence:
                            medication_adherence[med_name] = []
                        medication_adherence[med_name].append(rate)
                        
                    except json.JSONDecodeError:
                        continue
                
                if adherence_memories:
                    avg_adherence = total_rate / len(adherence_memories)
                    insights.append({
                        "type": "adherence_summary",
                        "content": f"平均服药依从性: {avg_adherence:.1%}",
                        "value": avg_adherence,
                        "severity": "high" if avg_adherence < 0.8 else "medium" if avg_adherence < 0.9 else "low"
                    })
                    
                    if poor_adherence_count > 0:
                        insights.append({
                            "type": "poor_adherence_alert",
                            "content": f"发现{poor_adherence_count}次依从性不佳的记录",
                            "value": poor_adherence_count,
                            "severity": "high"
                        })
            
            return insights
            
        except Exception as e:
            logger.error(f"分析依从性模式失败: {e}")
            return []
    
    async def _check_drug_interactions(self, user_id: str) -> List[Dict[str, Any]]:
        """检查药物相互作用"""
        try:
            # 获取用户当前用药
            current_medications = await self.memory_system.search_memories(
                query=f"user_id:{user_id} medication",
                filters={"memory_type": "medication_record", "user_id": user_id},
                limit=20
            )
            
            warnings = []
            medication_names = []
            
            for memory in current_medications:
                try:
                    content = json.loads(memory.content)
                    med_name = content.get("medication_name", "")
                    if med_name:
                        medication_names.append(med_name.lower())
                except json.JSONDecodeError:
                    continue
            
            # 简单的相互作用检查（实际应用中需要更复杂的药物数据库）
            known_interactions = {
                ("warfarin", "aspirin"): "增加出血风险",
                ("digoxin", "furosemide"): "可能导致地高辛中毒",
                ("lithium", "furosemide"): "可能导致锂中毒"
            }
            
            for (drug1, drug2), warning in known_interactions.items():
                if drug1 in medication_names and drug2 in medication_names:
                    warnings.append({
                        "type": "drug_interaction",
                        "content": f"{drug1}和{drug2}可能存在相互作用: {warning}",
                        "drugs": [drug1, drug2],
                        "severity": "high"
                    })
            
            return warnings
            
        except Exception as e:
            logger.error(f"检查药物相互作用失败: {e}")
            return []
    
    async def _analyze_medication_patterns(self, user_id: str, time_period_days: int) -> List[Dict[str, Any]]:
        """分析用药模式"""
        try:
            # 获取用药记录
            medication_memories = await self.memory_system.search_memories(
                query=f"user_id:{user_id}",
                filters={"memory_type": "medication_record", "user_id": user_id},
                limit=100
            )
            
            insights = []
            medication_frequency = {}
            medication_types = {}
            
            for memory in medication_memories:
                try:
                    content = json.loads(memory.content)
                    med_name = content.get("medication_name", "")
                    frequency = content.get("frequency", "")
                    
                    medication_frequency[med_name] = medication_frequency.get(med_name, 0) + 1
                    medication_types[frequency] = medication_types.get(frequency, 0) + 1
                    
                except json.JSONDecodeError:
                    continue
            
            if medication_frequency:
                # 最常用药物
                most_common = max(medication_frequency.items(), key=lambda x: x[1])
                insights.append({
                    "type": "most_common_medication",
                    "content": f"最常用药物: {most_common[0]} (使用{most_common[1]}次)",
                    "medication": most_common[0],
                    "count": most_common[1],
                    "severity": "low"
                })
                
                # 用药种类统计
                insights.append({
                    "type": "medication_variety",
                    "content": f"总共使用了{len(medication_frequency)}种不同的药物",
                    "count": len(medication_frequency),
                    "severity": "medium" if len(medication_frequency) > 5 else "low"
                })
            
            return insights
            
        except Exception as e:
            logger.error(f"分析用药模式失败: {e}")
            return []
    
    async def _generate_personalized_recommendations(self, user_id: str) -> List[Dict[str, Any]]:
        """生成个性化建议"""
        try:
            recommendations = []
            
            # 获取用户档案
            profile_memories = await self.memory_system.search_memories(
                query=f"user_id:{user_id} profile",
                filters={"memory_type": "medication_profile", "user_id": user_id},
                limit=5
            )
            
            # 获取依从性记录
            adherence_memories = await self.memory_system.search_memories(
                query=f"user_id:{user_id} adherence",
                filters={"memory_type": "adherence_record", "user_id": user_id},
                limit=10
            )
            
            # 基于依从性生成建议
            if adherence_memories:
                poor_adherence_count = 0
                for memory in adherence_memories:
                    try:
                        content = json.loads(memory.content)
                        if content.get("adherence_rate", 1.0) < 0.8:
                            poor_adherence_count += 1
                    except json.JSONDecodeError:
                        continue
                
                if poor_adherence_count > 0:
                    recommendations.append({
                        "type": "adherence_improvement",
                        "content": "建议设置更频繁的提醒或使用药盒来改善服药依从性",
                        "priority": "high",
                        "category": "adherence"
                    })
            
            # 基于档案生成建议
            if profile_memories:
                for memory in profile_memories:
                    try:
                        content = json.loads(memory.content)
                        if content.get("allergies"):
                            recommendations.append({
                                "type": "allergy_reminder",
                                "content": "请确保新处方药物不与您的过敏史冲突",
                                "priority": "high",
                                "category": "safety"
                            })
                        break
                    except json.JSONDecodeError:
                        continue
            
            # 通用建议
            recommendations.append({
                "type": "general_reminder",
                "content": "建议定期与医生回顾您的用药方案",
                "priority": "medium",
                "category": "general"
            })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"生成个性化建议失败: {e}")
            return []
    
    async def close(self):
        """关闭记忆服务"""
        if self.memory_system:
            await self.memory_system.close()
            self.is_initialized = False
            logger.info("用药提醒记忆服务已关闭")