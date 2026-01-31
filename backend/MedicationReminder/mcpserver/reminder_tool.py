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
            # user_medications table (from HealthRecordsManager schema)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_medications (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    drug_name TEXT NOT NULL,
                    dosage TEXT,
                    frequency TEXT,
                    start_date DATE,
                    end_date DATE,
                    notes TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_medications_user_id ON user_medications(user_id)")

            # reminders table (Global reminders)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    reminder_type TEXT NOT NULL, -- 'medication', 'health', etc.
                    title TEXT NOT NULL,
                    description TEXT,
                    reminder_time TIMESTAMPTZ NOT NULL,
                    is_completed INTEGER DEFAULT 0,
                    completed_at TIMESTAMPTZ,
                    is_deleted INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user_time ON reminders(user_id, reminder_time DESC)")

            # medication_reminders table (Linking table)
            # Ensure it has reminder_id and medication_id
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
                    medication_id INTEGER REFERENCES user_medications(id),
                    reminder_id INTEGER REFERENCES reminders(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE medication_reminders ADD COLUMN IF NOT EXISTS medication_id INTEGER")
            cur.execute("ALTER TABLE medication_reminders ADD COLUMN IF NOT EXISTS reminder_id INTEGER")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_medication_reminders_user ON medication_reminders(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_medication_reminders_active ON medication_reminders(is_active)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_medication_reminders_created ON medication_reminders(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_medication_reminders_user_created_desc ON medication_reminders(user_id, created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_medication_reminders_user_medication ON medication_reminders(user_id, medication_id)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reminder_logs (
                    id SERIAL PRIMARY KEY,
                    reminder_id INTEGER NOT NULL REFERENCES medication_reminders(id) ON DELETE CASCADE,
                    scheduled_time TIMESTAMPTZ NOT NULL,
                    actual_time TIMESTAMPTZ,
                    status TEXT NOT NULL,
                    notes TEXT,
                    completion_time TIMESTAMPTZ,
                    user_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS user_id TEXT")
            cur.execute("ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS completion_time TIMESTAMPTZ")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder ON reminder_logs(reminder_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder_scheduled ON reminder_logs(reminder_id, scheduled_time)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_logs_user_scheduled ON reminder_logs(user_id, scheduled_time)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_logs_status ON reminder_logs(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_logs_created ON reminder_logs(created_at)")

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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_appointment_reminders_user ON appointment_reminders(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_appointment_reminders_date ON appointment_reminders(appointment_date)")
            conn.commit()

# 初始化数据库
init_database()

@mcp.tool()
def add_medication_reminder(user_id: str, medication_name: str, dosage: str, frequency: str,
                          start_date: str, reminder_times: List[str], end_date: Optional[str] = None,
                          notes: Optional[str] = None) -> Dict[str, Any]:
    """
    添加用药提醒 (同步创建 user_medications, reminders 和 medication_reminders)

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
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

        # 格式化频率文本
        frequency_text = frequency if frequency else f"每日{len(reminder_times)}次"

        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                # 1. 插入 user_medications
                cur.execute(
                    """
                    INSERT INTO user_medications
                    (user_id, drug_name, dosage, frequency, start_date, end_date, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, medication_name, dosage, frequency_text, start_dt, end_dt, notes)
                )
                medication_id = cur.fetchone()["id"]

                reminder_ids = []

                # 2. 为每个时间点创建提醒
                for time_str in reminder_times:
                    # 2a. 插入 reminders (主提醒表)
                    # 计算首次提醒时间
                    try:
                        t = datetime.strptime(time_str, "%H:%M").time()
                        first_reminder_dt = datetime.combine(start_dt, t)
                    except ValueError:
                         # 如果时间格式不对，跳过或默认
                         continue

                    cur.execute(
                        """
                        INSERT INTO reminders
                        (user_id, reminder_type, title, description, reminder_time)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (user_id, "medication", medication_name, notes or f"请按时服用{medication_name}", first_reminder_dt)
                    )
                    main_reminder_id = cur.fetchone()["id"]

                    # 2b. 插入 medication_reminders (详情表)
                    cur.execute(
                        """
                        INSERT INTO medication_reminders
                        (reminder_id, user_id, medication_id, medication_name, dosage, frequency,
                         reminder_times, start_date, end_date, notes, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            main_reminder_id,
                            user_id,
                            medication_id,
                            medication_name,
                            dosage,
                            frequency_text,
                            Json([time_str]), # Store single time as JSON array for compatibility
                            start_dt,
                            end_dt,
                            notes,
                            now,
                            now,
                        ),
                    )
                    mr_id = cur.fetchone()["id"]
                    reminder_ids.append(mr_id)

                conn.commit()

        return {
            "status": "success",
            "medication_id": medication_id,
            "reminder_ids": reminder_ids,
            "message": f"成功添加{medication_name}的用药提醒",
            "details": {
                "medication": medication_name,
                "dosage": dosage,
                "frequency": frequency_text,
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
def get_medication_reminders(user_id: str, date: Optional[str] = None, active_only: bool = True) -> Dict[str, Any]:
    """
    获取用户的用药提醒列表

    Args:
        user_id: 用户ID
        date: 指定日期 (YYYY-MM-DD)，为空则获取全部（如果active_only为True则默认为今天）
        active_only: 是否只返回活跃的提醒

    Returns:
        用药提醒列表
    """
    try:
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                target_date = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
                if active_only:
                    cur.execute(
                        """
                        SELECT id, user_id, medication_name, dosage, frequency, start_date, end_date,
                               reminder_times, notes, is_active, created_at, reminder_id, medication_id
                        FROM medication_reminders
                        WHERE user_id = %s
                          AND is_active = TRUE
                          AND (start_date <= %s)
                          AND (end_date IS NULL OR end_date >= %s)
                        ORDER BY created_at DESC
                        """,
                        (user_id, target_date, target_date),
                    )
                else:
                    # 如果不是只查活跃的，且指定了日期，也可以过滤，但通常 active_only=False 用于查历史
                    if date:
                         target_date = datetime.strptime(date, "%Y-%m-%d").date()
                         cur.execute(
                            """
                            SELECT id, user_id, medication_name, dosage, frequency, start_date, end_date,
                                   reminder_times, notes, is_active, created_at, reminder_id, medication_id
                            FROM medication_reminders
                            WHERE user_id = %s
                              AND (start_date <= %s)
                              AND (end_date IS NULL OR end_date >= %s)
                            ORDER BY created_at DESC
                            """,
                            (user_id, target_date, target_date),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, user_id, medication_name, dosage, frequency, start_date, end_date,
                                   reminder_times, notes, is_active, created_at, reminder_id, medication_id
                            FROM medication_reminders
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            """,
                            (user_id,),
                        )
                reminders = cur.fetchall()

                # 获取当天的服药记录
                start_dt = datetime.combine(target_date, time.min)
                end_dt = start_dt + timedelta(days=1)
                cur.execute(
                    """
                    SELECT reminder_id, scheduled_time, actual_time, status
                    FROM reminder_logs
                    WHERE user_id = %s
                      AND scheduled_time >= %s
                      AND scheduled_time < %s
                    """,
                    (user_id, start_dt, end_dt)
                )
                logs = cur.fetchall()

                # 构建 logs 字典，key 为 reminder_id (medication_reminders.id)
                logs_map = {}
                for log in logs:
                    rid = log["reminder_id"]
                    if rid not in logs_map:
                        logs_map[rid] = []

                    # 提取 HH:MM
                    try:
                        if log["scheduled_time"]:
                            time_str = log["scheduled_time"].strftime("%H:%M")
                            logs_map[rid].append({
                                "time": time_str,
                                "status": log["status"],
                                "actual_time": log["actual_time"].strftime("%H:%M") if log["actual_time"] else None
                            })
                    except Exception:
                        pass

        reminder_list = []
        for r in reminders:
            # 查找该提醒对应的日志
            r_logs = logs_map.get(r["id"], [])

            # 提取已服用的时间点
            taken_times = [l["time"] for l in r_logs if l["status"] == "completed" or l["status"] == "taken"]

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
                "reminder_id": r["reminder_id"],
                "medication_id": r["medication_id"],
                "taken_records": taken_times,  # 新增：已服用的时间列表
                "logs": r_logs                 # 新增：详细日志
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
                    SELECT id, medication_name, dosage, reminder_times, notes, reminder_id
                    FROM medication_reminders
                    WHERE user_id = %s AND is_active = TRUE
                      AND start_date <= %s
                      AND (end_date IS NULL OR end_date >= %s)
                    """,
                    (user_id, today, today),
                )
                reminders = cur.fetchall()

                # 获取当天的服药记录
                start_dt = datetime.combine(today, time.min)
                end_dt = start_dt + timedelta(days=1)
                cur.execute(
                    """
                    SELECT reminder_id, scheduled_time, status
                    FROM reminder_logs
                    WHERE user_id = %s
                      AND scheduled_time >= %s
                      AND scheduled_time < %s
                    """,
                    (user_id, start_dt, end_dt)
                )
                logs = cur.fetchall()

                # 构建 (reminder_id, time_str) -> status 映射
                taken_map = {}
                for log in logs:
                    try:
                        if log["scheduled_time"]:
                            t_str = log["scheduled_time"].strftime("%H:%M")
                            key = (log["reminder_id"], t_str)
                            taken_map[key] = log["status"]
                    except Exception:
                        pass

        today_reminders = []
        for r in reminders:
            reminder_times = r["reminder_times"] or []
            for t in reminder_times:
                # 检查是否已服用
                status = taken_map.get((r["id"], t))
                is_taken = (status == "completed" or status == "taken")

                today_reminders.append({
                    "id": r["id"],
                    "medication_name": r["medication_name"],
                    "dosage": r["dosage"],
                    "time": t,
                    "notes": r["notes"],
                    "reminder_id": r["reminder_id"],
                    "is_taken": is_taken,  # 新增：是否已服用
                    "status": status       # 新增：状态
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
        reminder_id: 提醒ID (medication_reminders表的主键ID)
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
