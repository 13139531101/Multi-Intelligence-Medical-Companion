"""
PHASE RBAC: 工具权限系统 (tool_permissions.py)

基于角色的访问控制（RBAC）—— 不同角色用户只能调用被允许的工具子集。

角色等级: guest(1) < user(2) < admin(3)
"""
from enum import Enum
from typing import Dict

# ============================================================
# 角色定义
# ============================================================
class Role(Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"


ROLE_LEVEL: Dict[Role, int] = {
    Role.GUEST: 1,
    Role.USER: 2,
    Role.ADMIN: 3,
}

# 危险操作工具前缀（admin only）
ADMIN_ONLY_PREFIXES = (
    "delete_",
    "drop_",
    "purge_",
    "wipe_",
    "destroy_",
    "reset_",
    "truncate_",
)

# 写操作工具前缀（需要经过写审计）
WRITE_OP_PREFIXES = (
    "save_",
    "add_",
    "update_",
    "upsert_",
    "log_",
    "complete_",
    "mark_",
    "send_",
)

# 默认工具权限映射（tool_name → minimum required role）
DEFAULT_TOOL_ROLES: Dict[str, str] = {
    # guest 可用：只读工具
    "get_health_records": "guest",
    "get_medication_reminders": "guest",
    "calculate_bmi": "guest",
    "search_drug_info": "guest",
    "list_": "guest",
    "get_": "guest",
    "query_": "guest",
    "search_": "guest",
    # user 可用：写操作
    "schedule_visit": "user",
    "log_medication_taken": "user",
    "save_health_record": "user",
    "save_medication": "user",
    "add_medication_reminder": "user",
    "add_appointment_reminder": "user",
    "send_medication_notification": "user",
    "send_appointment_notification": "user",
    "save_consultation": "user",
    "save_generated_summary": "user",
    "upsert_medical_kb_document": "user",
    "create_": "user",
    "set_notification_preferences": "user",
    # admin only：危险操作
    "delete_health_record": "admin",
    "delete_reminder": "admin",
    "delete_visit_summary": "admin",
    "delete_medical_kb_document": "admin",
    "revoke_": "admin",
    "change_password": "admin",
    "update_password": "admin",
}


def get_required_role(tool_name: str) -> str:
    """查询工具需要的最低角色（默认 guest）"""
    # 精确匹配优先
    if tool_name in DEFAULT_TOOL_ROLES:
        return DEFAULT_TOOL_ROLES[tool_name]
    # 前缀匹配
    for prefix, role in DEFAULT_TOOL_ROLES.items():
        if tool_name.startswith(prefix):
            return role
    return "guest"


def check_permission(tool_name: str, user_role: str) -> bool:
    """检查用户角色是否足够调用该工具"""
    required_str = get_required_role(tool_name)
    try:
        required = Role(required_str)
    except ValueError:
        required = Role.GUEST
    try:
        user = Role(user_role)
    except ValueError:
        user = Role.GUEST
    return ROLE_LEVEL.get(user, 0) >= ROLE_LEVEL.get(required, 1)


def check_admin_only(tool_name: str) -> bool:
    """检查是否 admin-only 危险工具"""
    return any(tool_name.startswith(p) for p in ADMIN_ONLY_PREFIXES)


def check_write_operation(tool_name: str) -> bool:
    """检查是否是写操作（需要经过写审计层）"""
    return any(tool_name.startswith(p) for p in WRITE_OP_PREFIXES)


def get_role_level(role_str: str) -> int:
    """获取角色等级数值（用于比较）"""
    try:
        return ROLE_LEVEL[Role(role_str)]
    except ValueError:
        return 0
