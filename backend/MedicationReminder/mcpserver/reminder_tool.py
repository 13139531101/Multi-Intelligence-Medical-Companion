from mcp.server.fastmcp import FastMCP
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import os

# 创建 FastMCP 应用
mcp = FastMCP("ReminderTool")

# 数据库文件路径
DB_PATH = "medication_reminders.db"

def init_database():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 创建用药提醒表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS medication_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            medication_name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            frequency TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            reminder_times TEXT NOT NULL,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    # 创建提醒记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminder_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL,
            scheduled_time TEXT NOT NULL,
            actual_time TEXT,
            status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reminder_id) REFERENCES medication_reminders (id)
        )
    ''')
    
    # 创建复诊提醒表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointment_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            doctor_name TEXT NOT NULL,
            department TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            hospital TEXT NOT NULL,
            notes TEXT,
            reminder_advance_days INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        reminder_times_json = json.dumps(reminder_times)
        
        cursor.execute('''
            INSERT INTO medication_reminders 
            (user_id, medication_name, dosage, frequency, start_date, end_date, 
             reminder_times, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, medication_name, dosage, frequency, start_date, end_date,
              reminder_times_json, notes, current_time, current_time))
        
        reminder_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('''
                SELECT * FROM medication_reminders 
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT * FROM medication_reminders 
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
        
        reminders = cursor.fetchall()
        conn.close()
        
        reminder_list = []
        for reminder in reminders:
            reminder_dict = {
                "id": reminder[0],
                "medication_name": reminder[2],
                "dosage": reminder[3],
                "frequency": reminder[4],
                "start_date": reminder[5],
                "end_date": reminder[6],
                "reminder_times": json.loads(reminder[7]),
                "notes": reminder[8],
                "is_active": bool(reminder[9]),
                "created_at": reminder[10]
            }
            reminder_list.append(reminder_dict)
        
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
        today = datetime.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM medication_reminders 
            WHERE user_id = ? AND is_active = 1 
            AND start_date <= ? 
            AND (end_date IS NULL OR end_date >= ?)
        ''', (user_id, today, today))
        
        reminders = cursor.fetchall()
        conn.close()
        
        today_reminders = []
        for reminder in reminders:
            reminder_times = json.loads(reminder[7])
            for time in reminder_times:
                today_reminders.append({
                    "id": reminder[0],
                    "medication_name": reminder[2],
                    "dosage": reminder[3],
                    "time": time,
                    "notes": reminder[8]
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
        if actual_time is None:
            actual_time = datetime.now().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        scheduled_time = datetime.now().strftime("%H:%M")
        
        cursor.execute('''
            INSERT INTO reminder_logs 
            (reminder_id, scheduled_time, actual_time, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (reminder_id, scheduled_time, actual_time, "taken", notes, current_time))
        
        conn.commit()
        conn.close()
        
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO appointment_reminders 
            (user_id, doctor_name, department, appointment_date, appointment_time, 
             hospital, reminder_advance_days, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, doctor_name, department, appointment_date, appointment_time,
              hospital, reminder_advance_days, notes, current_time, current_time))
        
        appointment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
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
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM appointment_reminders 
            WHERE user_id = ? AND is_active = 1 
            AND appointment_date BETWEEN ? AND ?
            ORDER BY appointment_date, appointment_time
        ''', (user_id, today.isoformat(), end_date.isoformat()))
        
        appointments = cursor.fetchall()
        conn.close()
        
        appointment_list = []
        for appointment in appointments:
            appointment_dict = {
                "id": appointment[0],
                "doctor_name": appointment[2],
                "department": appointment[3],
                "appointment_date": appointment[4],
                "appointment_time": appointment[5],
                "hospital": appointment[6],
                "notes": appointment[7],
                "reminder_advance_days": appointment[8]
            }
            appointment_list.append(appointment_dict)
        
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