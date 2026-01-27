# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : storage_tool.py
# @Author: Health Assistant Team
# @Desc  : 安全存储工具 - 用于加密存储和管理健康数据（MySQL版本）

import os
import json
import hashlib
from uuid import uuid4
from datetime import datetime
from cryptography.fernet import Fernet
from mcp.server.fastmcp import FastMCP
import sys
import logging

# 添加父目录到路径以导入database_config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import get_db_manager

logger = logging.getLogger(__name__)
mcp = FastMCP("健康数据安全存储工具")

class HealthDataStorage:
    def __init__(self):
        self.db_manager = get_db_manager()
        self.encryption_key = self.get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)

    def get_or_create_encryption_key(self):
        """获取或创建加密密钥"""
        key_file = os.path.join(os.path.dirname(__file__), "..", "encryption.key")
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            return key

    def encrypt_data(self, data):
        """加密数据"""
        if isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False)
        elif not isinstance(data, str):
            data = str(data)

        return self.cipher.encrypt(data.encode('utf-8'))

    def decrypt_data(self, encrypted_data):
        """解密数据"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data)
            return decrypted.decode('utf-8')
        except Exception as e:
            return f"解密失败: {str(e)}"

    def calculate_file_hash(self, content):
        """计算文件哈希值"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

# 全局存储实例
storage = HealthDataStorage()

