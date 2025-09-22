# -*- coding: utf-8 -*-
"""
就诊摘要生成智能体记忆服务
为 VisitSummaryGenerator 提供记忆系统的集成服务
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# 添加记忆系统路径
import sys
import os
# 将 backend 根目录加入 sys.path，保证 memory_system 和 AgentMemorySystem 包的导入
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

try:
    from memory_system import AgentMemorySystem
    from VisitSummaryGenerator.database_config import MemoryDatabaseConfig
except ImportError as e:
    logging.error(f"无法导入记忆系统: {e}")
    AgentMemorySystem = None
    MemoryDatabaseConfig = None

from VisitSummaryGenerator.memory_config import visit_summary_memory_config

@dataclass
class VisitRecord:
    """就诊记录数据结构"""
    user_id: str
    visit_date: datetime
    visit_type: str
    specialty: str
    diagnosis: str
    treatment: str
    symptoms: List[str]
    doctor_notes: str
    follow_up: Optional[str] = None
    severity_level: str = "中等"
    
@dataclass
class HealthTrend:
    """健康趋势数据结构"""
    user_id: str
    trend_type: str
    trend_data: Dict[str, Any]
    analysis_period: str
    risk_level: str
    recommendations: List[str]
    
class VisitSummaryMemoryService:
    """
    就诊摘要生成智能体记忆服务类
    """
    
    def __init__(self):
        self.memory_system: Optional[AgentMemorySystem] = None
        self.config = visit_summary_memory_config
        self.logger = logging.getLogger(__name__)
        self._initialized = False
    
    async def initialize(self) -> bool:
        """
        初始化记忆系统
        
        Returns:
            初始化是否成功
        """
        try:
            if AgentMemorySystem is None or MemoryDatabaseConfig is None:
                self.logger.error("记忆系统模块未正确导入")
                return False
            
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
            self._initialized = True
            
            self.logger.info("就诊摘要生成记忆服务初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"记忆服务初始化失败: {e}")
            return False
    
    async def store_visit_record(self, visit_record: VisitRecord) -> bool:
        """
        存储就诊记录
        
        Args:
            visit_record: 就诊记录
            
        Returns:
            存储是否成功
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法存储就诊记录")
            return False
        
        try:
            # 计算重要性评分
            importance_score = self._calculate_visit_importance(visit_record)
            
            # 生成标签
            tags = self.config.get_default_tags(visit_record.visit_type, visit_record.specialty)
            tags.extend([visit_record.severity_level, f"user_{visit_record.user_id}"])
            
            # 构建内容
            content = f"""
就诊记录 - {visit_record.visit_date.strftime('%Y-%m-%d')}
就诊类型: {visit_record.visit_type}
专科: {visit_record.specialty}
诊断: {visit_record.diagnosis}
治疗方案: {visit_record.treatment}
症状: {', '.join(visit_record.symptoms)}
医生备注: {visit_record.doctor_notes}
随访安排: {visit_record.follow_up or '无'}
严重程度: {visit_record.severity_level}
            """.strip()
            
            # 存储到记忆系统
            memory_id = await self.memory_system.store_memory(
                content=content,
                memory_type="visit_record",
                importance=importance_score,
                tags=tags,
                metadata={
                    "user_id": visit_record.user_id,
                    "visit_date": visit_record.visit_date.isoformat(),
                    "visit_type": visit_record.visit_type,
                    "specialty": visit_record.specialty,
                    "diagnosis": visit_record.diagnosis,
                    "severity_level": visit_record.severity_level
                }
            )
            
            self.logger.info(f"就诊记录存储成功，记忆ID: {memory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"存储就诊记录失败: {e}")
            return False
    
    async def search_visit_history(self, 
                                 user_id: str,
                                 date_range: Optional[Tuple[datetime, datetime]] = None,
                                 diagnosis_keywords: Optional[List[str]] = None,
                                 specialty: Optional[str] = None,
                                 limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索历史就诊记录
        
        Args:
            user_id: 用户ID
            date_range: 日期范围 (开始日期, 结束日期)
            diagnosis_keywords: 诊断关键词
            specialty: 专科
            limit: 返回数量限制
            
        Returns:
            就诊记录列表
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法搜索就诊历史")
            return []
        
        try:
            # 构建搜索查询
            query_parts = [f"用户 {user_id} 的就诊记录"]
            
            if diagnosis_keywords:
                query_parts.append(f"诊断包含: {', '.join(diagnosis_keywords)}")
            
            if specialty:
                query_parts.append(f"专科: {specialty}")
            
            query = " ".join(query_parts)
            
            # 构建过滤条件
            filters = {
                "memory_type": "visit_record",
                "metadata.user_id": user_id
            }
            
            if specialty:
                filters["metadata.specialty"] = specialty
            
            # 执行搜索
            results = await self.memory_system.search_memories(
                query=query,
                filters=filters,
                limit=limit
            )
            
            # 过滤日期范围
            if date_range:
                start_date, end_date = date_range
                filtered_results = []
                for result in results:
                    visit_date_str = result.get('metadata', {}).get('visit_date')
                    if visit_date_str:
                        visit_date = datetime.fromisoformat(visit_date_str)
                        if start_date <= visit_date <= end_date:
                            filtered_results.append(result)
                results = filtered_results
            
            self.logger.info(f"搜索到 {len(results)} 条就诊记录")
            return results
            
        except Exception as e:
            self.logger.error(f"搜索就诊历史失败: {e}")
            return []
    
    async def store_health_trend(self, health_trend: HealthTrend) -> bool:
        """
        存储健康趋势分析
        
        Args:
            health_trend: 健康趋势数据
            
        Returns:
            存储是否成功
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法存储健康趋势")
            return False
        
        try:
            # 计算重要性评分
            importance_score = self._calculate_trend_importance(health_trend)
            
            # 生成标签
            tags = ["health_trend", health_trend.trend_type, health_trend.risk_level, 
                   f"user_{health_trend.user_id}", health_trend.analysis_period]
            
            # 构建内容
            content = f"""
健康趋势分析 - {health_trend.trend_type}
分析周期: {health_trend.analysis_period}
风险等级: {health_trend.risk_level}
趋势数据: {health_trend.trend_data}
建议措施: {', '.join(health_trend.recommendations)}
            """.strip()
            
            # 存储到记忆系统
            memory_id = await self.memory_system.store_memory(
                content=content,
                memory_type="health_trend",
                importance=importance_score,
                tags=tags,
                metadata={
                    "user_id": health_trend.user_id,
                    "trend_type": health_trend.trend_type,
                    "risk_level": health_trend.risk_level,
                    "analysis_period": health_trend.analysis_period,
                    "trend_data": health_trend.trend_data
                }
            )
            
            self.logger.info(f"健康趋势存储成功，记忆ID: {memory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"存储健康趋势失败: {e}")
            return False
    
    async def store_user_preference(self, 
                                  user_id: str,
                                  preference_type: str,
                                  preference_value: str,
                                  context: str = "") -> bool:
        """
        存储用户偏好设置
        
        Args:
            user_id: 用户ID
            preference_type: 偏好类型
            preference_value: 偏好值
            context: 上下文说明
            
        Returns:
            存储是否成功
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法存储用户偏好")
            return False
        
        try:
            # 构建内容
            content = f"""
用户偏好设置
偏好类型: {preference_type}
偏好值: {preference_value}
上下文: {context}
            """.strip()
            
            # 生成标签
            tags = ["user_preference", preference_type, f"user_{user_id}"]
            
            # 存储到记忆系统
            memory_id = await self.memory_system.store_memory(
                content=content,
                memory_type="user_preferences",
                importance=0.6,
                tags=tags,
                metadata={
                    "user_id": user_id,
                    "preference_type": preference_type,
                    "preference_value": preference_value,
                    "context": context
                }
            )
            
            self.logger.info(f"用户偏好存储成功，记忆ID: {memory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"存储用户偏好失败: {e}")
            return False
    
    async def store_medical_knowledge(self, 
                                    knowledge_type: str,
                                    content: str,
                                    source: str,
                                    importance_score: float = 0.7) -> bool:
        """
        存储医疗知识点
        
        Args:
            knowledge_type: 知识类型
            content: 知识内容
            source: 知识来源
            importance_score: 重要性评分
            
        Returns:
            存储是否成功
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法存储医疗知识")
            return False
        
        try:
            # 生成标签
            tags = ["medical_knowledge", knowledge_type, source]
            
            # 存储到记忆系统
            memory_id = await self.memory_system.store_memory(
                content=content,
                memory_type="medical_knowledge",
                importance=importance_score,
                tags=tags,
                metadata={
                    "knowledge_type": knowledge_type,
                    "source": source
                }
            )
            
            self.logger.info(f"医疗知识存储成功，记忆ID: {memory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"存储医疗知识失败: {e}")
            return False
    
    async def get_summary_insights(self, 
                                 user_id: str,
                                 analysis_type: str = "健康趋势",
                                 time_range: str = "最近6个月") -> Dict[str, Any]:
        """
        获取摘要生成洞察和分析
        
        Args:
            user_id: 用户ID
            analysis_type: 分析类型
            time_range: 时间范围
            
        Returns:
            洞察分析结果
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法获取洞察")
            return {}
        
        try:
            insights = {
                "user_id": user_id,
                "analysis_type": analysis_type,
                "time_range": time_range,
                "generated_at": datetime.now().isoformat()
            }
            
            # 获取就诊模式分析
            visit_patterns = await self._analyze_visit_patterns(user_id)
            insights["visit_patterns"] = visit_patterns
            
            # 获取健康趋势分析
            health_trends = await self._analyze_health_trends(user_id)
            insights["health_trends"] = health_trends
            
            # 获取治疗效果分析
            treatment_effectiveness = await self._analyze_treatment_effectiveness(user_id)
            insights["treatment_effectiveness"] = treatment_effectiveness
            
            # 获取风险评估
            risk_assessment = await self._assess_health_risks(user_id)
            insights["risk_assessment"] = risk_assessment
            
            # 生成个性化建议
            recommendations = await self._generate_personalized_recommendations(user_id)
            insights["recommendations"] = recommendations
            
            self.logger.info(f"生成用户 {user_id} 的摘要洞察成功")
            return insights
            
        except Exception as e:
            self.logger.error(f"获取摘要洞察失败: {e}")
            return {}
    
    async def cleanup_expired_memories(self, 
                                     retention_days: int = 365,
                                     cleanup_types: Optional[List[str]] = None) -> int:
        """
        清理过期的记忆数据
        
        Args:
            retention_days: 保留天数
            cleanup_types: 要清理的记忆类型列表
            
        Returns:
            清理的记忆数量
        """
        if not self._initialized or not self.memory_system:
            self.logger.warning("记忆系统未初始化，无法清理记忆")
            return 0
        
        try:
            cleanup_types = cleanup_types or ["temporary_data", "processing_logs"]
            total_cleaned = 0
            
            for memory_type in cleanup_types:
                expire_days = self.config.auto_expire_days.get(memory_type, retention_days)
                cutoff_date = datetime.now() - timedelta(days=expire_days)
                
                # 执行清理
                cleaned_count = await self.memory_system.cleanup_memories(
                    memory_type=memory_type,
                    before_date=cutoff_date
                )
                
                total_cleaned += cleaned_count
                self.logger.info(f"清理 {memory_type} 类型的过期记忆 {cleaned_count} 条")
            
            self.logger.info(f"总共清理过期记忆 {total_cleaned} 条")
            return total_cleaned
            
        except Exception as e:
            self.logger.error(f"清理过期记忆失败: {e}")
            return 0
    
    def _calculate_visit_importance(self, visit_record: VisitRecord) -> float:
        """
        计算就诊记录的重要性评分
        
        Args:
            visit_record: 就诊记录
            
        Returns:
            重要性评分
        """
        # 诊断严重程度评分
        severity_scores = {"轻微": 0.3, "中等": 0.6, "严重": 0.9, "危重": 1.0}
        diagnosis_severity = severity_scores.get(visit_record.severity_level, 0.6)
        
        # 治疗复杂度评分（基于治疗方案长度和复杂性）
        treatment_complexity = min(len(visit_record.treatment) / 200, 1.0)
        
        # 患者关注度评分（基于症状数量和描述详细程度）
        patient_concern = min(len(visit_record.symptoms) / 10 + len(visit_record.doctor_notes) / 500, 1.0)
        
        # 随访重要性评分
        follow_up_importance = 0.8 if visit_record.follow_up else 0.3
        
        # 文档完整性评分
        completeness_factors = [
            bool(visit_record.diagnosis),
            bool(visit_record.treatment),
            bool(visit_record.symptoms),
            bool(visit_record.doctor_notes)
        ]
        document_completeness = sum(completeness_factors) / len(completeness_factors)
        
        return self.config.calculate_importance_score(
            diagnosis_severity,
            treatment_complexity,
            patient_concern,
            follow_up_importance,
            document_completeness
        )
    
    def _calculate_trend_importance(self, health_trend: HealthTrend) -> float:
        """
        计算健康趋势的重要性评分
        
        Args:
            health_trend: 健康趋势
            
        Returns:
            重要性评分
        """
        # 风险等级评分
        risk_scores = {"低": 0.3, "中等": 0.6, "高": 0.9, "极高": 1.0}
        risk_score = risk_scores.get(health_trend.risk_level, 0.6)
        
        # 趋势类型重要性
        trend_importance = {
            "血压变化": 0.9, "血糖变化": 0.9, "心率变化": 0.8,
            "体重变化": 0.6, "症状变化": 0.7, "用药效果": 0.8
        }
        type_score = trend_importance.get(health_trend.trend_type, 0.5)
        
        # 建议数量评分
        recommendation_score = min(len(health_trend.recommendations) / 5, 1.0)
        
        return (risk_score * 0.5 + type_score * 0.3 + recommendation_score * 0.2)
    
    async def _analyze_visit_patterns(self, user_id: str) -> Dict[str, Any]:
        """
        分析就诊模式
        
        Args:
            user_id: 用户ID
            
        Returns:
            就诊模式分析结果
        """
        try:
            # 获取最近的就诊记录
            recent_visits = await self.search_visit_history(user_id, limit=50)
            
            if not recent_visits:
                return {"message": "暂无就诊记录"}
            
            # 分析就诊频率
            visit_frequency = len(recent_visits)
            
            # 分析常见专科
            specialties = [visit.get('metadata', {}).get('specialty', '') for visit in recent_visits]
            common_specialties = self._get_frequency_analysis(specialties)
            
            # 分析常见诊断
            diagnoses = [visit.get('metadata', {}).get('diagnosis', '') for visit in recent_visits]
            common_diagnoses = self._get_frequency_analysis(diagnoses)
            
            return {
                "visit_frequency": visit_frequency,
                "common_specialties": common_specialties,
                "common_diagnoses": common_diagnoses,
                "analysis_period": "最近50次就诊"
            }
            
        except Exception as e:
            self.logger.error(f"分析就诊模式失败: {e}")
            return {"error": str(e)}
    
    async def _analyze_health_trends(self, user_id: str) -> Dict[str, Any]:
        """
        分析健康趋势
        
        Args:
            user_id: 用户ID
            
        Returns:
            健康趋势分析结果
        """
        try:
            # 搜索健康趋势记录
            trend_query = f"用户 {user_id} 的健康趋势"
            trend_results = await self.memory_system.search_memories(
                query=trend_query,
                filters={"memory_type": "health_trend", "metadata.user_id": user_id},
                limit=20
            )
            
            if not trend_results:
                return {"message": "暂无健康趋势数据"}
            
            # 分析趋势类型分布
            trend_types = [result.get('metadata', {}).get('trend_type', '') for result in trend_results]
            trend_distribution = self._get_frequency_analysis(trend_types)
            
            # 分析风险等级分布
            risk_levels = [result.get('metadata', {}).get('risk_level', '') for result in trend_results]
            risk_distribution = self._get_frequency_analysis(risk_levels)
            
            return {
                "trend_count": len(trend_results),
                "trend_distribution": trend_distribution,
                "risk_distribution": risk_distribution,
                "latest_trends": trend_results[:5]  # 最新的5个趋势
            }
            
        except Exception as e:
            self.logger.error(f"分析健康趋势失败: {e}")
            return {"error": str(e)}
    
    async def _analyze_treatment_effectiveness(self, user_id: str) -> Dict[str, Any]:
        """
        分析治疗效果
        
        Args:
            user_id: 用户ID
            
        Returns:
            治疗效果分析结果
        """
        try:
            # 获取有随访记录的就诊
            visits_with_followup = await self.search_visit_history(user_id, limit=30)
            followup_visits = [v for v in visits_with_followup 
                             if v.get('metadata', {}).get('follow_up')]
            
            if not followup_visits:
                return {"message": "暂无随访数据"}
            
            # 分析治疗方案类型
            treatments = [visit.get('metadata', {}).get('treatment', '') for visit in followup_visits]
            treatment_types = self._get_frequency_analysis(treatments)
            
            return {
                "followup_count": len(followup_visits),
                "treatment_types": treatment_types,
                "effectiveness_score": 0.75,  # 简化的效果评分
                "improvement_rate": "75%"  # 简化的改善率
            }
            
        except Exception as e:
            self.logger.error(f"分析治疗效果失败: {e}")
            return {"error": str(e)}
    
    async def _assess_health_risks(self, user_id: str) -> Dict[str, Any]:
        """
        评估健康风险
        
        Args:
            user_id: 用户ID
            
        Returns:
            健康风险评估结果
        """
        try:
            # 获取最近的健康趋势
            recent_trends = await self.memory_system.search_memories(
                query=f"用户 {user_id} 健康风险",
                filters={"memory_type": "health_trend", "metadata.user_id": user_id},
                limit=10
            )
            
            if not recent_trends:
                return {"message": "暂无风险评估数据"}
            
            # 分析风险等级
            risk_levels = [trend.get('metadata', {}).get('risk_level', '') for trend in recent_trends]
            high_risk_count = sum(1 for level in risk_levels if level in ['高', '极高'])
            
            overall_risk = "高" if high_risk_count > len(risk_levels) * 0.3 else "中等" if high_risk_count > 0 else "低"
            
            return {
                "overall_risk_level": overall_risk,
                "high_risk_factors": high_risk_count,
                "total_factors": len(risk_levels),
                "risk_percentage": f"{(high_risk_count / len(risk_levels) * 100):.1f}%" if risk_levels else "0%"
            }
            
        except Exception as e:
            self.logger.error(f"评估健康风险失败: {e}")
            return {"error": str(e)}
    
    async def _generate_personalized_recommendations(self, user_id: str) -> List[str]:
        """
        生成个性化建议
        
        Args:
            user_id: 用户ID
            
        Returns:
            个性化建议列表
        """
        try:
            recommendations = []
            
            # 基于就诊模式的建议
            visit_patterns = await self._analyze_visit_patterns(user_id)
            if visit_patterns.get('visit_frequency', 0) > 10:
                recommendations.append("建议建立定期健康检查计划，减少急诊就诊")
            
            # 基于健康趋势的建议
            health_trends = await self._analyze_health_trends(user_id)
            risk_distribution = health_trends.get('risk_distribution', {})
            if risk_distribution.get('高', 0) > 0:
                recommendations.append("建议加强高风险健康指标的监测和管理")
            
            # 基于用户偏好的建议
            preferences = await self.memory_system.search_memories(
                query=f"用户 {user_id} 偏好",
                filters={"memory_type": "user_preferences", "metadata.user_id": user_id},
                limit=5
            )
            
            if preferences:
                recommendations.append("根据您的偏好，建议继续使用详细版摘要格式")
            
            # 默认建议
            if not recommendations:
                recommendations = [
                    "建议定期进行健康检查",
                    "保持良好的生活习惯",
                    "及时关注身体变化"
                ]
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"生成个性化建议失败: {e}")
            return ["暂时无法生成个性化建议"]
    
    def _get_frequency_analysis(self, items: List[str]) -> Dict[str, int]:
        """
        获取频率分析
        
        Args:
            items: 项目列表
            
        Returns:
            频率统计字典
        """
        frequency = {}
        for item in items:
            if item:
                frequency[item] = frequency.get(item, 0) + 1
        
        # 按频率排序
        return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True))

# 全局服务实例
visit_summary_memory_service = VisitSummaryMemoryService()