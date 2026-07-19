"""阶段48-16: HumanInTheLoop 危险 tool 配置.

根据 agent 名字决定哪些 tool 调用前需要人工确认.
"""
from __future__ import annotations
from typing import Dict

# ============================================================
# 通用危险操作 (所有 agent 都触发 human confirm)
# ============================================================
_DANGEROUS_KEYWORDS = (
    "delete",    # 删除数据
    "complete",  # 完成/标记完成
    "log_taken", # 记录已服用 (改变状态)
    "save_",     # 保存 (写入新数据)
    "add_",      # 添加 (新增数据)
    "update_",   # 更新
    "send_",     # 发送 (通知/邮件)
)


def is_dangerous(tool_name: str) -> bool:
    """简单关键词检查: tool 名含危险关键字 → dangerous."""
    n = tool_name.lower()
    return any(kw in n for kw in _DANGEROUS_KEYWORDS)


def get_interrupt_config(agent_name: str) -> dict:
    """返回 {tool_name: True} 给 HumanInTheLoopMiddleware.interrupt_on.

    Args:
        agent_name: 当前 agent 名字 (例如 'medication_reminder')

    Returns:
        dict: tool_name -> True (需要 interrupt)
    """
    # 不同 agent 危险 tool 名单
    if agent_name == "health_records":
        return {
            # 🔴 高危 — 不可逆
            "delete_reminder": True,
            "delete_health_record": True,
            # 🟡 中危 — 用户可能要确认
            "complete_reminder": True,
            "mark_reminder_taken": True,
            "add_medication_reminder": True,
            "save_health_record": True,
            "save_medication": True,
        }
    elif agent_name == "medication_reminder":
        return {
            "add_medication_reminder": True,
            "add_appointment_reminder": True,
            "log_medication_taken": True,  # 标记已吃
            # ⚠ 通知类 — 实际就是 send notification
            "send_medication_notification": True,
            "send_appointment_notification": True,
            "set_notification_preferences": True,
        }
    elif agent_name == "visit_summary":
        return {
            "save_generated_summary": True,    # 写入新总结
            "delete_visit_summary": True,      # 删除 (如有)
            "delete_health_record": True,
        }
    elif agent_name == "health_advisor":
        return {
            # ⚠ 删除知识库文档 → 高危
            "delete_medical_kb_document": True,
            "save_consultation": True,
            "upsert_medical_kb_document": True,
        }
    return {}  # 默认不 confirm (但仍可加 is_dangerous fallback)
