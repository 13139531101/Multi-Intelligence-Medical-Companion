from mcp.server.fastmcp import FastMCP
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import sqlite3

# 创建 FastMCP 应用
mcp = FastMCP("NotificationTool")

# 数据库文件路径
DB_PATH = "medication_reminders.db"

@mcp.tool()
def send_medication_notification(user_id: str, medication_name: str, dosage: str, 
                               scheduled_time: str, notification_type: str = "reminder") -> Dict[str, Any]:
    """
    发送用药通知
    
    Args:
        user_id: 用户ID
        medication_name: 药物名称
        dosage: 剂量
        scheduled_time: 预定时间
        notification_type: 通知类型（reminder/overdue/missed）
    
    Returns:
        通知发送结果
    """
    try:
        current_time = datetime.now().strftime("%H:%M")
        
        # 根据通知类型生成不同的消息
        if notification_type == "reminder":
            message = f"⏰ 用药提醒\n\n药物：{medication_name}\n剂量：{dosage}\n时间：{scheduled_time}\n\n请按时服药，保持健康！"
            title = "用药提醒"
        elif notification_type == "overdue":
            message = f"⚠️ 用药逾期提醒\n\n药物：{medication_name}\n剂量：{dosage}\n预定时间：{scheduled_time}\n当前时间：{current_time}\n\n您的用药时间已过，请尽快服药！"
            title = "用药逾期提醒"
        elif notification_type == "missed":
            message = f"❌ 漏服提醒\n\n药物：{medication_name}\n剂量：{dosage}\n预定时间：{scheduled_time}\n\n您错过了用药时间，请咨询医生是否需要补服。"
            title = "漏服提醒"
        else:
            message = f"📋 用药通知\n\n药物：{medication_name}\n剂量：{dosage}\n时间：{scheduled_time}"
            title = "用药通知"
        
        # 模拟发送通知（实际应用中可以集成推送服务）
        notification_data = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "medication": medication_name,
            "dosage": dosage,
            "scheduled_time": scheduled_time,
            "sent_time": datetime.now().isoformat(),
            "status": "sent"
        }
        
        return {
            "status": "success",
            "message": "通知发送成功",
            "notification": notification_data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"发送通知失败：{str(e)}"
        }

@mcp.tool()
def send_appointment_notification(user_id: str, doctor_name: str, department: str,
                                appointment_date: str, appointment_time: str, 
                                hospital: str, advance_days: int) -> Dict[str, Any]:
    """
    发送复诊预约通知
    
    Args:
        user_id: 用户ID
        doctor_name: 医生姓名
        department: 科室
        appointment_date: 预约日期
        appointment_time: 预约时间
        hospital: 医院名称
        advance_days: 提前天数
    
    Returns:
        通知发送结果
    """
    try:
        if advance_days == 0:
            title = "今日复诊提醒"
            time_desc = "今天"
        elif advance_days == 1:
            title = "明日复诊提醒"
            time_desc = "明天"
        else:
            title = f"{advance_days}天后复诊提醒"
            time_desc = f"{advance_days}天后"
        
        message = f"🏥 复诊预约提醒\n\n医生：{doctor_name}\n科室：{department}\n医院：{hospital}\n时间：{time_desc} {appointment_time}\n日期：{appointment_date}\n\n请提前准备相关资料，按时就诊。"
        
        notification_data = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": "appointment",
            "doctor": doctor_name,
            "department": department,
            "hospital": hospital,
            "appointment_date": appointment_date,
            "appointment_time": appointment_time,
            "advance_days": advance_days,
            "sent_time": datetime.now().isoformat(),
            "status": "sent"
        }
        
        return {
            "status": "success",
            "message": "复诊提醒发送成功",
            "notification": notification_data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"发送复诊提醒失败：{str(e)}"
        }

