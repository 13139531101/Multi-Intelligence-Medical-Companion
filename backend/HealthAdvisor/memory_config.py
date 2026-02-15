#!/usr/bin/env python3
"""
健康顾问记忆系统配置
为健康顾问智能体提供记忆系统的配置和初始化功能
"""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

class HealthAdvisorMemoryConfig:
    """健康顾问记忆系统配置类"""
    
    def __init__(self):
        # 数据库配置
        self.database_url = os.getenv('DATABASE_URL', 'postgresql://pha:pha_pass@postgres:5432/personal_health_assistant')
        self.database_pool_size = int(os.getenv('DATABASE_POOL_SIZE', '10'))
        self.database_timeout = int(os.getenv('DATABASE_TIMEOUT', '30'))
        
        # 嵌入模型配置
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
        self.embedding_dimension = int(os.getenv('EMBEDDING_DIMENSION', '1536'))
        self.embedding_batch_size = int(os.getenv('EMBEDDING_BATCH_SIZE', '100'))
        
        # 记忆管理配置
        self.max_memory_age_days = int(os.getenv('MAX_MEMORY_AGE_DAYS', '365'))  # 记忆保存1年
        self.max_memories_per_user = int(os.getenv('MAX_MEMORIES_PER_USER', '10000'))
        self.memory_cleanup_interval_hours = int(os.getenv('MEMORY_CLEANUP_INTERVAL_HOURS', '24'))
        self.auto_cleanup_enabled = os.getenv('AUTO_CLEANUP_ENABLED', 'true').lower() == 'true'
        
        # 检索配置
        self.default_search_limit = int(os.getenv('DEFAULT_SEARCH_LIMIT', '10'))
        self.similarity_threshold = float(os.getenv('SIMILARITY_THRESHOLD', '0.7'))
        self.max_search_results = int(os.getenv('MAX_SEARCH_RESULTS', '50'))
        
        # 健康顾问特定配置
        self.consultation_types = {
            'symptom_analysis': '症状分析',
            'disease_inquiry': '疾病咨询',
            'health_advice': '健康建议',
            'medication_guidance': '用药指导',
            'lifestyle_recommendation': '生活方式建议',
            'prevention_advice': '预防建议',
            'emergency_consultation': '紧急咨询',
            'follow_up': '随访咨询'
        }
        
        self.critical_symptoms = [
            '胸痛', '呼吸困难', '意识丧失', '严重头痛', '高热', 
            '剧烈腹痛', '大出血', '中毒', '过敏反应', '心悸'
        ]
        
        self.health_categories = [
            '心血管', '呼吸系统', '消化系统', '神经系统', '内分泌',
            '免疫系统', '骨骼肌肉', '皮肤', '眼科', '耳鼻喉',
            '妇科', '儿科', '精神健康', '营养', '运动健康'
        ]
        
        # 记忆重要性评分权重
        self.importance_weights = {
            'critical_symptoms': 1.0,      # 危急症状
            'chronic_conditions': 0.9,     # 慢性疾病
            'medication_related': 0.8,     # 用药相关
            'diagnostic_results': 0.8,     # 诊断结果
            'treatment_outcomes': 0.7,     # 治疗效果
            'user_feedback': 0.6,          # 用户反馈
            'general_consultation': 0.5,   # 一般咨询
            'lifestyle_advice': 0.4        # 生活建议
        }
        
        # 自动过期配置（天数）
        self.auto_expire_days = {
            'general_consultation': 90,     # 一般咨询3个月
            'symptom_analysis': 180,       # 症状分析6个月
            'medication_guidance': 365,    # 用药指导1年
            'chronic_conditions': -1,      # 慢性疾病永不过期
            'emergency_consultation': 730, # 紧急咨询2年
            'user_profile': -1,           # 用户档案永不过期
            'diagnostic_results': 1095    # 诊断结果3年
        }
        
        # 安全配置
        self.encryption_enabled = os.getenv('ENCRYPTION_ENABLED', 'true').lower() == 'true'
        self.data_anonymization = os.getenv('DATA_ANONYMIZATION', 'true').lower() == 'true'
        self.access_logging = os.getenv('ACCESS_LOGGING', 'true').lower() == 'true'
        
        # 性能配置
        self.cache_enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.cache_ttl_seconds = int(os.getenv('CACHE_TTL_SECONDS', '3600'))  # 1小时
        self.batch_processing_enabled = os.getenv('BATCH_PROCESSING_ENABLED', 'true').lower() == 'true'
        
        # 日志配置
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', 'health_advisor_memory.log')
        self.log_rotation = os.getenv('LOG_ROTATION', 'daily')
        
    def get_consultation_config(self, consultation_type: str) -> Dict[str, Any]:
        """获取特定咨询类型的配置"""
        return {
            'type': consultation_type,
            'name': self.consultation_types.get(consultation_type, consultation_type),
            'importance_weight': self.importance_weights.get(consultation_type, 0.5),
            'auto_expire_days': self.auto_expire_days.get(consultation_type, 90)
        }
    
    def is_critical_symptom(self, symptom: str) -> bool:
        """判断是否为危急症状"""
        return any(critical in symptom for critical in self.critical_symptoms)
    
    def get_health_category(self, content: str) -> Optional[str]:
        """根据内容判断健康分类"""
        content_lower = content.lower()
        for category in self.health_categories:
            if category in content_lower:
                return category
        return None
    
    def calculate_importance_score(self, 
                                 consultation_type: str,
                                 has_critical_symptoms: bool = False,
                                 is_chronic_condition: bool = False,
                                 user_feedback_score: float = 0.0) -> float:
        """计算记忆重要性评分"""
        base_score = self.importance_weights.get(consultation_type, 0.5)
        
        # 危急症状加权
        if has_critical_symptoms:
            base_score = max(base_score, self.importance_weights['critical_symptoms'])
        
        # 慢性疾病加权
        if is_chronic_condition:
            base_score = max(base_score, self.importance_weights['chronic_conditions'])
        
        # 用户反馈加权
        if user_feedback_score > 0:
            feedback_weight = min(user_feedback_score / 5.0, 1.0)  # 假设5分制
            base_score += feedback_weight * 0.2
        
        return min(base_score, 1.0)
    
    def get_default_tags(self, consultation_type: str, content: str) -> List[str]:
        """获取默认标签"""
        tags = [consultation_type]
        
        # 添加健康分类标签
        category = self.get_health_category(content)
        if category:
            tags.append(category)
        
        # 添加危急症状标签
        if self.is_critical_symptom(content):
            tags.append('critical')
        
        # 添加时间标签
        now = datetime.now()
        tags.extend([
            f'year_{now.year}',
            f'month_{now.month:02d}',
            f'quarter_Q{(now.month-1)//3 + 1}'
        ])
        
        return tags
    
    def should_auto_expire(self, memory_type: str, created_at: datetime) -> bool:
        """判断记忆是否应该自动过期"""
        expire_days = self.auto_expire_days.get(memory_type, 90)
        
        # -1 表示永不过期
        if expire_days == -1:
            return False
        
        expire_date = created_at + timedelta(days=expire_days)
        return datetime.now() > expire_date
    
    def validate_config(self) -> List[str]:
        """验证配置的有效性"""
        errors = []
        
        # 验证数据库配置
        if not self.database_url:
            errors.append("数据库URL不能为空")
        
        # 验证嵌入模型配置
        if self.embedding_dimension <= 0:
            errors.append("嵌入维度必须大于0")
        
        # 验证检索配置
        if not 0 <= self.similarity_threshold <= 1:
            errors.append("相似度阈值必须在0-1之间")
        
        # 验证重要性权重
        for weight in self.importance_weights.values():
            if not 0 <= weight <= 1:
                errors.append(f"重要性权重必须在0-1之间: {weight}")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'database': {
                'url': self.database_url,
                'pool_size': self.database_pool_size,
                'timeout': self.database_timeout
            },
            'embedding': {
                'model': self.embedding_model,
                'dimension': self.embedding_dimension,
                'batch_size': self.embedding_batch_size
            },
            'memory_management': {
                'max_age_days': self.max_memory_age_days,
                'max_per_user': self.max_memories_per_user,
                'cleanup_interval_hours': self.memory_cleanup_interval_hours,
                'auto_cleanup_enabled': self.auto_cleanup_enabled
            },
            'retrieval': {
                'default_limit': self.default_search_limit,
                'similarity_threshold': self.similarity_threshold,
                'max_results': self.max_search_results
            },
            'health_advisor': {
                'consultation_types': self.consultation_types,
                'critical_symptoms': self.critical_symptoms,
                'health_categories': self.health_categories,
                'importance_weights': self.importance_weights,
                'auto_expire_days': self.auto_expire_days
            },
            'security': {
                'encryption_enabled': self.encryption_enabled,
                'data_anonymization': self.data_anonymization,
                'access_logging': self.access_logging
            },
            'performance': {
                'cache_enabled': self.cache_enabled,
                'cache_ttl_seconds': self.cache_ttl_seconds,
                'batch_processing_enabled': self.batch_processing_enabled
            },
            'logging': {
                'level': self.log_level,
                'file': self.log_file,
                'rotation': self.log_rotation
            }
        }

# 全局配置实例
health_advisor_memory_config = HealthAdvisorMemoryConfig()