@mcp.tool()
def save_health_record(user_id: str, record_type: str, title: str, content: str, extracted_data: str = "") -> str:
    """
    保存健康档案记录
    :param user_id: 用户ID
    :param record_type: 记录类型 (prescription/test_report/medical_record/hospital_record/vaccination/surgery/other)
    :param title: 记录标题
    :param content: 原始内容
    :param extracted_data: 提取的结构化数据
    :return: 保存结果
    """
    try:
        rt_raw = str(record_type or "").strip().lower()
        rt_map = {
            "test_report": "lab_result",
            "inspection_report": "lab_result",
            "lab_report": "lab_result",
            "lab_result": "lab_result",
            "medical_report": "medical_record",
            "medical_record": "medical_record",
            "hospital_record": "hospital_record",
            "vaccination_record": "vaccination",
            "vaccination": "vaccination",
            "prescription": "prescription",
            "surgery": "surgery",
            "other": "other",
        }
        record_type = rt_map.get(rt_raw, rt_raw or "other")
        # 计算文件哈希（存入 metadata）
        file_hash = storage.calculate_file_hash(content)

        # 改进去重：仅按 user_id + 内容/文件哈希 去重，避免因标题/类型差异产生重复
        # 优先匹配完全相同的内容，其次匹配 metadata 中的 file_hash
        existing_query = """
            SELECT id FROM health_records
            WHERE user_id = %s AND (content = %s OR metadata ->> 'file_hash' = %s)
        """
        existing_records = storage.db_manager.execute_query(
            existing_query, (user_id, content, file_hash)
        )

        if existing_records:
            return json.dumps({
                'success': False,
                'message': '相同内容的记录已存在',
                'record_id': str(existing_records[0]['id'])
            }, ensure_ascii=False)

        # 插入新记录（适配现有 schema）
        # importance 默认为 medium；tags/metadata 写为 JSON
        insert_query = """
            INSERT INTO health_records
            (id, user_id, record_type, title, summary, content, importance, tags, metadata, record_date, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, CURRENT_DATE, NOW(), NOW())
            RETURNING id
        """

        tags = json.dumps(["健康档案", record_type, "storage_tool"] , ensure_ascii=False)
        metadata = json.dumps({"extracted_data": extracted_data, "file_hash": file_hash, "source": "StorageTool"}, ensure_ascii=False, default=str)
        summary = extracted_data or ""

        record_id = storage.db_manager.execute_insert(
            insert_query,
            (str(uuid4()), user_id, record_type, title, summary, content, "medium", tags, metadata)
        )

        return json.dumps({
            'success': True,
            'message': '健康档案保存成功',
            'record_id': str(record_id)
        }, ensure_ascii=False, default=str)

    except Exception as e:
        logger.error(f"保存健康档案失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'保存失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def get_health_records(user_id: str, record_type: str = "", limit: int = 10) -> str:
    """
    获取健康档案记录
    :param user_id: 用户ID
    :param record_type: 记录类型过滤
    :param limit: 返回记录数量限制
    :return: 记录列表
    """
    try:
        # 构建查询语句
        if record_type:
            query = """
                SELECT id, record_type, title, created_at, updated_at
                FROM health_records
                WHERE user_id = %s AND record_type = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            params = (user_id, record_type, limit)
        else:
            query = """
                SELECT id, record_type, title, created_at, updated_at
                FROM health_records
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            params = (user_id, limit)

        records = storage.db_manager.execute_query(query, params)

        return json.dumps({
            'success': True,
            'records': records,
            'total': len(records)
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        logger.error(f"获取健康档案失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'获取记录失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def get_health_record_detail(user_id: str, record_id: str) -> str:
    """
    获取健康档案详细信息
    :param user_id: 用户ID
    :param record_id: 记录ID
    :return: 详细记录信息
    """
    try:
        query = """
            SELECT record_type, title, summary, content, metadata, created_at
            FROM health_records
            WHERE id = %s AND user_id = %s
        """

        records = storage.db_manager.execute_query(query, (record_id, user_id))

        if not records:
            return json.dumps({
                'success': False,
                'message': '记录不存在或无权限访问'
            }, ensure_ascii=False)

        record = records[0]
        # 提取 metadata.extracted_data
        try:
            meta = record.get('metadata') or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            extracted_data = meta.get('extracted_data') or record.get('summary') or ""
        except Exception:
            extracted_data = record.get('summary') or ""

        return json.dumps({
            'success': True,
            'record': {
                'id': record_id,
                'record_type': record['record_type'],
                'title': record['title'],
                'content': record['content'],
                'extracted_data': extracted_data,
                'created_at': str(record['created_at'])
            }
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"获取健康档案详情失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'获取记录详情失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def save_medication(user_id: str, drug_name: str, dosage: str = "", frequency: str = "",
                  start_date: str = "", end_date: str = "", notes: str = "") -> str:
    """
    保存用药记录
    :param user_id: 用户ID
    :param drug_name: 药物名称
    :param dosage: 剂量
    :param frequency: 频次
    :param start_date: 开始日期
    :param end_date: 结束日期
    :param notes: 备注
    :return: 保存结果
    """
    try:
        insert_query = """
            INSERT INTO user_medications
            (user_id, drug_name, dosage, frequency, start_date, end_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        medication_id = storage.db_manager.execute_insert(
            insert_query,
            (user_id, drug_name, dosage, frequency, start_date or None, end_date or None, notes)
        )

        return json.dumps({
            'success': True,
            'message': '用药记录保存成功',
            'medication_id': medication_id
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"保存用药记录失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'保存用药记录失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def get_medications(user_id: str, is_active: bool = True) -> str:
    """
    获取用药记录
    :param user_id: 用户ID
    :param is_active: 是否只获取活跃的用药记录
    :return: 用药记录列表
    """
    try:
        if is_active:
            query = """
                SELECT id, drug_name, dosage, frequency, start_date, end_date, notes, created_at
                FROM user_medications
                WHERE user_id = %s AND CAST(is_active AS TEXT) IN ('1','t','true')
                ORDER BY created_at DESC
            """
            params = (user_id,)
        else:
            query = """
                SELECT id, drug_name, dosage, frequency, start_date, end_date, notes, created_at
                FROM user_medications
                WHERE user_id = %s
                ORDER BY created_at DESC
            """
            params = (user_id,)

        medications = storage.db_manager.execute_query(query, params)

        return json.dumps({
            'success': True,
            'medications': medications,
            'total': len(medications)
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        logger.error(f"获取用药记录失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'获取用药记录失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def delete_health_record(user_id: str, record_id: str) -> str:
    """
    删除健康档案记录（软删除）
    :param user_id: 用户ID
    :param record_id: 记录ID
    :return: 删除结果
    """
    try:
        # 检查记录是否存在且属于该用户
        check_query = "SELECT id FROM health_records WHERE id = %s AND user_id = %s"
        existing_records = storage.db_manager.execute_query(check_query, (record_id, user_id))

        if not existing_records:
            return json.dumps({
                'success': False,
                'message': '记录不存在或无权限删除'
            }, ensure_ascii=False)

        # 物理删除记录（当前表无 is_deleted 字段）
        delete_query = "DELETE FROM health_records WHERE id = %s AND user_id = %s"
        affected_rows = storage.db_manager.execute_update(delete_query, (record_id, user_id))

        if affected_rows > 0:
            return json.dumps({
                'success': True,
                'message': '记录删除成功'
            }, ensure_ascii=False)
        else:
            return json.dumps({
                'success': False,
                'message': '删除操作失败'
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"删除健康档案失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'删除记录失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def create_user_profile(user_id: str, username: str, email: str = "", real_name: str = "",
                       gender: str = "", birth_date: str = "") -> str:
    """
    创建用户档案
    :param user_id: 用户ID
    :param username: 用户名
    :param email: 邮箱
    :param real_name: 真实姓名
    :param gender: 性别 (male/female/other)
    :param birth_date: 出生日期 (YYYY-MM-DD)
    :return: 创建结果
    """
    try:
        # 检查用户是否已存在
        check_query = "SELECT user_id FROM users WHERE user_id = %s"
        existing_users = storage.db_manager.execute_query(check_query, (user_id,))

        if existing_users:
            return json.dumps({
                'success': False,
                'message': '用户已存在'
            }, ensure_ascii=False)

        # 使用存储过程创建用户档案
        with storage.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # 插入用户基本信息
            user_query = "INSERT INTO users (user_id, username, email) VALUES (%s, %s, %s)"
            cursor.execute(user_query, (user_id, username, email or None))

            # 插入用户档案信息
            if real_name or gender or birth_date:
                profile_query = """
                    INSERT INTO user_profiles (user_id, real_name, gender, birth_date)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(profile_query, (
                    user_id,
                    real_name or None,
                    gender if gender in ['male', 'female', 'other'] else None,
                    birth_date or None
                ))

            conn.commit()
            cursor.close()

        return json.dumps({
            'success': True,
            'message': '用户档案创建成功',
            'user_id': user_id
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"创建用户档案失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'创建用户档案失败: {str(e)}'
        }, ensure_ascii=False)

if __name__ == '__main__':
    # 作为 MCP 服务器运行：默认执行 mcp.run()
    # 如需运行内置测试，请在环境变量中设置 RUN_TESTS=1
    run_tests = os.getenv('RUN_TESTS', '0') == '1'
    if not run_tests:
        logging.basicConfig(level=logging.INFO)
        mcp.run()
    else:
        # 测试存储工具
        import logging
        logging.basicConfig(level=logging.INFO)

        # 测试数据库连接
        if storage.db_manager.test_connection():
            print("数据库连接成功！")

            # 测试保存健康档案
            test_user_id = "test_user_001"
            test_content = "患者姓名：张三\n诊断：高血压"
            test_extracted = '{"patient_name": "张三", "diagnosis": "高血压"}'

            result = save_health_record(test_user_id, "medical_record", "测试病历", test_content, test_extracted)
            print("保存结果:", result)

            # 测试获取记录
            records = get_health_records(test_user_id)
            print("\n获取记录:", records)
        else:
            print("数据库连接失败！")
