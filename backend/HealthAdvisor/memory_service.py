#!/usr/bin/env python3
"""
健康顾问记忆服务
为健康顾问智能体提供记忆系统的集成服务
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import sys
import os

# 添加 backend 根目录到 sys.path，保证可用包导入（如 AgentMemorySystem、memory_system 等）
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from memory_system import AgentMemorySystem
from AgentMemorySystem.database_config import MemoryDatabaseConfig
from HealthAdvisor.memory_config import health_advisor_memory_config

class HealthAdvisorMemoryService:
    """健康顾问记忆服务类"""
    
    def __init__(self):
        self.config = health_advisor_memory_config
        self.memory_system: Optional[AgentMemorySystem] = None
        self.logger = logging.getLogger(__name__)
        self.is_initialized = False
        
    async def initialize(self) -> bool:
        """初始化记忆系统"""
        try:
            # 验证配置
            config_errors = self.config.validate_config()
            if config_errors:
                self.logger.error(f"配置验证失败: {config_errors}")
                return False
            
            # 创建数据库配置对象
            db_config = MemoryDatabaseConfig()
            
            # 初始化记忆系统
            self.memory_system = AgentMemorySystem(db_config=db_config)
            
            await self.memory_system.initialize()
            self.is_initialized = True
            self.logger.info("健康顾问记忆系统初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"记忆系统初始化失败: {e}")
            return False
    
    async def store_consultation_memory(self,
                                      consultation_content: str,
                                      symptoms: List[str],
                                      diagnosis: str,
                                      recommendations: str,
                                      user_id: str,
                                      consultation_type: str = 'general_consultation',
                                      metadata: Optional[Dict] = None) -> Optional[str]:
        """存储咨询记忆"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法存储咨询记忆")
            return None
        
        try:
            # 构建记忆内容
            memory_content = {
                'consultation_content': consultation_content,
                'symptoms': symptoms,
                'diagnosis': diagnosis,
                'recommendations': recommendations,
                'consultation_type': consultation_type,
                'timestamp': datetime.now().isoformat()
            }
            
            # 计算重要性评分
            has_critical = any(self.config.is_critical_symptom(symptom) for symptom in symptoms)
            is_chronic = 'chronic' in consultation_content.lower() or 'chronic' in diagnosis.lower()
            importance_score = self.config.calculate_importance_score(
                consultation_type, has_critical, is_chronic
            )
            
            # 生成标签
            tags = self.config.get_default_tags(consultation_type, consultation_content)
            tags.extend(['consultation', 'health_advisor'])
            if symptoms:
                tags.extend([f'symptom_{symptom}' for symptom in symptoms[:3]])  # 限制症状标签数量
            
            # 合并元数据
            full_metadata = {
                'user_id': user_id,
                'consultation_type': consultation_type,
                'symptoms_count': len(symptoms),
                'has_critical_symptoms': has_critical,
                'is_chronic_condition': is_chronic,
                'importance_score': importance_score
            }
            if metadata:
                full_metadata.update(metadata)
            
            # 存储记忆
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(memory_content, ensure_ascii=False),
                memory_type='consultation',
                tags=tags,
                importance_score=importance_score,
                metadata=full_metadata
            )
            
            self.logger.info(f"咨询记忆存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"存储咨询记忆失败: {e}")
            return None
    
    async def search_consultation_history(self,
                                        query: str,
                                        user_id: Optional[str] = None,
                                        consultation_type: Optional[str] = None,
                                        date_range: Optional[Tuple[datetime, datetime]] = None,
                                        limit: int = 10) -> List[Dict]:
        """搜索咨询历史"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法搜索咨询历史")
            return []
        
        try:
            # 构建搜索过滤器
            filters = {'memory_type': 'consultation'}
            if user_id:
                filters['user_id'] = user_id
            if consultation_type:
                filters['consultation_type'] = consultation_type
            
            # 搜索记忆
            memories = await self.memory_system.search_memories(
                query=query,
                limit=limit,
                filters=filters,
                similarity_threshold=self.config.similarity_threshold
            )
            
            # 处理搜索结果
            results = []
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                    result = {
                        'memory_id': memory.id,
                        'consultation_content': content.get('consultation_content', ''),
                        'symptoms': content.get('symptoms', []),
                        'diagnosis': content.get('diagnosis', ''),
                        'recommendations': content.get('recommendations', ''),
                        'consultation_type': content.get('consultation_type', ''),
                        'timestamp': content.get('timestamp', ''),
                        'similarity_score': memory.similarity_score,
                        'importance_score': memory.importance_score,
                        'tags': memory.tags
                    }
                    
                    # 添加日期范围过滤
                    if date_range:
                        memory_date = datetime.fromisoformat(content.get('timestamp', ''))
                        if not (date_range[0] <= memory_date <= date_range[1]):
                            continue
                    
                    results.append(result)
                except (json.JSONDecodeError, ValueError) as e:
                    self.logger.warning(f"解析记忆内容失败: {e}")
                    continue
            
            self.logger.info(f"搜索到 {len(results)} 条咨询历史")
            return results
            
        except Exception as e:
            self.logger.error(f"搜索咨询历史失败: {e}")
            return []
    
    async def store_user_health_profile(self,
                                      user_id: str,
                                      profile_data: Dict,
                                      allergies: List[str] = None,
                                      chronic_conditions: List[str] = None,
                                      preferences: Dict = None,
                                      emergency_contacts: List[Dict] = None) -> Optional[str]:
        """存储用户健康档案"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法存储用户档案")
            return None
        
        try:
            # 构建档案内容
            profile_content = {
                'user_id': user_id,
                'profile_data': profile_data,
                'allergies': allergies or [],
                'chronic_conditions': chronic_conditions or [],
                'preferences': preferences or {},
                'emergency_contacts': emergency_contacts or [],
                'last_updated': datetime.now().isoformat()
            }
            
            # 生成标签
            tags = ['user_profile', 'health_advisor', user_id]
            if allergies:
                tags.extend([f'allergy_{allergy}' for allergy in allergies[:3]])
            if chronic_conditions:
                tags.extend([f'chronic_{condition}' for condition in chronic_conditions[:3]])
            
            # 元数据
            metadata = {
                'user_id': user_id,
                'profile_type': 'health_profile',
                'allergies_count': len(allergies or []),
                'chronic_conditions_count': len(chronic_conditions or [])
            }
            
            # 存储档案
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(profile_content, ensure_ascii=False),
                memory_type='user_profile',
                tags=tags,
                importance_score=0.9,  # 用户档案重要性较高
                metadata=metadata
            )
            
            self.logger.info(f"用户健康档案存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"存储用户健康档案失败: {e}")
            return None
    
    async def get_personalized_recommendations(self,
                                             user_id: str,
                                             current_symptoms: List[str] = None,
                                             recommendation_type: str = 'general') -> Dict:
        """获取个性化建议"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法获取个性化建议")
            return {}
        
        try:
            # 获取用户档案
            profile_memories = await self.memory_system.search_memories(
                query=f"user_id:{user_id}",
                filters={'memory_type': 'user_profile', 'user_id': user_id},
                limit=1
            )
            
            user_profile = {}
            if profile_memories:
                try:
                    user_profile = json.loads(profile_memories[0].content)
                except json.JSONDecodeError:
                    pass
            
            # 获取历史咨询记录
            consultation_query = f"user_id:{user_id}"
            if current_symptoms:
                consultation_query += f" {' '.join(current_symptoms)}"
            
            consultation_memories = await self.memory_system.search_memories(
                query=consultation_query,
                filters={'memory_type': 'consultation', 'user_id': user_id},
                limit=10
            )
            
            # 分析历史模式
            recommendations = await self._generate_personalized_recommendations(
                user_profile, consultation_memories, current_symptoms, recommendation_type
            )
            
            self.logger.info(f"为用户 {user_id} 生成个性化建议")
            return recommendations
            
        except Exception as e:
            self.logger.error(f"获取个性化建议失败: {e}")
            return {}
    
    async def analyze_health_patterns(self,
                                    user_id: str,
                                    analysis_type: str = 'symptom_trends',
                                    time_period: int = 90) -> Dict:
        """分析健康模式"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法分析健康模式")
            return {}
        
        try:
            # 获取指定时间段内的咨询记录
            start_date = datetime.now() - timedelta(days=time_period)
            
            consultation_memories = await self.memory_system.search_memories(
                query=f"user_id:{user_id}",
                filters={'memory_type': 'consultation', 'user_id': user_id},
                limit=100
            )
            
            # 过滤时间范围
            filtered_memories = []
            for memory in consultation_memories:
                try:
                    content = json.loads(memory.content)
                    timestamp = datetime.fromisoformat(content.get('timestamp', ''))
                    if timestamp >= start_date:
                        filtered_memories.append(content)
                except (json.JSONDecodeError, ValueError):
                    continue
            
            # 执行模式分析
            analysis_result = await self._perform_health_pattern_analysis(
                filtered_memories, analysis_type, time_period
            )
            
            self.logger.info(f"为用户 {user_id} 完成健康模式分析")
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"健康模式分析失败: {e}")
            return {}
    
    async def store_diagnosis_feedback(self,
                                     consultation_id: str,
                                     feedback_type: str,
                                     user_comments: str,
                                     outcome: str,
                                     effectiveness_score: float = 0.0) -> Optional[str]:
        """存储诊断反馈"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法存储诊断反馈")
            return None
        
        try:
            # 构建反馈内容
            feedback_content = {
                'consultation_id': consultation_id,
                'feedback_type': feedback_type,
                'user_comments': user_comments,
                'outcome': outcome,
                'effectiveness_score': effectiveness_score,
                'feedback_timestamp': datetime.now().isoformat()
            }
            
            # 生成标签
            tags = ['diagnosis_feedback', 'health_advisor', feedback_type]
            
            # 元数据
            metadata = {
                'consultation_id': consultation_id,
                'feedback_type': feedback_type,
                'effectiveness_score': effectiveness_score
            }
            
            # 存储反馈
            memory_id = await self.memory_system.store_memory(
                content=json.dumps(feedback_content, ensure_ascii=False),
                memory_type='diagnosis_feedback',
                tags=tags,
                importance_score=0.7,
                metadata=metadata
            )
            
            self.logger.info(f"诊断反馈存储成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"存储诊断反馈失败: {e}")
            return None
    
    async def cleanup_advisor_memories(self,
                                     user_id: Optional[str] = None,
                                     older_than_days: int = 365) -> int:
        """清理健康顾问记忆"""
        if not self.is_initialized:
            self.logger.warning("记忆系统未初始化，无法清理记忆")
            return 0
        
        try:
            # 构建清理过滤器
            filters = {}
            if user_id:
                filters['user_id'] = user_id
            
            # 执行清理
            cleanup_date = datetime.now() - timedelta(days=older_than_days)
            cleaned_count = await self.memory_system.cleanup_memories(
                older_than=cleanup_date,
                filters=filters
            )
            
            self.logger.info(f"清理了 {cleaned_count} 条健康顾问记忆")
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"清理健康顾问记忆失败: {e}")
            return 0
    
    async def _generate_personalized_recommendations(self,
                                                   user_profile: Dict,
                                                   consultation_memories: List,
                                                   current_symptoms: List[str],
                                                   recommendation_type: str) -> Dict:
        """生成个性化建议"""
        recommendations = {
            'type': recommendation_type,
            'generated_at': datetime.now().isoformat(),
            'recommendations': [],
            'warnings': [],
            'follow_up_suggestions': []
        }
        
        try:
            # 分析用户档案
            allergies = user_profile.get('allergies', [])
            chronic_conditions = user_profile.get('chronic_conditions', [])
            preferences = user_profile.get('preferences', {})
            
            # 分析历史咨询模式
            symptom_patterns = {}
            for memory in consultation_memories:
                try:
                    content = json.loads(memory.content)
                    symptoms = content.get('symptoms', [])
                    for symptom in symptoms:
                        symptom_patterns[symptom] = symptom_patterns.get(symptom, 0) + 1
                except json.JSONDecodeError:
                    continue
            
            # 生成基于历史的建议
            if symptom_patterns:
                frequent_symptoms = sorted(symptom_patterns.items(), key=lambda x: x[1], reverse=True)[:3]
                for symptom, count in frequent_symptoms:
                    if count > 1:
                        recommendations['recommendations'].append({
                            'type': 'pattern_based',
                            'content': f"您经常出现{symptom}症状，建议定期监测并考虑预防措施",
                            'priority': 'medium'
                        })
            
            # 基于过敏史的警告
            if allergies and current_symptoms:
                for allergy in allergies:
                    recommendations['warnings'].append({
                        'type': 'allergy_warning',
                        'content': f"注意您对{allergy}过敏，请避免相关接触",
                        'priority': 'high'
                    })
            
            # 基于慢性疾病的建议
            if chronic_conditions:
                for condition in chronic_conditions:
                    recommendations['recommendations'].append({
                        'type': 'chronic_management',
                        'content': f"请继续关注{condition}的管理，定期复查",
                        'priority': 'high'
                    })
            
            # 生成随访建议
            if current_symptoms:
                recommendations['follow_up_suggestions'].append({
                    'type': 'symptom_monitoring',
                    'content': "建议记录症状变化，如有加重请及时就医",
                    'timeframe': '1-2周'
                })
            
        except Exception as e:
            self.logger.error(f"生成个性化建议时出错: {e}")
        
        return recommendations
    
    async def _perform_health_pattern_analysis(self,
                                             consultation_memories: List[Dict],
                                             analysis_type: str,
                                             time_period: int) -> Dict:
        """执行健康模式分析"""
        analysis_result = {
            'analysis_type': analysis_type,
            'time_period_days': time_period,
            'analyzed_at': datetime.now().isoformat(),
            'patterns': {},
            'trends': {},
            'insights': []
        }
        
        try:
            if analysis_type == 'symptom_trends':
                # 症状趋势分析
                symptom_timeline = {}
                for memory in consultation_memories:
                    timestamp = memory.get('timestamp', '')
                    symptoms = memory.get('symptoms', [])
                    
                    for symptom in symptoms:
                        if symptom not in symptom_timeline:
                            symptom_timeline[symptom] = []
                        symptom_timeline[symptom].append(timestamp)
                
                analysis_result['patterns']['symptom_frequency'] = {
                    symptom: len(timestamps) for symptom, timestamps in symptom_timeline.items()
                }
                
                # 生成趋势洞察
                if symptom_timeline:
                    most_frequent = max(symptom_timeline.items(), key=lambda x: len(x[1]))
                    analysis_result['insights'].append({
                        'type': 'frequent_symptom',
                        'content': f"最常出现的症状是{most_frequent[0]}，出现{len(most_frequent[1])}次",
                        'severity': 'medium'
                    })
            
            elif analysis_type == 'consultation_frequency':
                # 咨询频率分析
                monthly_counts = {}
                for memory in consultation_memories:
                    timestamp = memory.get('timestamp', '')
                    try:
                        date = datetime.fromisoformat(timestamp)
                        month_key = f"{date.year}-{date.month:02d}"
                        monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
                    except ValueError:
                        continue
                
                analysis_result['patterns']['monthly_consultation_counts'] = monthly_counts
                
                # 生成频率洞察
                if monthly_counts:
                    avg_monthly = sum(monthly_counts.values()) / len(monthly_counts)
                    analysis_result['insights'].append({
                        'type': 'consultation_frequency',
                        'content': f"平均每月咨询{avg_monthly:.1f}次",
                        'severity': 'low'
                    })
            
        except Exception as e:
            self.logger.error(f"健康模式分析时出错: {e}")
        
        return analysis_result

# 全局记忆服务实例
health_advisor_memory_service = HealthAdvisorMemoryService()