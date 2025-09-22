#!/usr/bin/env python3
"""
健康档案管理器记忆集成配置

这个模块为健康档案管理器提供记忆系统的配置和初始化功能。
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

class HealthRecordsMemoryConfig:
    """健康档案管理器记忆配置类"""
    
    def __init__(self):
        """初始化配置"""
        self.agent_id = "health_records_manager"
        self.agent_name = "健康档案管理员"
        self.agent_version = "1.0.0"
        
        # 记忆系统配置
        self.memory_config = {
            # 数据库配置
            "database": {
                "host": os.getenv("MEMORY_DB_HOST", "localhost"),
                "port": int(os.getenv("MEMORY_DB_PORT", "3306")),
                "database": os.getenv("MEMORY_DB_NAME", "agent_memory"),
                "user": os.getenv("MEMORY_DB_USER", "root"),
                "password": os.getenv("MEMORY_DB_PASSWORD", "password"),
                "charset": "utf8mb4",
                "autocommit": True
            },
            
            # 嵌入模型配置
            "embedding": {
                "model_name": os.getenv("MEMORY_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
                "model_cache_dir": os.getenv("MEMORY_MODEL_CACHE_DIR", "./models"),
                "batch_size": int(os.getenv("MEMORY_EMBEDDING_BATCH_SIZE", "32")),
                "max_length": int(os.getenv("MEMORY_EMBEDDING_MAX_LENGTH", "512"))
            },
            
            # 记忆管理配置
            "memory_management": {
                "importance_weights": {
                    "base_score": 0.3,
                    "access_frequency": 0.25,
                    "time_decay": 0.2,
                    "association_strength": 0.15,
                    "tag_richness": 0.1
                },
                "time_decay_factor": 0.95,
                "compression_similarity_threshold": 0.85,
                "cleanup_low_importance_threshold": 0.3,
                "cleanup_max_age_days": 365
            },
            
            # 检索配置
            "retrieval": {
                "default_limit": 20,
                "max_limit": 100,
                "min_similarity_threshold": 0.3,
                "semantic_search_weight": 0.7,
                "keyword_search_weight": 0.3
            },
            
            # 健康档案特定配置
            "health_records": {
                "default_memory_type": "long_term",
                "urgent_importance_boost": 0.2,
                "medical_record_types": [
                    "体检报告", "诊断记录", "处方单", "化验单", 
                    "影像报告", "手术记录", "住院记录", "疫苗记录",
                    "过敏记录", "用药记录", "生命体征", "健康指标"
                ],
                "critical_tags": [
                    "紧急", "异常", "高风险", "慢性病", "过敏", 
                    "手术", "住院", "重要检查", "药物不良反应"
                ],
                "auto_expire_days": {
                    "OCR识别": 30,
                    "临时记录": 7,
                    "工作记忆": 30,
                    "长期记录": None  # 不自动过期
                }
            },
            
            # 安全配置
            "security": {
                "encrypt_sensitive_data": True,
                "encryption_key_env": "MEMORY_ENCRYPTION_KEY",
                "access_log_enabled": True,
                "audit_trail_enabled": True,
                "data_retention_days": 2555  # 7年
            },
            
            # 性能配置
            "performance": {
                "connection_pool_size": 10,
                "connection_pool_max_overflow": 20,
                "query_timeout": 30,
                "batch_insert_size": 100,
                "cache_enabled": True,
                "cache_ttl_seconds": 3600
            },
            
            # 日志配置
            "logging": {
                "level": os.getenv("MEMORY_LOG_LEVEL", "INFO"),
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file_path": os.getenv("MEMORY_LOG_FILE", "./logs/memory_system.log"),
                "max_file_size": "10MB",
                "backup_count": 5
            }
        }
    
    def get_database_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.memory_config["database"]
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """获取嵌入模型配置"""
        return self.memory_config["embedding"]
    
    def get_health_records_config(self) -> Dict[str, Any]:
        """获取健康档案特定配置"""
        return self.memory_config["health_records"]
    
    def get_security_config(self) -> Dict[str, Any]:
        """获取安全配置"""
        return self.memory_config["security"]
    
    def get_performance_config(self) -> Dict[str, Any]:
        """获取性能配置"""
        return self.memory_config["performance"]
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.memory_config["logging"]
    
    def is_critical_record_type(self, record_type: str) -> bool:
        """判断是否为关键记录类型"""
        medical_types = self.memory_config["health_records"]["medical_record_types"]
        return record_type in medical_types
    
    def is_critical_tag(self, tag: str) -> bool:
        """判断是否为关键标签"""
        critical_tags = self.memory_config["health_records"]["critical_tags"]
        return tag in critical_tags
    
    def get_auto_expire_days(self, record_type: str) -> Optional[int]:
        """获取记录类型的自动过期天数"""
        auto_expire = self.memory_config["health_records"]["auto_expire_days"]
        return auto_expire.get(record_type)
    
    def calculate_importance_score(self, 
                                 base_score: float = 0.5,
                                 is_urgent: bool = False,
                                 is_critical_type: bool = False,
                                 has_critical_tags: bool = False,
                                 confidence: float = 1.0) -> float:
        """计算重要性评分"""
        importance = base_score
        
        # 紧急记录加分
        if is_urgent:
            importance += self.memory_config["health_records"]["urgent_importance_boost"]
        
        # 关键记录类型加分
        if is_critical_type:
            importance += 0.15
        
        # 关键标签加分
        if has_critical_tags:
            importance += 0.1
        
        # 置信度调整
        importance *= confidence
        
        # 确保在有效范围内
        return min(1.0, max(0.0, importance))
    
    def get_default_tags_for_record_type(self, record_type: str) -> list:
        """获取记录类型的默认标签"""
        default_tags = ["健康档案", record_type]
        
        # 根据记录类型添加特定标签
        type_specific_tags = {
            "体检报告": ["体检", "健康评估"],
            "诊断记录": ["诊断", "医疗记录"],
            "处方单": ["处方", "用药"],
            "化验单": ["化验", "检查结果"],
            "影像报告": ["影像", "检查结果"],
            "手术记录": ["手术", "重要医疗"],
            "住院记录": ["住院", "重要医疗"],
            "疫苗记录": ["疫苗", "预防接种"],
            "过敏记录": ["过敏", "重要信息"],
            "用药记录": ["用药", "药物管理"],
            "生命体征": ["生命体征", "监测数据"],
            "健康指标": ["健康指标", "监测数据"]
        }
        
        if record_type in type_specific_tags:
            default_tags.extend(type_specific_tags[record_type])
        
        return default_tags
    
    def validate_config(self) -> bool:
        """验证配置的有效性"""
        try:
            # 检查必要的环境变量
            required_env_vars = [
                "MEMORY_DB_HOST", "MEMORY_DB_PORT", "MEMORY_DB_NAME",
                "MEMORY_DB_USER", "MEMORY_DB_PASSWORD"
            ]
            
            missing_vars = []
            for var in required_env_vars:
                if not os.getenv(var):
                    missing_vars.append(var)
            
            if missing_vars:
                logger.warning(f"缺少环境变量: {missing_vars}，将使用默认值")
            
            # 检查数据库配置
            db_config = self.get_database_config()
            if not all([db_config["host"], db_config["database"], 
                       db_config["user"], db_config["password"]]):
                logger.error("数据库配置不完整")
                return False
            
            # 检查嵌入模型配置
            embedding_config = self.get_embedding_config()
            if not embedding_config["model_name"]:
                logger.error("嵌入模型配置不完整")
                return False
            
            logger.info("记忆系统配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    def get_memory_system_init_params(self) -> Dict[str, Any]:
        """获取记忆系统初始化参数"""
        return {
            "config": self.memory_config,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"HealthRecordsMemoryConfig(agent_id={self.agent_id}, version={self.agent_version})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()

# 全局配置实例
health_records_memory_config = HealthRecordsMemoryConfig()

# 配置验证
if not health_records_memory_config.validate_config():
    logger.warning("记忆系统配置验证失败，某些功能可能无法正常工作")

# 导出配置
__all__ = [
    "HealthRecordsMemoryConfig",
    "health_records_memory_config"
]