#!/usr/bin/env python3
"""
用药提醒智能体记忆配置
定义用药提醒智能体的记忆系统配置参数
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class MedicationReminderMemoryConfig:
    """用药提醒智能体记忆配置类"""
    
    def __init__(self):
        """初始化配置"""
        # 数据库配置
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///medication_reminder_memory.db')
        self.database_pool_size = int(os.getenv('DATABASE_POOL_SIZE', '10'))
        self.database_timeout = int(os.getenv('DATABASE_TIMEOUT', '30'))
        
        # 嵌入模型配置
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
        self.embedding_dimension = int(os.getenv('EMBEDDING_DIMENSION', '1536'))
        self.embedding_batch_size = int(os.getenv('EMBEDDING_BATCH_SIZE', '100'))
        
        # 记忆管理配置
        self.max_memories_per_user = int(os.getenv('MAX_MEMORIES_PER_USER', '10000'))
        self.memory_cleanup_interval_hours = int(os.getenv('MEMORY_CLEANUP_INTERVAL_HOURS', '24'))
        self.auto_cleanup_enabled = os.getenv('AUTO_CLEANUP_ENABLED', 'true').lower() == 'true'
        
        # 检索配置
        self.default_search_limit = int(os.getenv('DEFAULT_SEARCH_LIMIT', '10'))
        self.similarity_threshold = float(os.getenv('SIMILARITY_THRESHOLD', '0.7'))
        self.max_search_results = int(os.getenv('MAX_SEARCH_RESULTS', '50'))
        
        # 用药提醒特定配置
        self.medication_types = [
            'prescription',  # 处方药
            'otc',          # 非处方药
            'supplement',   # 营养补充剂
            'herbal',       # 草药
            'injection',    # 注射剂
            'topical',      # 外用药
            'inhaler',      # 吸入剂
            'drops'         # 滴剂
        ]
        
        self.reminder_frequencies = [
            'once_daily',      # 每日一次
            'twice_daily',     # 每日两次
            'three_times_daily', # 每日三次
            'four_times_daily',  # 每日四次
            'every_other_day',   # 隔日一次
            'weekly',           # 每周一次
            'monthly',          # 每月一次
            'as_needed',        # 按需服用
            'before_meals',     # 餐前
            'after_meals',      # 餐后
            'with_meals',       # 餐时
            'bedtime'           # 睡前
        ]
        
        self.critical_medications = [
            'insulin',          # 胰岛素
            'warfarin',         # 华法林
            'digoxin',          # 地高辛
            'lithium',          # 锂盐
            'phenytoin',        # 苯妥英
            'theophylline',     # 茶碱
            'immunosuppressant', # 免疫抑制剂
            'chemotherapy',     # 化疗药物
            'anticoagulant',    # 抗凝药
            'antiarrhythmic'    # 抗心律失常药
        ]
        
        self.adherence_categories = {
            'excellent': (0.95, 1.0),    # 优秀: 95-100%
            'good': (0.85, 0.95),        # 良好: 85-95%
            'fair': (0.70, 0.85),        # 一般: 70-85%
            'poor': (0.50, 0.70),        # 较差: 50-70%
            'very_poor': (0.0, 0.50)     # 很差: 0-50%
        }
        
        # 记忆重要性评分权重
        self.importance_weights = {
            'critical_medication': 1.0,      # 关键药物
            'poor_adherence': 0.9,           # 依从性差
            'drug_interaction': 0.95,        # 药物相互作用
            'allergy_reaction': 1.0,         # 过敏反应
            'side_effect': 0.8,              # 副作用
            'dosage_change': 0.7,            # 剂量调整
            'new_medication': 0.6,           # 新药物
            'routine_reminder': 0.4,         # 常规提醒
            'appointment': 0.7,              # 预约记录
            'prescription_refill': 0.5       # 处方续药
        }
        
        # 自动过期天数
        self.auto_expire_days = {
            'medication_record': 730,        # 用药记录: 2年
            'adherence_record': 365,         # 依从性记录: 1年
            'medication_profile': None,      # 用药档案: 永不过期
            'appointment_record': 1095,      # 预约记录: 3年
            'reminder_log': 90,              # 提醒日志: 3个月
            'side_effect_report': 1095,      # 副作用报告: 3年
            'interaction_warning': 1095      # 相互作用警告: 3年
        }
        
        # 安全配置
        self.enable_encryption = os.getenv('ENABLE_ENCRYPTION', 'true').lower() == 'true'
        self.encryption_key = os.getenv('MEMORY_ENCRYPTION_KEY', '')
        self.enable_audit_log = os.getenv('ENABLE_AUDIT_LOG', 'true').lower() == 'true'
        
        # 性能配置
        self.cache_enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.cache_ttl_seconds = int(os.getenv('CACHE_TTL_SECONDS', '3600'))
        self.batch_processing_enabled = os.getenv('BATCH_PROCESSING_ENABLED', 'true').lower() == 'true'
        
        # 日志配置
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', 'medication_reminder_memory.log')
        self.enable_debug_logging = os.getenv('ENABLE_DEBUG_LOGGING', 'false').lower() == 'true'
    
    def get_medication_config(self, medication_type: str) -> Dict[str, Any]:
        """获取特定药物类型的配置"""
        base_config = {
            'type': medication_type,
            'requires_prescription': medication_type == 'prescription',
            'critical': medication_type in ['prescription', 'injection'],
            'default_importance': 0.7
        }
        
        # 特殊配置
        if medication_type == 'prescription':
            base_config.update({
                'requires_doctor_approval': True,
                'strict_timing': True,
                'default_importance': 0.8
            })
        elif medication_type == 'injection':
            base_config.update({
                'requires_training': True,
                'storage_requirements': 'refrigerated',
                'default_importance': 0.9
            })
        elif medication_type == 'supplement':
            base_config.update({
                'flexible_timing': True,
                'default_importance': 0.4
            })
        
        return base_config
    
    def is_critical_medication(self, medication_name: str) -> bool:
        """判断是否为关键药物"""
        medication_lower = medication_name.lower()
        return any(critical.lower() in medication_lower for critical in self.critical_medications)
    
    def get_adherence_category(self, adherence_rate: float) -> str:
        """获取依从性分类"""
        for category, (min_rate, max_rate) in self.adherence_categories.items():
            if min_rate <= adherence_rate < max_rate:
                return category
        return 'unknown'
    
    def calculate_importance_score(self, memory_type: str, content: Dict[str, Any]) -> float:
        """计算记忆重要性评分"""
        base_score = 0.5
        
        # 根据记忆类型调整
        if memory_type == 'medication_profile':
            base_score = 0.9
        elif memory_type == 'adherence_record':
            adherence_rate = content.get('adherence_rate', 1.0)
            if adherence_rate < 0.8:
                base_score = 0.9
            else:
                base_score = 0.6
        elif memory_type == 'medication_record':
            medication_name = content.get('medication_name', '')
            if self.is_critical_medication(medication_name):
                base_score = 0.9
            else:
                base_score = 0.6
        
        # 应用权重调整
        for factor, weight in self.importance_weights.items():
            if factor in content.get('factors', []):
                base_score = min(1.0, base_score * weight)
        
        return base_score
    
    def get_default_tags(self, memory_type: str, content: Dict[str, Any]) -> List[str]:
        """获取默认标签"""
        tags = [memory_type]
        
        # 添加用户标签
        if 'user_id' in content:
            tags.append(f"user_{content['user_id']}")
        
        # 添加药物相关标签
        if 'medication_name' in content:
            tags.append(content['medication_name'].lower())
            if self.is_critical_medication(content['medication_name']):
                tags.append('critical_medication')
        
        # 添加依从性标签
        if 'adherence_rate' in content:
            category = self.get_adherence_category(content['adherence_rate'])
            tags.append(f"adherence_{category}")
        
        # 添加时间标签
        tags.append(f"year_{datetime.now().year}")
        tags.append(f"month_{datetime.now().month}")
        
        return tags
    
    def is_memory_expired(self, memory_type: str, created_at: datetime) -> bool:
        """判断记忆是否过期"""
        expire_days = self.auto_expire_days.get(memory_type)
        if expire_days is None:
            return False
        
        expire_date = created_at + timedelta(days=expire_days)
        return datetime.now() > expire_date
    
    def validate_config(self) -> List[str]:
        """验证配置有效性"""
        errors = []
        
        # 验证数据库URL
        if not self.database_url:
            errors.append("数据库URL不能为空")
        
        # 验证嵌入模型
        if not self.embedding_model:
            errors.append("嵌入模型不能为空")
        
        # 验证数值范围
        if self.similarity_threshold < 0 or self.similarity_threshold > 1:
            errors.append("相似度阈值必须在0-1之间")
        
        if self.max_memories_per_user <= 0:
            errors.append("每用户最大记忆数必须大于0")
        
        # 验证加密配置
        if self.enable_encryption and not self.encryption_key:
            errors.append("启用加密时必须提供加密密钥")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'database_url': self.database_url,
            'embedding_model': self.embedding_model,
            'max_memories_per_user': self.max_memories_per_user,
            'similarity_threshold': self.similarity_threshold,
            'medication_types': self.medication_types,
            'critical_medications': self.critical_medications,
            'adherence_categories': self.adherence_categories,
            'importance_weights': self.importance_weights,
            'auto_expire_days': self.auto_expire_days,
            'enable_encryption': self.enable_encryption,
            'cache_enabled': self.cache_enabled,
            'log_level': self.log_level
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'MedicationReminderMemoryConfig':
        """从字典创建配置实例"""
        config = cls()
        for key, value in config_dict.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config