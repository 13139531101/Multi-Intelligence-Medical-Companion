from mcp.server.fastmcp import FastMCP
import json
from datetime import datetime, timedelta, time
from typing import Dict, List, Any, Optional
import os
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

# 创建 FastMCP 应用
mcp = FastMCP("ReminderTool")

# PostgreSQL 连接字符串
PG_DSN = (
    os.environ.get("PG_DSN")
    or os.environ.get("DATABASE_URL")
    # 默认回退到容器网络中的 postgres 服务与项目数据库
    or "postgresql://pha:pha_pass@postgres:5432/personal_health_assistant"
)

def get_pg_conn():
    return psycopg.connect(PG_DSN, row_factory=dict_row)

def init_database():
    """初始化PostgreSQL数据库（防御性创建表）"""
    with get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS medication_reminders (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    medication_name TEXT NOT NULL,
                    dosage TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE,
                    reminder_times JSONB NOT NULL,
                    notes TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reminder_logs (
                    id SERIAL PRIMARY KEY,
                    reminder_id INTEGER NOT NULL REFERENCES medication_reminders(id) ON DELETE CASCADE,
                    scheduled_time TIMESTAMPTZ NOT NULL,
                    actual_time TIMESTAMPTZ,
                    status TEXT NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS appointment_reminders (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    doctor_name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    appointment_date DATE NOT NULL,
                    appointment_time TIME NOT NULL,
                    hospital TEXT NOT NULL,
                    notes TEXT,
                    reminder_advance_days INTEGER DEFAULT 1,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()

# 初始化数据库
init_database()

@mcp.tool()
def add_medication_reminder(user_id: str, medication_name: str, dosage: str, frequency: str, 
                          start_date: str, reminder_times: List[str], end_date: Optional[str] = None, 
                          notes: Optional[str] = None) -> Dict[str, Any]:
    """
    添加用药提醒
    
    Args:
        user_id: 用户ID
        medication_name: 药物名称
        dosage: 剂量
        frequency: 频率（如：每日3次、每8小时一次）
        start_date: 开始日期（YYYY-MM-DD格式）
        reminder_times: 提醒时间列表（如：["08:00", "14:00", "20:00"]）
        end_date: 结束日期（可选）
        notes: 备注（可选）
    
    Returns:
        添加结果
    """
    try:
        now = datetime.now()
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO medication_reminders
                    (user_id, medication_name, dosage, frequency, start_date, end_date,
                     reminder_times, notes, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        medication_name,
                        dosage,
                        frequency,
                        datetime.strptime(start_date, "%Y-%m-%d").date(),
                        datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None,
                        Json(reminder_times),
                        notes,
                        now,
                        now,
                    ),
                )
                reminder_id = cur.fetchone()["id"]
                conn.commit()
        
        return {
            "status": "success",
            "reminder_id": reminder_id,
            "message": f"成功添加{medication_name}的用药提醒",
            "details": {
                "medication": medication_name,
                "dosage": dosage,
                "frequency": frequency,
                "reminder_times": reminder_times,
                "start_date": start_date,
                "end_date": end_date
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"添加用药提醒失败：{str(e)}"
        }

@mcp.tool()
def get_medication_reminders(user_id: str, active_only: bool = True) -> Dict[str, Any]:
    """
    获取用户的用药提醒列表
    
    Args:
        user_id: 用户ID
        active_only: 是否只返回活跃的提醒
    
    Returns:
        用药提醒列表
    """
    try:
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                if active_only:
                    cur.execute(
                        """
                        SELECT id, user_id, medication_name, dosage, frequency, start_date, end_date,
                               reminder_times, notes, is_active, created_at
                        FROM medication_reminders
                        WHERE user_id = %s AND is_active = TRUE
                        ORDER BY created_at DESC
                        """,
                        (user_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, user_id, medication_name, dosage, frequency, start_date, end_date,
                               reminder_times, notes, is_active, created_at
                        FROM medication_reminders
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        """,
                        (user_id,),
                    )
                reminders = cur.fetchall()

        reminder_list = []
        for r in reminders:
            reminder_list.append({
                "id": r["id"],
                "medication_name": r["medication_name"],
                "dosage": r["dosage"],
                "frequency": r["frequency"],
                "start_date": r["start_date"].isoformat() if r["start_date"] else None,
                "end_date": r["end_date"].isoformat() if r["end_date"] else None,
                "reminder_times": r["reminder_times"] or [],
                "notes": r["notes"],
                "is_active": bool(r["is_active"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
        
        return {
            "status": "success",
            "reminders": reminder_list,
            "count": len(reminder_list)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"获取用药提醒失败：{str(e)}"
        }

@mcp.tool()
def get_today_reminders(user_id: str) -> Dict[str, Any]:
    """
    获取今日的用药提醒
    
    Args:
        user_id: 用户ID
    
    Returns:
        今日用药提醒列表
    """
    try:
        today = datetime.now().date()
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, medication_name, dosage, reminder_times, notes
                    FROM medication_reminders
                    WHERE user_id = %s AND is_active = TRUE
                      AND start_date <= %s
                      AND (end_date IS NULL OR end_date >= %s)
                    """,
                    (user_id, today, today),
                )
                reminders = cur.fetchall()

        today_reminders = []
        for r in reminders:
            reminder_times = r["reminder_times"] or []
            for t in reminder_times:
                today_reminders.append({
                    "id": r["id"],
                    "medication_name": r["medication_name"],
                    "dosage": r["dosage"],
                    "time": t,
                    "notes": r["notes"],
                })
        
        # 按时间排序
        today_reminders.sort(key=lambda x: x["time"])
        
        return {
            "status": "success",
            "date": today,
            "reminders": today_reminders,
            "count": len(today_reminders)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"获取今日提醒失败：{str(e)}"
        }

@mcp.tool()
def log_medication_taken(reminder_id: int, actual_time: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """
    记录用药情况
    
    Args:
        reminder_id: 提醒ID
        actual_time: 实际用药时间（可选，默认为当前时间）
        notes: 备注（可选）
    
    Returns:
        记录结果
    """
    try:
        now = datetime.now()
        if actual_time is None:
            actual_dt = now
        else:
            try:
                # HH:MM provided
                hh, mm = actual_time.split(":")
                actual_dt = datetime.combine(now.date(), time(int(hh), int(mm)))
            except Exception:
                actual_dt = now

        scheduled_dt = datetime.combine(now.date(), now.time().replace(second=0, microsecond=0))

        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reminder_logs
                    (reminder_id, scheduled_time, actual_time, status, notes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (reminder_id, scheduled_dt, actual_dt, "taken", notes, now),
                )
                conn.commit()
        
        return {
            "status": "success",
            "message": "用药记录已保存",
            "actual_time": actual_time
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"记录用药失败：{str(e)}"
        }

@mcp.tool()
def add_appointment_reminder(user_id: str, doctor_name: str, department: str, 
                           appointment_date: str, appointment_time: str, hospital: str,
                           reminder_advance_days: int = 1, notes: Optional[str] = None) -> Dict[str, Any]:
    """
    添加复诊提醒
    
    Args:
        user_id: 用户ID
        doctor_name: 医生姓名
        department: 科室
        appointment_date: 预约日期（YYYY-MM-DD格式）
        appointment_time: 预约时间（HH:MM格式）
        hospital: 医院名称
        reminder_advance_days: 提前提醒天数（默认1天）
        notes: 备注（可选）
    
    Returns:
        添加结果
    """
    try:
        now = datetime.now()
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO appointment_reminders
                    (user_id, doctor_name, department, appointment_date, appointment_time,
                     hospital, reminder_advance_days, notes, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        doctor_name,
                        department,
                        datetime.strptime(appointment_date, "%Y-%m-%d").date(),
                        datetime.strptime(appointment_time, "%H:%M").time(),
                        hospital,
                        reminder_advance_days,
                        notes,
                        now,
                        now,
                    ),
                )
                appointment_id = cur.fetchone()["id"]
                conn.commit()
        
        return {
            "status": "success",
            "appointment_id": appointment_id,
            "message": f"成功添加{doctor_name}医生的复诊提醒",
            "details": {
                "doctor": doctor_name,
                "department": department,
                "date": appointment_date,
                "time": appointment_time,
                "hospital": hospital,
                "advance_days": reminder_advance_days
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"添加复诊提醒失败：{str(e)}"
        }

@mcp.tool()
def get_upcoming_appointments(user_id: str, days_ahead: int = 7) -> Dict[str, Any]:
    """
    获取即将到来的复诊预约
    
    Args:
        user_id: 用户ID
        days_ahead: 查看未来多少天的预约（默认7天）
    
    Returns:
        即将到来的预约列表
    """
    try:
        today = datetime.now().date()
        end_date = today + timedelta(days=days_ahead)
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, doctor_name, department, appointment_date, appointment_time,
                           hospital, notes, reminder_advance_days
                    FROM appointment_reminders
                    WHERE user_id = %s AND is_active = TRUE
                      AND appointment_date BETWEEN %s AND %s
                    ORDER BY appointment_date, appointment_time
                    """,
                    (user_id, today, end_date),
                )
                appointments = cur.fetchall()

        appointment_list = []
        for a in appointments:
            appointment_list.append({
                "id": a["id"],
                "doctor_name": a["doctor_name"],
                "department": a["department"],
                "appointment_date": a["appointment_date"].isoformat() if a["appointment_date"] else None,
                "appointment_time": a["appointment_time"].strftime("%H:%M") if a["appointment_time"] else None,
                "hospital": a["hospital"],
                "notes": a["notes"],
                "reminder_advance_days": a["reminder_advance_days"],
            })
        
        return {
            "status": "success",
            "appointments": appointment_list,
            "count": len(appointment_list),
            "period": f"{today.isoformat()} 到 {end_date.isoformat()}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"获取预约信息失败：{str(e)}"
        }

if __name__ == "__main__":
    mcp.run()