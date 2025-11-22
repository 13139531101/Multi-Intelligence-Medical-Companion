# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : reminder_tool.py
# @Author: Health Assistant Team
# @Desc  : 提醒工具 - 用于管理用药提醒和健康提醒（MySQL版本）

import os
import json
import sys
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP
import logging

# 添加父目录到路径以导入database_config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import get_db_manager

logger = logging.getLogger(__name__)
mcp = FastMCP("健康提醒管理工具")

class ReminderManager:
    def __init__(self):
        self.db_manager = get_db_manager()

    def format_datetime(self, dt_str):
        """格式化日期时间字符串"""
        try:
            if isinstance(dt_str, str):
                # 尝试解析不同格式的日期时间
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M',
                    '%Y-%m-%d',
                    '%m/%d/%Y %H:%M',
                    '%m/%d/%Y'
                ]

                for fmt in formats:
                    try:
                        return datetime.strptime(dt_str, fmt)
                    except ValueError:
                        continue

                # 如果都不匹配，返回None
                return None
            elif isinstance(dt_str, datetime):
                return dt_str
            else:
                return None
        except Exception:
            return None

# 全局提醒管理器实例
reminder_manager = ReminderManager()

@mcp.tool()
def add_medication_reminder(user_id: str, medication_name: str, dosage: str,
                          frequency: str, reminder_times: str, start_date: str = "",
                          end_date: str = "", notes: str = "") -> str:
    """
    添加用药提醒
    :param user_id: 用户ID
    :param medication_name: 药物名称
    :param dosage: 剂量
    :param frequency: 频率文本（兼容调用方，不参与入参校验）
    :param reminder_times: 提醒时间（JSON格式，如：["08:00", "12:00", "18:00"]）
    :param start_date: 开始日期 (YYYY-MM-DD)
    :param end_date: 结束日期 (YYYY-MM-DD)
    :param notes: 备注
    :return: 添加结果
    """
    try:
        # 解析提醒时间
        try:
            times_list = json.loads(reminder_times) if isinstance(reminder_times, str) else reminder_times
        except json.JSONDecodeError:
            # 如果不是JSON格式，尝试按逗号分割
            times_list = [t.strip() for t in reminder_times.split(',')]

        # 验证时间格式
        valid_times = []
        for time_str in times_list:
            try:
                # 验证时间格式 HH:MM
                datetime.strptime(time_str, '%H:%M')
                valid_times.append(time_str)
            except ValueError:
                logger.warning(f"无效的时间格式: {time_str}")

        if not valid_times:
            return json.dumps({
                'success': False,
                'message': '没有有效的提醒时间'
            }, ensure_ascii=False)

        # 处理日期
        start_dt = reminder_manager.format_datetime(start_date) if start_date else datetime.now().date()
        end_dt = reminder_manager.format_datetime(end_date) if end_date else None
        # 统一 DATE 类型用于插入
        start_date_sql = start_dt.date() if isinstance(start_dt, datetime) else start_dt
        end_date_sql = (end_dt.date() if isinstance(end_dt, datetime) else end_dt) if end_dt else None

        # 插入用药记录
        medication_query = """
            INSERT INTO user_medications
            (user_id, drug_name, dosage, frequency, start_date, end_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        frequency_text = f"每日{len(valid_times)}次，时间：{', '.join(valid_times)}"
        medication_id = reminder_manager.db_manager.execute_insert(
            medication_query,
            (user_id, medication_name, dosage, frequency_text, start_date_sql, end_date_sql, notes)
        )

        # 为每个时间点创建提醒
        reminder_ids = []
        for time_str in valid_times:
            # 组合首次提醒时间到具体日期时间
            date_str = (start_dt.date().isoformat() if isinstance(start_dt, datetime) else str(start_dt))
            first_dt = f"{date_str} {str(time_str)}:00"
            # 1) 插入主提醒
            main_id = reminder_manager.db_manager.execute_insert(
                """
                INSERT INTO reminders
                (user_id, reminder_type, title, description, reminder_time)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, "medication", medication_name, notes, first_dt)
            )

            # 2) 插入详情，绑定外键 reminder_id，并存储单个时间点的 JSON
            reminder_id = reminder_manager.db_manager.execute_insert(
                """
                INSERT INTO medication_reminders
                (reminder_id, user_id, medication_id, medication_name, dosage, frequency, reminder_times,
                 start_date, end_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (main_id, user_id, medication_id, medication_name, dosage, frequency_text, json.dumps([time_str]),
                 start_date_sql, end_date_sql, notes)
            )
            reminder_ids.append(reminder_id)

        return json.dumps({
            'success': True,
            'message': '用药提醒添加成功',
            'medication_id': medication_id,
            'reminder_ids': reminder_ids,
            'reminder_count': len(reminder_ids)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"添加用药提醒失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'添加用药提醒失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def get_medication_reminders(user_id: str, date: str = "", active_only: bool = True) -> str:
    """
    获取用药提醒列表
    :param user_id: 用户ID
    :param date: 指定日期 (YYYY-MM-DD)，为空则获取今天的
    :param active_only: 是否只获取活跃的提醒
    :return: 提醒列表
    """
    try:
        # 处理日期
        if date:
            target_date = reminder_manager.format_datetime(date)
            if not target_date:
                target_date = datetime.now().date()
            else:
                target_date = target_date.date()
        else:
            target_date = datetime.now().date()

        # 构建查询
        if active_only:
            query = """
                SELECT mr.id, mr.medication_name, mr.dosage, mr.reminder_times,
                       mr.start_date, mr.end_date, mr.notes, mr.created_at,
                       um.is_active as medication_active
                FROM medication_reminders mr
                LEFT JOIN user_medications um ON mr.medication_id = um.id
                WHERE mr.user_id = %s
                  AND CAST(mr.is_active AS TEXT) IN ('1','t','true')
                  AND (mr.start_date <= %s)
                  AND (mr.end_date IS NULL OR mr.end_date >= %s)
                ORDER BY mr.created_at DESC
            """
            params = (user_id, target_date, target_date)
        else:
            query = """
                SELECT mr.id, mr.medication_name, mr.dosage, mr.reminder_times,
                       mr.start_date, mr.end_date, mr.notes, mr.created_at,
                       um.is_active as medication_active
                FROM medication_reminders mr
                LEFT JOIN user_medications um ON mr.medication_id = um.id
                WHERE mr.user_id = %s
                ORDER BY mr.created_at DESC
            """
            params = (user_id,)

        reminders = reminder_manager.db_manager.execute_query(query, params)

        # 展开 JSON 的提醒时间到多个条目，每条包含一个 HH:MM 的 reminder_time
        expanded = []
        for row in reminders or []:
            times_raw = row.get("reminder_times")
            times_list = []
            try:
                if isinstance(times_raw, str):
                    times_list = json.loads(times_raw)
                elif isinstance(times_raw, (list, tuple)):
                    times_list = list(times_raw)
            except Exception:
                times_list = []
            for t in times_list:
                item = dict(row)
                item["reminder_time"] = str(t)
                expanded.append(item)

        # 按时间排序（HH:MM）
        try:
            expanded.sort(key=lambda x: x.get("reminder_time", ""))
        except Exception:
            pass

        return json.dumps({
            'success': True,
            'date': str(target_date),
            'reminders': expanded,
            'total': len(expanded)
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        logger.error(f"获取用药提醒失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'获取用药提醒失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def mark_reminder_taken(user_id: str, reminder_id: int, taken_time: str = "") -> str:
    """
    标记提醒已服药
    :param user_id: 用户ID
    :param reminder_id: 提醒ID
    :param taken_time: 服药时间 (YYYY-MM-DD HH:MM:SS)，为空则使用当前时间
    :return: 标记结果
    """
    try:
        # 处理服药时间
        if taken_time:
            taken_dt = reminder_manager.format_datetime(taken_time)
            if not taken_dt:
                taken_dt = datetime.now()
        else:
            taken_dt = datetime.now()

        # 检查提醒是否存在
        check_query = """
            SELECT id, reminder_id, medication_id, medication_name, reminder_times
            FROM medication_reminders
            WHERE id = %s AND user_id = %s
        """
        reminders = reminder_manager.db_manager.execute_query(check_query, (reminder_id, user_id))

        if not reminders:
            return json.dumps({
                'success': False,
                'message': '提醒不存在或无权限访问'
            }, ensure_ascii=False)

        reminder = reminders[0]

        # 解析该条提醒的计划时间（当天的 HH:MM）
        time_str = "12:00"
        try:
            times_raw = reminder.get("reminder_times")
            times_list = json.loads(times_raw) if isinstance(times_raw, str) else (list(times_raw) if isinstance(times_raw, (list, tuple)) else [])
            if times_list:
                s = str(times_list[0])
                # 简单校验 HH:MM
                datetime.strptime(s, "%H:%M")
                time_str = s
        except Exception:
            pass

        # 记录服药日志（状态使用枚举中的 completed，并写入完成时间）
        log_query = """
            INSERT INTO reminder_logs
            (reminder_id, user_id, scheduled_time, actual_time, status, completion_time, notes)
            VALUES (%s, %s, %s, %s, 'completed', %s, '用户手动标记已服药')
        """

        today = datetime.now().date()
        scheduled_time = datetime.combine(today, datetime.strptime(time_str, "%H:%M").time())

        log_id = reminder_manager.db_manager.execute_insert(
            log_query,
            (reminder['reminder_id'], user_id, scheduled_time, taken_dt, taken_dt)
        )

        return json.dumps({
            'success': True,
            'message': '服药记录已保存',
            'log_id': log_id,
            'taken_time': str(taken_dt)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"标记服药失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'标记服药失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def add_health_reminder(user_id: str, title: str, description: str = "",
                       reminder_time: str = "", reminder_type: str = "health") -> str:
    """
    添加健康提醒
    :param user_id: 用户ID
    :param title: 提醒标题
    :param description: 提醒描述
    :param reminder_time: 提醒时间 (YYYY-MM-DD HH:MM:SS)
    :param reminder_type: 提醒类型 (health/checkup/exercise/diet/other)
    :return: 添加结果
    """
    try:
        # 处理提醒时间
        if reminder_time:
            reminder_dt = reminder_manager.format_datetime(reminder_time)
            if not reminder_dt:
                return json.dumps({
                    'success': False,
                    'message': '无效的提醒时间格式'
                }, ensure_ascii=False)
        else:
            # 默认设置为1小时后
            reminder_dt = datetime.now() + timedelta(hours=1)

        # 插入提醒记录
        insert_query = """
            INSERT INTO reminders
            (user_id, reminder_type, title, description, reminder_time)
            VALUES (%s, %s, %s, %s, %s)
        """

        reminder_id = reminder_manager.db_manager.execute_insert(
            insert_query,
            (user_id, reminder_type, title, description, reminder_dt)
        )

        return json.dumps({
            'success': True,
            'message': '健康提醒添加成功',
            'reminder_id': reminder_id,
            'reminder_time': str(reminder_dt)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"添加健康提醒失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'添加健康提醒失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def get_health_reminders(user_id: str, reminder_type: str = "",
                        start_date: str = "", end_date: str = "") -> str:
    """
    获取健康提醒列表
    :param user_id: 用户ID
    :param reminder_type: 提醒类型过滤
    :param start_date: 开始日期 (YYYY-MM-DD)
    :param end_date: 结束日期 (YYYY-MM-DD)
    :return: 提醒列表
    """
    try:
        # 构建查询条件
        conditions = ["user_id = %s", "is_deleted = 0"]
        params = [user_id]

        if reminder_type:
            conditions.append("reminder_type = %s")
            params.append(reminder_type)

        if start_date:
            start_dt = reminder_manager.format_datetime(start_date)
            if start_dt:
                conditions.append("reminder_time >= %s")
                params.append(start_dt)

        if end_date:
            end_dt = reminder_manager.format_datetime(end_date)
            if end_dt:
                conditions.append("reminder_time <= %s")
                params.append(end_dt)

        query = f"""
            SELECT id, reminder_type, title, description, reminder_time,
                   is_completed, created_at
            FROM reminders
            WHERE {' AND '.join(conditions)}
            ORDER BY reminder_time ASC
        """

        reminders = reminder_manager.db_manager.execute_query(query, params)

        return json.dumps({
            'success': True,
            'reminders': reminders,
            'total': len(reminders)
        }, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        logger.error(f"获取健康提醒失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'获取健康提醒失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def complete_reminder(user_id: str, reminder_id: int) -> str:
    """
    完成提醒
    :param user_id: 用户ID
    :param reminder_id: 提醒ID
    :return: 完成结果
    """
    try:
        # 检查提醒是否存在
        check_query = "SELECT id FROM reminders WHERE id = %s AND user_id = %s AND is_deleted = 0"
        existing_reminders = reminder_manager.db_manager.execute_query(check_query, (reminder_id, user_id))

        if not existing_reminders:
            return json.dumps({
                'success': False,
                'message': '提醒不存在或无权限访问'
            }, ensure_ascii=False)

        # 更新提醒状态
        update_query = """
            UPDATE reminders
            SET is_completed = 1, completed_at = NOW(), updated_at = NOW()
            WHERE id = %s AND user_id = %s
        """

        affected_rows = reminder_manager.db_manager.execute_update(update_query, (reminder_id, user_id))

        if affected_rows > 0:
            return json.dumps({
                'success': True,
                'message': '提醒已完成'
            }, ensure_ascii=False)
        else:
            return json.dumps({
                'success': False,
                'message': '更新提醒状态失败'
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"完成提醒失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'完成提醒失败: {str(e)}'
        }, ensure_ascii=False)

@mcp.tool()
def delete_reminder(user_id: str, reminder_id: int, reminder_type: str = "health") -> str:
    """
    删除提醒（软删除）
    :param user_id: 用户ID
    :param reminder_id: 提醒ID
    :param reminder_type: 提醒类型 (health/medication)
    :return: 删除结果
    """
    try:
        if reminder_type == "medication":
            table_name = "medication_reminders"
        else:
            table_name = "reminders"

        # 检查提醒是否存在
        check_query = f"SELECT id FROM {table_name} WHERE id = %s AND user_id = %s AND is_deleted = 0"
        existing_reminders = reminder_manager.db_manager.execute_query(check_query, (reminder_id, user_id))

        if not existing_reminders:
            return json.dumps({
                'success': False,
                'message': '提醒不存在或无权限删除'
            }, ensure_ascii=False)

        # 软删除提醒
        update_query = f"""
            UPDATE {table_name}
            SET is_deleted = 1, updated_at = NOW()
            WHERE id = %s AND user_id = %s
        """

        affected_rows = reminder_manager.db_manager.execute_update(update_query, (reminder_id, user_id))

        if affected_rows > 0:
            return json.dumps({
                'success': True,
                'message': '提醒删除成功'
            }, ensure_ascii=False)
        else:
            return json.dumps({
                'success': False,
                'message': '删除操作失败'
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"删除提醒失败: {e}")
        return json.dumps({
            'success': False,
            'message': f'删除提醒失败: {str(e)}'
        }, ensure_ascii=False)

if __name__ == '__main__':
    # 作为 MCP 服务器运行：默认执行 mcp.run()
    # 如需运行内置测试，请在环境变量中设置 RUN_TESTS=1
    run_tests = os.getenv('RUN_TESTS', '0') == '1'
    if not run_tests:
        logging.basicConfig(level=logging.INFO)
        mcp.run()
    else:
        # 测试提醒工具
        import logging
        logging.basicConfig(level=logging.INFO)

        # 测试数据库连接
        if reminder_manager.db_manager.test_connection():
            print("数据库连接成功！")

            # 测试添加用药提醒
            test_user_id = "test_user_001"
            result = add_medication_reminder(
                test_user_id,
                "阿司匹林",
                "100mg",
                '["08:00", "20:00"]',
                "2025-01-20",
                "2025-02-20",
                "饭后服用"
            )
            print("添加用药提醒结果:", result)

            # 测试获取提醒
            reminders = get_medication_reminders(test_user_id)
            print("\n获取用药提醒:", reminders)

            # 测试添加健康提醒
            health_result = add_health_reminder(
                test_user_id,
                "体检提醒",
                "年度体检时间到了",
                "2025-01-25 09:00:00",
                "checkup"
            )
            print("\n添加健康提醒结果:", health_result)

        else:
            print("数据库连接失败！")