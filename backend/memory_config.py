import os
from typing import Any, Dict


class MemorySystemConfig:
    """记忆系统配置类

    管理记忆系统的所有配置参数
    """

    # 数据库配置
    DATABASE_CONFIG = {
        'host': os.getenv('MEMORY_DB_HOST', 'localhost'),
        'port': int(os.getenv('MEMORY_DB_PORT', 3306)),
        'user': os.getenv('MEMORY_DB_USER', 'root'),
        'password': os.getenv('MEMORY_DB_PASSWORD', ''),
        'database': os.getenv('MEMORY_DB_NAME', 'agent_memory'),
        'charset': 'utf8mb4',
        'autocommit': True
    }

    # 连接池配置
    CONNECTION_POOL_CONFIG = {
        'pool_name': 'memory_pool',
        'pool_size': int(os.getenv('MEMORY_DB_POOL_SIZE', 10)),
        'pool_reset_session': True,
        'pool_pre_ping': True,
        'max_overflow': int(os.getenv('MEMORY_DB_MAX_OVERFLOW', 20))
    }

    # 嵌入模型配置
    EMBEDDING_CONFIG = {
        'model_name': os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2'),
        'backup_models': [
            'paraphrase-MiniLM-L6-v2',
            'all-mpnet-base-v2'
        ],
        'device': os.getenv('EMBEDDING_DEVICE', 'cpu'),
        'max_seq_length': int(os.getenv('EMBEDDING_MAX_LENGTH', 512)),
        'batch_size': int(os.getenv('EMBEDDING_BATCH_SIZE', 32))
    }

    # 记忆管理配置
    MEMORY_MANAGEMENT_CONFIG = {
        # 重要性评估权重
        'importance_weights': {
            'base_score': 0.3,
            'access_frequency': 0.25,
            'time_decay': 0.2,
            'association_count': 0.15,
            'tag_richness': 0.1
        },

        # 时间衰减参数
        'time_decay': {
            'half_life_days': int(os.getenv('MEMORY_HALF_LIFE_DAYS', 30)),
            'min_decay_factor': float(os.getenv('MEMORY_MIN_DECAY', 0.1))
        },

        # 记忆压缩配置
        'compression': {
            'similarity_threshold': float(os.getenv('MEMORY_SIMILARITY_THRESHOLD', 0.85)),
            'min_memories_for_compression': int(os.getenv('MEMORY_MIN_COMPRESS', 5)),
            'max_compression_batch': int(os.getenv('MEMORY_MAX_COMPRESS_BATCH', 100))
        },

        # 清理配置
        'cleanup': {
            'expired_check_interval_hours': int(os.getenv('MEMORY_CLEANUP_INTERVAL', 24)),
            'low_importance_threshold': float(os.getenv('MEMORY_LOW_IMPORTANCE', 0.2)),
            'max_age_days_for_cleanup': int(os.getenv('MEMORY_MAX_AGE_CLEANUP', 90))
        }
    }

    # 检索配置
    RETRIEVAL_CONFIG = {
        'default_similarity_threshold': float(os.getenv('MEMORY_DEFAULT_SIMILARITY', 0.5)),
        'max_search_results': int(os.getenv('MEMORY_MAX_SEARCH_RESULTS', 50)),
        'semantic_search_enabled': os.getenv('MEMORY_SEMANTIC_SEARCH', 'true').lower() == 'true',
        'fallback_to_text_search': os.getenv('MEMORY_FALLBACK_TEXT_SEARCH', 'true').lower() == 'true'
    }

    # 记忆类型配置
    MEMORY_TYPES_CONFIG = {
        'short_term': {
            'default_expires_hours': 24,
            'max_importance': 0.6,
            'auto_cleanup': True
        },
        'working': {
            'default_expires_hours': 168,  # 7天
            'max_importance': 0.8,
            'auto_cleanup': True
        },
        'long_term': {
            'default_expires_hours': None,  # 永不过期
            'max_importance': 1.0,
            'auto_cleanup': False
        },
        'meta': {
            'default_expires_hours': None,
            'max_importance': 0.9,
            'auto_cleanup': False
        }
    }

    # 智能体特化配置
    AGENT_SPECIFIC_CONFIG = {
        'health_records': {
            'default_importance': 0.8,
            'memory_type': 'long_term',
            'required_tags': ['健康档案'],
            'retention_policy': 'permanent'
        },
        'health_advisor': {
            'default_importance': 0.7,
            'memory_type': 'working',
            'required_tags': ['健康咨询'],
            'retention_policy': 'medium_term'
        },
        'medication_reminder': {
            'default_importance': 0.7,
            'memory_type': 'working',
            'required_tags': ['用药提醒'],
            'retention_policy': 'short_term'
        },
        'general': {
            'default_importance': 0.5,
            'memory_type': 'working',
            'required_tags': [],
            'retention_policy': 'standard'
        }
    }

    # 安全配置
    SECURITY_CONFIG = {
        'encryption_enabled': os.getenv('MEMORY_ENCRYPTION_ENABLED', 'true').lower() == 'true',
        'encryption_key': os.getenv('MEMORY_ENCRYPTION_KEY', ''),
        'hash_sensitive_data': os.getenv('MEMORY_HASH_SENSITIVE', 'true').lower() == 'true',
        'audit_enabled': os.getenv('MEMORY_AUDIT_ENABLED', 'true').lower() == 'true'
    }

    # 性能配置
    PERFORMANCE_CONFIG = {
        'cache_enabled': os.getenv('MEMORY_CACHE_ENABLED', 'true').lower() == 'true',
        'cache_size': int(os.getenv('MEMORY_CACHE_SIZE', 1000)),
        'cache_ttl_seconds': int(os.getenv('MEMORY_CACHE_TTL', 3600)),
        'async_operations': os.getenv('MEMORY_ASYNC_OPS', 'true').lower() == 'true',
        'batch_operations': os.getenv('MEMORY_BATCH_OPS', 'true').lower() == 'true'
    }

    # 日志配置
    LOGGING_CONFIG = {
        'level': os.getenv('MEMORY_LOG_LEVEL', 'INFO'),
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'file_path': os.getenv('MEMORY_LOG_FILE', 'logs/memory_system.log'),
        'max_file_size': int(os.getenv('MEMORY_LOG_MAX_SIZE', 10485760)),  # 10MB
        'backup_count': int(os.getenv('MEMORY_LOG_BACKUP_COUNT', 5))
    }

    @classmethod
    def get_config(cls, section: str = None) -> Dict[str, Any]:
        """获取配置

        Args:
            section: 配置节名称，如果为None则返回所有配置

        Returns:
            Dict: 配置字典
        """
        if section is None:
            return {
                'database': cls.DATABASE_CONFIG,
                'connection_pool': cls.CONNECTION_POOL_CONFIG,
                'embedding': cls.EMBEDDING_CONFIG,
                'memory_management': cls.MEMORY_MANAGEMENT_CONFIG,
                'retrieval': cls.RETRIEVAL_CONFIG,
                'memory_types': cls.MEMORY_TYPES_CONFIG,
                'agent_specific': cls.AGENT_SPECIFIC_CONFIG,
                'security': cls.SECURITY_CONFIG,
                'performance': cls.PERFORMANCE_CONFIG,
                'logging': cls.LOGGING_CONFIG
            }

        config_map = {
            'database': cls.DATABASE_CONFIG,
            'connection_pool': cls.CONNECTION_POOL_CONFIG,
            'embedding': cls.EMBEDDING_CONFIG,
            'memory_management': cls.MEMORY_MANAGEMENT_CONFIG,
            'retrieval': cls.RETRIEVAL_CONFIG,
            'memory_types': cls.MEMORY_TYPES_CONFIG,
            'agent_specific': cls.AGENT_SPECIFIC_CONFIG,
            'security': cls.SECURITY_CONFIG,
            'performance': cls.PERFORMANCE_CONFIG,
            'logging': cls.LOGGING_CONFIG
        }

        return config_map.get(section, {})

    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """验证配置

        Returns:
            Dict: 验证结果
        """
        issues = []
        warnings = []

        # 检查必需的环境变量
        required_vars = [
            'MEMORY_DB_HOST',
            'MEMORY_DB_USER',
            'MEMORY_DB_PASSWORD',
            'MEMORY_DB_NAME'
        ]

        for var in required_vars:
            if not os.getenv(var):
                issues.append(f"缺少必需的环境变量: {var}")

        # 检查数据库连接参数
        if cls.DATABASE_CONFIG['port'] < 1 or cls.DATABASE_CONFIG['port'] > 65535:
            issues.append("数据库端口号无效")

        # 检查连接池配置
        if cls.CONNECTION_POOL_CONFIG['pool_size'] < 1:
            issues.append("连接池大小必须大于0")

        # 检查嵌入模型配置
        if cls.EMBEDDING_CONFIG['max_seq_length'] < 1:
            issues.append("嵌入模型最大序列长度必须大于0")

        # 检查重要性权重总和
        weights = cls.MEMORY_MANAGEMENT_CONFIG['importance_weights']
        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 0.01:
            warnings.append(f"重要性权重总和不等于1.0: {total_weight}")

        # 检查阈值范围
        similarity_threshold = cls.MEMORY_MANAGEMENT_CONFIG['compression']['similarity_threshold']
        if similarity_threshold < 0 or similarity_threshold > 1:
            issues.append("相似度阈值必须在0-1之间")

        default_similarity = cls.RETRIEVAL_CONFIG['default_similarity_threshold']
        if default_similarity < 0 or default_similarity > 1:
            issues.append("默认相似度阈值必须在0-1之间")

        # 检查加密配置
        if cls.SECURITY_CONFIG['encryption_enabled'] and not cls.SECURITY_CONFIG['encryption_key']:
            issues.append("启用加密但未提供加密密钥")

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }

    @classmethod
    def get_agent_config(cls, agent_type: str) -> Dict[str, Any]:
        """获取特定智能体的配置

        Args:
            agent_type: 智能体类型

        Returns:
            Dict: 智能体配置
        """
        return cls.AGENT_SPECIFIC_CONFIG.get(agent_type, cls.AGENT_SPECIFIC_CONFIG['general'])

    @classmethod
    def get_memory_type_config(cls, memory_type: str) -> Dict[str, Any]:
        """获取记忆类型配置

        Args:
            memory_type: 记忆类型

        Returns:
            Dict: 记忆类型配置
        """
        return cls.MEMORY_TYPES_CONFIG.get(memory_type, cls.MEMORY_TYPES_CONFIG['working'])


# 全局配置实例
config = MemorySystemConfig()
