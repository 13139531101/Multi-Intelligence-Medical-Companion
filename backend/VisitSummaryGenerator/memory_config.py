# -*- coding: utf-8 -*-
"""
就诊摘要生成智能体记忆配置
为 VisitSummaryGenerator 提供记忆系统的配置和初始化功能
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

@dataclass
class VisitSummaryMemoryConfig:
    """
    就诊摘要生成智能体记忆系统配置类
    """
    
    # 数据库配置
    database_url: str = field(default_factory=lambda: os.getenv('MEMORY_DATABASE_URL', 'postgresql://pha:pha_pass@postgres:5432/personal_health_assistant'))
    database_pool_size: int = 10
    database_timeout: int = 30
    
    # 嵌入模型配置
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimension: int = 1536
    embedding_batch_size: int = 100
    
    # 记忆管理配置
    max_memory_items: int = 10000
    memory_cleanup_interval: int = 24  # 小时
    importance_threshold: float = 0.3
    
    # 检索配置
    default_retrieval_limit: int = 20
    similarity_threshold: float = 0.7
    max_search_results: int = 50
    
    # 就诊摘要特定配置
    visit_record_types: List[str] = field(default_factory=lambda: [
        '门诊记录', '住院记录', '急诊记录', '体检记录', 
        '复查记录', '专科会诊', '手术记录', '检查报告'
    ])
    
    health_trend_types: List[str] = field(default_factory=lambda: [
        '血压变化', '血糖变化', '体重变化', '心率变化',
        '症状变化', '用药效果', '检查指标', '生活质量'
    ])
    
    medical_specialties: List[str] = field(default_factory=lambda: [
        '内科', '外科', '妇科', '儿科', '眼科', '耳鼻喉科',
        '皮肤科', '神经科', '心血管科', '消化科', '呼吸科',
        '内分泌科', '肾内科', '血液科', '肿瘤科', '精神科'
    ])
    
    document_formats: List[str] = field(default_factory=lambda: [
        '简要摘要', '详细摘要', '专业报告', '患者版本',
        '医生版本', '保险版本', '转诊摘要', '随访记录'
    ])
    
    # 重要性评分权重
    importance_weights: Dict[str, float] = field(default_factory=lambda: {
        'diagnosis_severity': 0.3,      # 诊断严重程度
        'treatment_complexity': 0.25,   # 治疗复杂度
        'patient_concern': 0.2,         # 患者关注度
        'follow_up_importance': 0.15,   # 随访重要性
        'document_completeness': 0.1    # 文档完整性
    })
    
    # 自动过期配置（天数）
    auto_expire_days: Dict[str, int] = field(default_factory=lambda: {
        'visit_records': 1095,          # 就诊记录保留3年
        'health_trends': 730,           # 健康趋势保留2年
        'user_preferences': 365,        # 用户偏好保留1年
        'medical_knowledge': 1095,      # 医疗知识保留3年
        'processing_logs': 90,          # 处理日志保留3个月
        'temporary_data': 7             # 临时数据保留1周
    })
    
    # 安全配置
    enable_encryption: bool = True
    encryption_key: Optional[str] = field(default_factory=lambda: os.getenv('MEMORY_ENCRYPTION_KEY'))
    enable_audit_log: bool = True
    
    # 性能配置
    cache_size: int = 1000
    cache_ttl: int = 3600  # 秒
    batch_processing_size: int = 50
    
    # 日志配置
    log_level: str = 'INFO'
    log_file: str = 'visit_summary_memory.log'
    enable_performance_logging: bool = True
    
    def get_visit_type_config(self, visit_type: str) -> Dict[str, Any]:
        """
        获取特定就诊类型的配置
        
        Args:
            visit_type: 就诊类型
            
        Returns:
            配置字典
        """
        base_config = {
            'importance_multiplier': 1.0,
            'retention_days': self.auto_expire_days.get('visit_records', 1095),
            'required_fields': ['date', 'diagnosis', 'treatment'],
            'optional_fields': ['symptoms', 'doctor_notes', 'follow_up']
        }
        
        # 特殊类型的配置调整
        if visit_type in ['急诊记录', '手术记录']:
            base_config['importance_multiplier'] = 1.5
            base_config['retention_days'] = 1825  # 5年
        elif visit_type in ['体检记录', '复查记录']:
            base_config['importance_multiplier'] = 0.8
        
        return base_config
    
    def get_specialty_config(self, specialty: str) -> Dict[str, Any]:
        """
        获取特定专科的配置
        
        Args:
            specialty: 医疗专科
            
        Returns:
            配置字典
        """
        return {
            'terminology_weight': 1.0,
            'complexity_factor': 1.0,
            'follow_up_frequency': 30,  # 天
            'key_indicators': self._get_specialty_indicators(specialty)
        }
    
    def _get_specialty_indicators(self, specialty: str) -> List[str]:
        """
        获取专科关键指标
        
        Args:
            specialty: 医疗专科
            
        Returns:
            关键指标列表
        """
        indicators_map = {
            '心血管科': ['血压', '心率', '心电图', '血脂', '心肌酶'],
            '内分泌科': ['血糖', '胰岛素', '甲状腺功能', 'HbA1c'],
            '肾内科': ['肌酐', '尿素氮', '尿蛋白', '肾小球滤过率'],
            '消化科': ['肝功能', '胃镜', '肠镜', '幽门螺杆菌'],
            '呼吸科': ['肺功能', '胸片', 'CT', '血氧饱和度']
        }
        return indicators_map.get(specialty, ['常规检查', '症状评估'])
    
    def calculate_importance_score(self, 
                                 diagnosis_severity: float,
                                 treatment_complexity: float,
                                 patient_concern: float,
                                 follow_up_importance: float,
                                 document_completeness: float) -> float:
        """
        计算记忆重要性评分
        
        Args:
            diagnosis_severity: 诊断严重程度 (0-1)
            treatment_complexity: 治疗复杂度 (0-1)
            patient_concern: 患者关注度 (0-1)
            follow_up_importance: 随访重要性 (0-1)
            document_completeness: 文档完整性 (0-1)
            
        Returns:
            重要性评分 (0-1)
        """
        weights = self.importance_weights
        score = (
            diagnosis_severity * weights['diagnosis_severity'] +
            treatment_complexity * weights['treatment_complexity'] +
            patient_concern * weights['patient_concern'] +
            follow_up_importance * weights['follow_up_importance'] +
            document_completeness * weights['document_completeness']
        )
        return min(max(score, 0.0), 1.0)
    
    def get_default_tags(self, visit_type: str, specialty: str) -> List[str]:
        """
        获取默认标签
        
        Args:
            visit_type: 就诊类型
            specialty: 医疗专科
            
        Returns:
            标签列表
        """
        tags = ['visit_summary', visit_type.lower(), specialty.lower()]
        
        # 添加时间标签
        now = datetime.now()
        tags.extend([
            f'year_{now.year}',
            f'month_{now.month:02d}',
            f'quarter_Q{(now.month-1)//3 + 1}'
        ])
        
        return tags
    
    def is_memory_expired(self, memory_type: str, created_date: datetime) -> bool:
        """
        判断记忆是否过期
        
        Args:
            memory_type: 记忆类型
            created_date: 创建日期
            
        Returns:
            是否过期
        """
        expire_days = self.auto_expire_days.get(memory_type, 365)
        expire_date = created_date + timedelta(days=expire_days)
        return datetime.now() > expire_date
    
    def get_retention_period(self, memory_type: str, importance_score: float) -> int:
        """
        获取记忆保留期限
        
        Args:
            memory_type: 记忆类型
            importance_score: 重要性评分
            
        Returns:
            保留天数
        """
        base_days = self.auto_expire_days.get(memory_type, 365)
        
        # 根据重要性调整保留期
        if importance_score >= 0.8:
            return int(base_days * 1.5)  # 高重要性延长50%
        elif importance_score >= 0.6:
            return base_days  # 中等重要性保持原样
        else:
            return int(base_days * 0.7)  # 低重要性缩短30%
    
    def should_update_trend(self, last_update: datetime, trend_type: str) -> bool:
        """
        判断是否需要更新健康趋势
        
        Args:
            last_update: 上次更新时间
            trend_type: 趋势类型
            
        Returns:
            是否需要更新
        """
        update_intervals = {
            '血压变化': 1,      # 每天
            '血糖变化': 1,      # 每天
            '体重变化': 7,      # 每周
            '症状变化': 1,      # 每天
            '用药效果': 3,      # 每3天
            '检查指标': 30,     # 每月
            '生活质量': 7       # 每周
        }
        
        interval_days = update_intervals.get(trend_type, 7)
        return datetime.now() > last_update + timedelta(days=interval_days)
    
    def validate_config(self) -> List[str]:
        """
        验证配置有效性
        
        Returns:
            错误信息列表
        """
        errors = []
        
        # 检查必要的环境变量
        if self.enable_encryption and not self.encryption_key:
            errors.append("启用加密但未设置加密密钥")
        
        # 检查数值范围
        if not 0 < self.similarity_threshold <= 1:
            errors.append("相似度阈值必须在0-1之间")
        
        if not 0 < self.importance_threshold <= 1:
            errors.append("重要性阈值必须在0-1之间")
        
        # 检查权重总和
        weight_sum = sum(self.importance_weights.values())
        if abs(weight_sum - 1.0) > 0.01:
            errors.append(f"重要性权重总和应为1.0，当前为{weight_sum}")
        
        return errors

# 全局配置实例
visit_summary_memory_config = VisitSummaryMemoryConfig()