@mcp.tool()
def check_overdue_medications(user_id: str, tolerance_minutes: int = 30) -> Dict[str, Any]:
    """
    检查逾期用药
    
    Args:
        user_id: 用户ID
        tolerance_minutes: 容忍分钟数（超过此时间算逾期）
    
    Returns:
        逾期用药列表
    """
    try:
        current_time = datetime.now()
        current_date = current_time.strftime("%Y-%m-%d")
        current_time_str = current_time.strftime("%H:%M")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 获取今日活跃的用药提醒
        cursor.execute('''
            SELECT * FROM medication_reminders 
            WHERE user_id = ? AND is_active = 1 
            AND start_date <= ? 
            AND (end_date IS NULL OR end_date >= ?)
        ''', (user_id, current_date, current_date))
        
        reminders = cursor.fetchall()
        
        overdue_medications = []
        
        for reminder in reminders:
            reminder_times = json.loads(reminder[7])
            
            for time_str in reminder_times:
                # 解析提醒时间
                reminder_time = datetime.strptime(f"{current_date} {time_str}", "%Y-%m-%d %H:%M")
                
                # 计算是否逾期
                time_diff = current_time - reminder_time
                
                if time_diff.total_seconds() > tolerance_minutes * 60:
                    # 检查是否已经记录用药
                    cursor.execute('''
                        SELECT COUNT(*) FROM reminder_logs 
                        WHERE reminder_id = ? AND scheduled_time = ? 
                        AND DATE(created_at) = ? AND status = 'taken'
                    ''', (reminder[0], time_str, current_date))
                    
                    taken_count = cursor.fetchone()[0]
                    
                    if taken_count == 0:  # 未记录用药
                        overdue_medications.append({
                            "reminder_id": reminder[0],
                            "medication_name": reminder[2],
                            "dosage": reminder[3],
                            "scheduled_time": time_str,
                            "overdue_minutes": int(time_diff.total_seconds() / 60)
                        })
        
        conn.close()
        
        return {
            "status": "success",
            "overdue_medications": overdue_medications,
            "count": len(overdue_medications),
            "check_time": current_time.isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"检查逾期用药失败：{str(e)}"
        }

@mcp.tool()
def generate_daily_summary(user_id: str, date: Optional[str] = None) -> Dict[str, Any]:
    """
    生成每日用药总结
    
    Args:
        user_id: 用户ID
        date: 日期（YYYY-MM-DD格式，默认为今天）
    
    Returns:
        每日用药总结
    """
    try:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 获取当日的用药提醒
        cursor.execute('''
            SELECT * FROM medication_reminders 
            WHERE user_id = ? AND is_active = 1 
            AND start_date <= ? 
            AND (end_date IS NULL OR end_date >= ?)
        ''', (user_id, date, date))
        
        reminders = cursor.fetchall()
        
        total_doses = 0
        taken_doses = 0
        missed_doses = 0
        medication_details = []
        
        for reminder in reminders:
            reminder_times = json.loads(reminder[7])
            
            for time_str in reminder_times:
                total_doses += 1
                
                # 检查是否已服药
                cursor.execute('''
                    SELECT * FROM reminder_logs 
                    WHERE reminder_id = ? AND scheduled_time = ? 
                    AND DATE(created_at) = ? AND status = 'taken'
                ''', (reminder[0], time_str, date))
                
                log = cursor.fetchone()
                
                if log:
                    taken_doses += 1
                    status = "已服用"
                    actual_time = log[3] if log[3] else "未记录"
                else:
                    # 检查是否已过时间
                    current_time = datetime.now()
                    scheduled_datetime = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
                    
                    if current_time > scheduled_datetime:
                        missed_doses += 1
                        status = "已错过"
                        actual_time = None
                    else:
                        status = "待服用"
                        actual_time = None
                
                medication_details.append({
                    "medication_name": reminder[2],
                    "dosage": reminder[3],
                    "scheduled_time": time_str,
                    "status": status,
                    "actual_time": actual_time
                })
        
        conn.close()
        
        # 计算服药率
        compliance_rate = (taken_doses / total_doses * 100) if total_doses > 0 else 0
        
        summary = {
            "date": date,
            "total_doses": total_doses,
            "taken_doses": taken_doses,
            "missed_doses": missed_doses,
            "pending_doses": total_doses - taken_doses - missed_doses,
            "compliance_rate": round(compliance_rate, 1),
            "medication_details": medication_details
        }
        
        # 生成建议
        if compliance_rate >= 90:
            advice = "服药依从性很好，请继续保持！"
        elif compliance_rate >= 70:
            advice = "服药依从性良好，建议设置更多提醒以提高准确性。"
        else:
            advice = "服药依从性需要改善，建议咨询医生调整用药方案或设置更频繁的提醒。"
        
        return {
            "status": "success",
            "summary": summary,
            "advice": advice
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"生成每日总结失败：{str(e)}"
        }

@mcp.tool()
def set_notification_preferences(user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
    """
    设置通知偏好
    
    Args:
        user_id: 用户ID
        preferences: 通知偏好设置
    
    Returns:
        设置结果
    """
    try:
        # 模拟保存通知偏好（实际应用中应保存到数据库）
        default_preferences = {
            "enable_sound": True,
            "enable_vibration": True,
            "snooze_duration": 5,  # 分钟
            "max_snooze_count": 3,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "07:00",
            "advance_reminder_minutes": 10
        }
        
        # 合并用户偏好
        updated_preferences = {**default_preferences, **preferences}
        
        return {
            "status": "success",
            "message": "通知偏好设置成功",
            "preferences": updated_preferences
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"设置通知偏好失败：{str(e)}"
        }

if __name__ == "__main__":
    mcp.run()