import unittest
import os
import tempfile
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# 导入记忆系统模块
from memory_system import AgentMemorySystem
from database_config import MemoryDatabaseConfig
from memory_storage import MemoryStorage
from memory_retrieval import MemoryRetrieval
from memory_manager import MemoryManager
from embedding_service import EmbeddingService
from config import MemorySystemConfig

class TestMemorySystem(unittest.TestCase):
    """记忆系统测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 使用模拟的数据库配置
        self.mock_db_config = Mock(spec=MemoryDatabaseConfig)
        self.mock_db_config.check_connection.return_value = True
        self.mock_db_config.create_tables.return_value = None
        
        # 创建记忆系统实例
        with patch('memory_system.MemoryDatabaseConfig', return_value=self.mock_db_config):
            self.memory_system = AgentMemorySystem()
        
        # 测试数据
        self.test_agent_id = "test_agent_001"
        self.test_user_id = "test_user_001"
        self.test_content = {
            'text': '这是一条测试记忆',
            'structured_data': {'type': 'test', 'value': 123},
            'metadata': {'source': 'unit_test'}
        }
    
    def tearDown(self):
        """测试后清理"""
        pass
    
    def test_system_initialization(self):
        """测试系统初始化"""
        self.assertIsNotNone(self.memory_system)
        self.assertIsNotNone(self.memory_system.storage)
        self.assertIsNotNone(self.memory_system.retrieval)
        self.assertIsNotNone(self.memory_system.manager)
        self.assertIsNotNone(self.memory_system.embedding_service)
    
    @patch('memory_system.MemoryStorage.store_memory')
    def test_store_memory(self, mock_store):
        """测试存储记忆"""
        mock_store.return_value = "memory_123"
        
        memory_id = self.memory_system.store_memory(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            content=self.test_content,
            memory_type='long_term',
            importance=0.8,
            tags=['测试', '单元测试']
        )
        
        self.assertEqual(memory_id, "memory_123")
        mock_store.assert_called_once()
    
    @patch('memory_system.MemoryStorage.get_memory')
    def test_get_memory(self, mock_get):
        """测试获取记忆"""
        expected_memory = {
            'id': 'memory_123',
            'agent_id': self.test_agent_id,
            'user_id': self.test_user_id,
            'content': self.test_content,
            'memory_type': 'long_term',
            'importance': 0.8,
            'created_at': datetime.now().isoformat()
        }
        mock_get.return_value = expected_memory
        
        memory = self.memory_system.get_memory("memory_123")
        
        self.assertEqual(memory, expected_memory)
        mock_get.assert_called_once_with("memory_123")
    
    @patch('memory_system.MemoryRetrieval.search_by_content')
    def test_search_memories(self, mock_search):
        """测试搜索记忆"""
        expected_results = [
            {
                'id': 'memory_123',
                'content': self.test_content,
                'similarity': 0.85
            }
        ]
        mock_search.return_value = expected_results
        
        results = self.memory_system.search_memories(
            query="测试查询",
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            limit=10
        )
        
        self.assertEqual(results, expected_results)
        mock_search.assert_called_once()
    
    @patch('memory_system.MemoryRetrieval.get_recent_memories')
    def test_get_recent_memories(self, mock_recent):
        """测试获取最近记忆"""
        expected_memories = [
            {
                'id': 'memory_123',
                'content': self.test_content,
                'created_at': datetime.now().isoformat()
            }
        ]
        mock_recent.return_value = expected_memories
        
        memories = self.memory_system.get_recent_memories(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            hours=24
        )
        
        self.assertEqual(memories, expected_memories)
        mock_recent.assert_called_once()
    
    @patch('memory_system.MemoryManager.evaluate_importance')
    def test_evaluate_memory_importance(self, mock_evaluate):
        """测试评估记忆重要性"""
        mock_evaluate.return_value = 0.75
        
        importance = self.memory_system.evaluate_memory_importance("memory_123")
        
        self.assertEqual(importance, 0.75)
        mock_evaluate.assert_called_once_with("memory_123")
    
    @patch('memory_system.MemoryManager.cleanup_expired')
    def test_cleanup_expired_memories(self, mock_cleanup):
        """测试清理过期记忆"""
        mock_cleanup.return_value = 5
        
        cleaned_count = self.memory_system.cleanup_expired_memories()
        
        self.assertEqual(cleaned_count, 5)
        mock_cleanup.assert_called_once()
    
    def test_store_conversation_memory(self):
        """测试存储对话记忆"""
        with patch.object(self.memory_system, 'store_memory') as mock_store:
            mock_store.return_value = "conv_memory_123"
            
            memory_id = self.memory_system.store_conversation_memory(
                agent_id=self.test_agent_id,
                user_id=self.test_user_id,
                user_message="你好",
                agent_response="您好！有什么可以帮助您的吗？",
                context={'session_id': 'session_001'}
            )
            
            self.assertEqual(memory_id, "conv_memory_123")
            mock_store.assert_called_once()
            
            # 检查调用参数
            call_args = mock_store.call_args
            self.assertEqual(call_args[1]['memory_type'], 'working')
            self.assertIn('对话', call_args[1]['tags'])
    
    def test_store_health_record_memory(self):
        """测试存储健康档案记忆"""
        with patch.object(self.memory_system, 'store_memory') as mock_store:
            mock_store.return_value = "health_memory_123"
            
            record_data = {
                'summary': '血压检查正常',
                'blood_pressure': '120/80',
                'date': '2024-01-15'
            }
            
            memory_id = self.memory_system.store_health_record_memory(
                agent_id=self.test_agent_id,
                user_id=self.test_user_id,
                record_type="血压检查",
                record_data=record_data
            )
            
            self.assertEqual(memory_id, "health_memory_123")
            mock_store.assert_called_once()
            
            # 检查调用参数
            call_args = mock_store.call_args
            self.assertEqual(call_args[1]['memory_type'], 'long_term')
            self.assertIn('健康档案', call_args[1]['tags'])
    
    def test_store_medication_memory(self):
        """测试存储用药记忆"""
        with patch.object(self.memory_system, 'store_memory') as mock_store:
            mock_store.return_value = "med_memory_123"
            
            medication_info = {
                'medication_name': '阿司匹林',
                'dosage': '100mg',
                'frequency': '每日一次',
                'time': '08:00'
            }
            
            memory_id = self.memory_system.store_medication_memory(
                agent_id=self.test_agent_id,
                user_id=self.test_user_id,
                medication_info=medication_info
            )
            
            self.assertEqual(memory_id, "med_memory_123")
            mock_store.assert_called_once()
            
            # 检查调用参数
            call_args = mock_store.call_args
            self.assertEqual(call_args[1]['memory_type'], 'working')
            self.assertIn('用药提醒', call_args[1]['tags'])
    
    @patch('memory_system.MemoryDatabaseConfig.check_connection')
    @patch('memory_system.MemoryDatabaseConfig.get_table_info')
    @patch('memory_system.EmbeddingService.get_model_info')
    def test_get_system_status(self, mock_model_info, mock_table_info, mock_check_conn):
        """测试获取系统状态"""
        mock_check_conn.return_value = True
        mock_table_info.return_value = {'memories': 100, 'embeddings': 100}
        mock_model_info.return_value = {'model': 'all-MiniLM-L6-v2', 'device': 'cpu'}
        
        status = self.memory_system.get_system_status()
        
        self.assertTrue(status['database_connected'])
        self.assertIn('table_statistics', status)
        self.assertIn('embedding_service', status)
        self.assertIn('system_time', status)
    
    @patch('memory_system.AgentMemorySystem.cleanup_expired_memories')
    @patch('memory_system.AgentMemorySystem.cleanup_low_importance_memories')
    @patch('memory_system.AgentMemorySystem.compress_memories')
    def test_perform_maintenance(self, mock_compress, mock_cleanup_low, mock_cleanup_expired):
        """测试执行系统维护"""
        mock_cleanup_expired.return_value = 5
        mock_cleanup_low.return_value = 3
        mock_compress.return_value = 2
        
        results = self.memory_system.perform_maintenance(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id
        )
        
        self.assertEqual(results['expired_cleaned'], 5)
        self.assertEqual(results['low_importance_cleaned'], 3)
        self.assertEqual(results['memories_compressed'], 2)

class TestMemorySystemConfig(unittest.TestCase):
    """记忆系统配置测试类"""
    
    def test_get_config(self):
        """测试获取配置"""
        # 测试获取所有配置
        all_config = MemorySystemConfig.get_config()
        self.assertIn('database', all_config)
        self.assertIn('embedding', all_config)
        self.assertIn('memory_management', all_config)
        
        # 测试获取特定配置
        db_config = MemorySystemConfig.get_config('database')
        self.assertIn('host', db_config)
        self.assertIn('port', db_config)
    
    def test_validate_config(self):
        """测试配置验证"""
        with patch.dict(os.environ, {
            'MEMORY_DB_HOST': 'localhost',
            'MEMORY_DB_USER': 'test',
            'MEMORY_DB_PASSWORD': 'test',
            'MEMORY_DB_NAME': 'test_db'
        }):
            validation = MemorySystemConfig.validate_config()
            # 在有必需环境变量的情况下，应该通过基本验证
            self.assertIsInstance(validation, dict)
            self.assertIn('valid', validation)
            self.assertIn('issues', validation)
            self.assertIn('warnings', validation)
    
    def test_get_agent_config(self):
        """测试获取智能体配置"""
        health_config = MemorySystemConfig.get_agent_config('health_records')
        self.assertEqual(health_config['memory_type'], 'long_term')
        self.assertIn('健康档案', health_config['required_tags'])
        
        # 测试未知智能体类型
        unknown_config = MemorySystemConfig.get_agent_config('unknown_agent')
        self.assertEqual(unknown_config, MemorySystemConfig.AGENT_SPECIFIC_CONFIG['general'])
    
    def test_get_memory_type_config(self):
        """测试获取记忆类型配置"""
        long_term_config = MemorySystemConfig.get_memory_type_config('long_term')
        self.assertIsNone(long_term_config['default_expires_hours'])
        self.assertEqual(long_term_config['max_importance'], 1.0)
        
        # 测试未知记忆类型
        unknown_config = MemorySystemConfig.get_memory_type_config('unknown_type')
        self.assertEqual(unknown_config, MemorySystemConfig.MEMORY_TYPES_CONFIG['working'])

class TestEmbeddingService(unittest.TestCase):
    """嵌入服务测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 使用模拟的嵌入服务
        with patch('embedding_service.SentenceTransformer'):
            self.embedding_service = EmbeddingService()
    
    @patch('embedding_service.SentenceTransformer')
    def test_load_model(self, mock_transformer):
        """测试加载模型"""
        mock_model = Mock()
        mock_transformer.return_value = mock_model
        
        service = EmbeddingService()
        self.assertIsNotNone(service.model)
    
    def test_generate_embedding(self):
        """测试生成嵌入"""
        with patch.object(self.embedding_service, 'model') as mock_model:
            mock_model.encode.return_value = [0.1, 0.2, 0.3]
            
            embedding = self.embedding_service.generate_embedding("测试文本")
            self.assertEqual(embedding, [0.1, 0.2, 0.3])
    
    def test_calculate_similarity(self):
        """测试计算相似度"""
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [1.0, 0.0, 0.0]
        embedding3 = [0.0, 1.0, 0.0]
        
        # 相同向量的相似度应该为1
        similarity1 = self.embedding_service.calculate_similarity(embedding1, embedding2)
        self.assertAlmostEqual(similarity1, 1.0, places=5)
        
        # 正交向量的相似度应该为0
        similarity2 = self.embedding_service.calculate_similarity(embedding1, embedding3)
        self.assertAlmostEqual(similarity2, 0.0, places=5)

def run_tests():
    """运行所有测试"""
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_suite.addTest(unittest.makeSuite(TestMemorySystem))
    test_suite.addTest(unittest.makeSuite(TestMemorySystemConfig))
    test_suite.addTest(unittest.makeSuite(TestEmbeddingService))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    # 设置测试环境变量
    os.environ.update({
        'MEMORY_DB_HOST': 'localhost',
        'MEMORY_DB_USER': 'test',
        'MEMORY_DB_PASSWORD': 'test',
        'MEMORY_DB_NAME': 'test_memory',
        'EMBEDDING_MODEL': 'all-MiniLM-L6-v2',
        'EMBEDDING_DEVICE': 'cpu'
    })
    
    # 运行测试
    success = run_tests()
    
    if success:
        print("\n✅ 所有测试通过！")
    else:
        print("\n❌ 部分测试失败！")
        exit(1)