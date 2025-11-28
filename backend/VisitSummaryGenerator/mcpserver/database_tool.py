# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : database_tool.py
# @Author: Health Assistant Team
# @Desc  : 数据库查询工具 - 用于查询健康档案数据

import os
import json
from mcp.server.fastmcp import FastMCP
import sys
import logging
from datetime import datetime, timedelta

# 添加父目录到路径以导入database_config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import get_db_manager

logger = logging.getLogger(__name__)
mcp = FastMCP("DatabaseTool")

class HealthDataQuery:
    def __init__(self):
        self.db_manager = get_db_manager()

# 全局存储实例
storage = HealthDataQuery()

@mcp.tool()
def get_health_records_by_range(user_id: str, start_date: str = None, end_date: str = None, limit: int = 50) -> str:
    """
    根据时间范围获取健康档案记录
    :param user_id: 用户ID
    :param start_date: 开始日期 (YYYY-MM-DD)，默认为3个月前
    :param end_date: 结束日期 (YYYY-MM-DD)，默认为今天
    :param limit: 返回记录数量限制
    :return: 记录列表
    """
    try:
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            
        # 查询逻辑：优先使用 record_date，如果为空则使用 created_at
        # 注意：SQL中需要处理 NULL 值
        query = """
            SELECT id, record_type, title, summary, content, record_date, created_at, metadata
            FROM health_records
            WHERE user_id = %s 
            AND (
                (record_date >= %s AND record_date <= %s)
                OR 
                (record_date IS NULL AND created_at >= %s::timestamp AND created_at <= %s::timestamp + interval '1 day')
            )
            ORDER BY COALESCE(record_date, created_at::date) DESC
            LIMIT %s
        """
        
        # 参数顺序: user_id, start, end, start, end, limit
        records = storage.db_manager.execute_query(query, (user_id, start_date, end_date, start_date, end_date, limit))

        return json.dumps({
            'success': True,
            'start_date': start_date,
            'end_date': end_date,
            'records': records,
            'total': len(records)
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        logger.error(f"查询健康档案失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'查询失败: {str(e)}'
        }, ensure_ascii=False)

import uuid

@mcp.tool()
def save_generated_summary(user_id: str, content: str, time_range: str, record_ids: list = None) -> str:
    """
    保存生成的就诊摘要报告
    :param user_id: 用户ID
    :param content: 摘要内容
    :param time_range: 时间范围描述 (如 "2023-01 至 2023-03")
    :param record_ids: 关联的健康档案ID列表
    :return: 保存结果
    """
    try:
        summary_id = str(uuid.uuid4())
        visit_date = datetime.now().strftime('%Y-%m-%d')
        
        # 将关联的 record_ids 放入 metadata 或者 content 中 (这里简化处理，放入 content 前缀或 metadata 如果有的话)
        # visit_summaries 表没有 metadata 字段，但有 summary_content (LONGTEXT)
        # 我们将 record_ids 记录在 content 的末尾或作为隐藏信息
        
        final_content = content
        if record_ids:
            final_content += f"\n\n<!-- 关联记录ID: {','.join(map(str, record_ids))} -->"

        query = """
            INSERT INTO visit_summaries 
            (user_id, summary_id, visit_date, summary_content, generated_by, diagnosis)
            VALUES (%s, %s, %s, %s, 'ai_assistant', %s)
        """
        # 使用 diagnosis 字段临时存储 "时间范围" 说明，以便在列表中展示时能区分
        diagnosis_info = f"时间范围: {time_range}"
        
        storage.db_manager.execute_update(query, (user_id, summary_id, visit_date, final_content, diagnosis_info))
        
        return json.dumps({'success': True, 'summary_id': summary_id}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"保存摘要失败: {e}")
        return json.dumps({'success': False, 'message': str(e)}, ensure_ascii=False)

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
            SELECT record_type, title, summary, content, metadata, created_at, record_date
            FROM health_records
            WHERE id = %s AND user_id = %s
        """
        records = storage.db_manager.execute_query(query, (record_id, user_id))
        
        if not records:
             return json.dumps({'success': False, 'message': '记录不存在'}, ensure_ascii=False)
             
        return json.dumps({'success': True, 'data': records[0]}, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return json.dumps({'success': False, 'message': str(e)}, ensure_ascii=False)

if __name__ == '__main__':
    mcp.run()
