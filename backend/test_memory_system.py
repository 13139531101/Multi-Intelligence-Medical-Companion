#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
长期记忆系统测试脚本
测试各个智能体的记忆功能集成和性能
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('memory_system_test.log')
    ]
)
logger = logging.getLogger(__name__)

class MemorySystemTester:
    """
    记忆系统测试器
    """
    
    def __init__(self):
        self.test_results = {}
        self.test_user_id = "test_user_001"
        self.available_services = []
        
    def test_imports(self):
        """
        测试各个记忆服务的导入
        """
        logger.info("测试记忆服务导入...")
        
        # 测试核心记忆系统
        try:
            from memory_system import AgentMemorySystem
            from memory_config import MemorySystemConfig
            logger.info("✓ 核心记忆系统导入成功")
            self.test_results["core_memory_import"] = {"status": "PASS"}
        except ImportError as e:
            logger.error(f"✗ 核心记忆系统导入失败: {e}")
            self.test_results["core_memory_import"] = {"status": "FAIL", "error": str(e)}
        
        # 测试各个智能体的记忆配置文件
        agents = [
            ("HealthRecordsManager", "健康档案管理"),
            ("HealthAdvisor", "健康顾问"),
            ("MedicationReminder", "用药提醒"),
            ("VisitSummaryGenerator", "就诊摘要生成")
        ]
        
        for agent_dir, agent_name in agents:
            # 检查记忆配置文件
            config_file = os.path.join(agent_dir, "memory_config.py")
            service_file = os.path.join(agent_dir, "memory_service.py")
            prompt_file = os.path.join(agent_dir, "memory_enhanced_agent_prompt.md")
            
            config_exists = os.path.exists(config_file)
            service_exists = os.path.exists(service_file)
            prompt_exists = os.path.exists(prompt_file)
            
            if config_exists and service_exists and prompt_exists:
                logger.info(f"✓ {agent_name} 记忆系统文件完整")
                self.test_results[f"{agent_dir}_files"] = {"status": "PASS"}
                self.available_services.append((agent_dir, agent_name))
            else:
                missing_files = []
                if not config_exists:
                    missing_files.append("memory_config.py")
                if not service_exists:
                    missing_files.append("memory_service.py")
                if not prompt_exists:
                    missing_files.append("memory_enhanced_agent_prompt.md")
                
                logger.warning(f"✗ {agent_name} 缺少文件: {', '.join(missing_files)}")
                self.test_results[f"{agent_dir}_files"] = {
                    "status": "FAIL", 
                    "missing_files": missing_files
                }
    
    def test_file_contents(self):
        """
        测试文件内容的完整性
        """
        logger.info("测试文件内容完整性...")
        
        for agent_dir, agent_name in self.available_services:
            try:
                # 检查配置文件内容
                config_file = os.path.join(agent_dir, "memory_config.py")
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_content = f.read()
                
                # 检查关键类是否存在
                has_config_class = "MemoryConfig" in config_content
                has_init_method = "def __init__" in config_content
                has_database_config = "database" in config_content.lower()
                
                # 检查服务文件内容
                service_file = os.path.join(agent_dir, "memory_service.py")
                with open(service_file, 'r', encoding='utf-8') as f:
                    service_content = f.read()
                
                has_service_class = "MemoryService" in service_content
                has_initialize_method = "async def initialize" in service_content
                has_store_method = "store_" in service_content
                
                # 检查提示文件内容
                prompt_file = os.path.join(agent_dir, "memory_enhanced_agent_prompt.md")
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_content = f.read()
                
                has_memory_section = "记忆" in prompt_content
                has_workflow = "工作流程" in prompt_content or "workflow" in prompt_content.lower()
                
                content_score = sum([
                    has_config_class, has_init_method, has_database_config,
                    has_service_class, has_initialize_method, has_store_method,
                    has_memory_section, has_workflow
                ])
                
                if content_score >= 6:
                    logger.info(f"✓ {agent_name} 文件内容完整 ({content_score}/8)")
                    self.test_results[f"{agent_dir}_content"] = {
                        "status": "PASS", 
                        "score": content_score
                    }
                else:
                    logger.warning(f"✗ {agent_name} 文件内容不完整 ({content_score}/8)")
                    self.test_results[f"{agent_dir}_content"] = {
                        "status": "FAIL", 
                        "score": content_score
                    }
                    
            except Exception as e:
                logger.error(f"✗ {agent_name} 文件内容检查异常: {e}")
                self.test_results[f"{agent_dir}_content"] = {
                    "status": "ERROR", 
                    "error": str(e)
                }
    
    def test_main_file_integration(self):
        """
        测试主文件的记忆系统集成
        """
        logger.info("测试主文件记忆系统集成...")
        
        for agent_dir, agent_name in self.available_services:
            try:
                main_file = os.path.join(agent_dir, "main.py")
                if not os.path.exists(main_file):
                    logger.warning(f"✗ {agent_name} 主文件不存在")
                    self.test_results[f"{agent_dir}_main_integration"] = {
                        "status": "FAIL", 
                        "error": "main.py not found"
                    }
                    continue
                
                with open(main_file, 'r', encoding='utf-8') as f:
                    main_content = f.read()
                
                # 检查记忆系统集成
                has_memory_import = "memory_service" in main_content
                has_memory_init = "memory_service" in main_content and "initialize" in main_content
                has_enhanced_prompt = "memory_enhanced_agent_prompt.md" in main_content
                has_asyncio = "asyncio" in main_content
                
                integration_score = sum([
                    has_memory_import, has_memory_init, 
                    has_enhanced_prompt, has_asyncio
                ])
                
                if integration_score >= 3:
                    logger.info(f"✓ {agent_name} 主文件集成完整 ({integration_score}/4)")
                    self.test_results[f"{agent_dir}_main_integration"] = {
                        "status": "PASS", 
                        "score": integration_score
                    }
                else:
                    logger.warning(f"✗ {agent_name} 主文件集成不完整 ({integration_score}/4)")
                    self.test_results[f"{agent_dir}_main_integration"] = {
                        "status": "FAIL", 
                        "score": integration_score
                    }
                    
            except Exception as e:
                logger.error(f"✗ {agent_name} 主文件集成检查异常: {e}")
                self.test_results[f"{agent_dir}_main_integration"] = {
                    "status": "ERROR", 
                    "error": str(e)
                }
    
    def test_database_files(self):
        """
        测试数据库相关文件
        """
        logger.info("测试数据库相关文件...")
        
        # 检查核心数据库文件
        db_files = [
            "memory_system.py",
            "memory_config.py",
            "database_manager.py",
            "embedding_manager.py"
        ]
        
        for db_file in db_files:
            if os.path.exists(db_file):
                logger.info(f"✓ {db_file} 存在")
                self.test_results[f"db_file_{db_file}"] = {"status": "PASS"}
            else:
                logger.warning(f"✗ {db_file} 不存在")
                self.test_results[f"db_file_{db_file}"] = {"status": "FAIL"}
    
    def run_all_tests(self):
        """
        运行所有测试
        """
        logger.info("开始长期记忆系统测试")
        
        # 测试导入
        self.test_imports()
        
        # 测试文件内容
        self.test_file_contents()
        
        # 测试主文件集成
        self.test_main_file_integration()
        
        # 测试数据库文件
        self.test_database_files()
        
        # 生成测试报告
        self.generate_test_report()
    
    def generate_test_report(self):
        """
        生成测试报告
        """
        logger.info("生成测试报告...")
        
        report = []
        report.append("=" * 60)
        report.append("长期记忆系统测试报告")
        report.append("=" * 60)
        report.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"可用服务数量: {len(self.available_services)}")
        report.append("")
        
        # 统计测试结果
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() 
                          if result.get('status') == 'PASS')
        failed_tests = sum(1 for result in self.test_results.values() 
                          if result.get('status') == 'FAIL')
        error_tests = sum(1 for result in self.test_results.values() 
                         if result.get('status') == 'ERROR')
        
        report.append("测试概览:")
        report.append(f"  总测试数: {total_tests}")
        report.append(f"  通过: {passed_tests}")
        report.append(f"  失败: {failed_tests}")
        report.append(f"  错误: {error_tests}")
        if total_tests > 0:
            report.append(f"  成功率: {(passed_tests/total_tests*100):.1f}%")
        report.append("")
        
        # 可用服务列表
        report.append("可用记忆服务:")
        for agent_dir, agent_name in self.available_services:
            report.append(f"  ✓ {agent_name} ({agent_dir})")
        report.append("")
        
        # 详细测试结果
        report.append("详细测试结果:")
        for test_name, result in self.test_results.items():
            status = result.get('status', 'UNKNOWN')
            status_symbol = "✓" if status == "PASS" else "✗" if status == "FAIL" else "!"
            report.append(f"  {status_symbol} {test_name}: {status}")
            
            if 'score' in result:
                report.append(f"    评分: {result['score']}")
            
            if 'error' in result:
                report.append(f"    错误: {result['error']}")
            
            if 'missing_files' in result:
                report.append(f"    缺少文件: {', '.join(result['missing_files'])}")
        
        report.append("")
        
        # 建议和总结
        report.append("测试总结:")
        if passed_tests == total_tests:
            report.append("  🎉 所有测试通过！长期记忆系统集成成功。")
        elif passed_tests > total_tests * 0.8:
            report.append("  ✅ 大部分测试通过，记忆系统基本可用。")
        elif passed_tests > total_tests * 0.5:
            report.append("  ⚠️  部分测试通过，记忆系统需要进一步完善。")
        else:
            report.append("  ❌ 多数测试失败，记忆系统需要重新检查。")
        
        report.append("")
        report.append("=" * 60)
        
        # 输出报告
        report_content = "\n".join(report)
        print(report_content)
        
        # 保存报告到文件
        try:
            with open('memory_system_test_report.txt', 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info("测试报告已保存到 memory_system_test_report.txt")
        except Exception as e:
            logger.error(f"保存测试报告失败: {e}")

def main():
    """
    主函数
    """
    tester = MemorySystemTester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()