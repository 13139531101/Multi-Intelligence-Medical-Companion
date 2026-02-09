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

_backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

get_db_manager = None
try:
    from HealthRecordsManager.database_config import get_db_manager as _get_db_manager
    get_db_manager = _get_db_manager
except Exception:
    pass
if get_db_manager is None:
    try:
        from HealthAdvisor.database_config import get_db_manager as _get_db_manager
        get_db_manager = _get_db_manager
    except Exception:
        pass
if get_db_manager is None:
    raise ImportError("get_db_manager not found")

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

@mcp.tool()
def get_visit_summaries_by_range(
    user_id: str,
    start_date: str = None,
    end_date: str = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    try:
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        query = """
            SELECT
                id, title, visit_date, doctor, hospital, department,
                chief_complaint, symptoms, examination, diagnosis, treatment,
                prescription, follow_up, summary_content, notes,
                files, tests, is_deleted, created_at, updated_at
            FROM visit_summaries
            WHERE user_id = %s
              AND is_deleted = 0
              AND (
                (visit_date >= %s::date AND visit_date <= %s::date)
                OR
                (created_at >= %s::timestamp AND created_at <= %s::timestamp + interval '1 day')
              )
            ORDER BY COALESCE(visit_date, created_at::date) DESC, created_at DESC
            LIMIT %s OFFSET %s
        """
        items = storage.db_manager.execute_query(
            query,
            (user_id, start_date, end_date, start_date, end_date, limit, offset),
        )

        return json.dumps(
            {
                "success": True,
                "start_date": start_date,
                "end_date": end_date,
                "items": items,
                "count": len(items),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception as e:
        logger.error(f"查询就诊摘要失败: {e}")
        return json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_visit_summaries_count_by_range(
    user_id: str,
    start_date: str = None,
    end_date: str = None,
) -> str:
    try:
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        query = """
            SELECT COUNT(1) AS cnt
            FROM visit_summaries
            WHERE user_id = %s
              AND is_deleted = 0
              AND (
                (visit_date >= %s::date AND visit_date <= %s::date)
                OR
                (created_at >= %s::timestamp AND created_at <= %s::timestamp + interval '1 day')
              )
        """
        rows = storage.db_manager.execute_query(
            query,
            (user_id, start_date, end_date, start_date, end_date),
        )
        cnt = 0
        if rows and isinstance(rows, list):
            r0 = rows[0] if rows else {}
            if isinstance(r0, dict):
                try:
                    cnt = int(r0.get("cnt") or 0)
                except Exception:
                    cnt = 0

        return json.dumps(
            {"success": True, "start_date": start_date, "end_date": end_date, "count": cnt},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception as e:
        logger.error(f"统计就诊摘要失败: {e}")
        return json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_visit_summary_detail(user_id: str, summary_id: str) -> str:
    try:
        query = """
            SELECT
                id, user_id, title, visit_date, doctor, hospital, department,
                chief_complaint, symptoms, examination, diagnosis, treatment,
                prescription, follow_up, summary_content, notes,
                files, tests, is_deleted, created_at, updated_at
            FROM visit_summaries
            WHERE id = %s AND user_id = %s
        """
        rows = storage.db_manager.execute_query(query, (summary_id, user_id))
        if not rows:
            return json.dumps({"success": False, "message": "摘要不存在"}, ensure_ascii=False)
        return json.dumps(
            {"success": True, "data": rows[0]},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception as e:
        logger.error(f"获取就诊摘要详情失败: {e}")
        return json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)

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
        visit_date = datetime.now().strftime("%Y-%m-%d")
        
        final_content = content
        if record_ids:
            final_content += f"\n\n<!-- 关联记录ID: {','.join(map(str, record_ids))} -->"

        query = """
            INSERT INTO visit_summaries
            (id, user_id, title, visit_date, summary_content, notes, tests, files, is_deleted, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, 0, now(), now())
        """
        notes = f"时间范围: {time_range}"
        tests = []
        if record_ids:
            tests = [{"type": "source_record_ids", "data": {"record_ids": record_ids}}]
        storage.db_manager.execute_update(
            query,
            (
                summary_id,
                user_id,
                f"AI汇总摘要（{time_range}）",
                visit_date,
                final_content,
                notes,
                json.dumps(tests, ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
            ),
        )
        
        return json.dumps({"success": True, "summary_id": summary_id}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"保存摘要失败: {e}")
        return json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)

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
