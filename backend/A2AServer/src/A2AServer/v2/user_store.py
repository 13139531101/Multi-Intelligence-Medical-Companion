"""
PHA v2 用户存储 + RBAC 管理 API

提供：
- 用户注册/列表/更新/删除（in-memory，生产应接 PG）
- 角色管理（guest/user/admin）
- 工具权限配置管理
"""
from __future__ import annotations

import time
import logging
import secrets
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class Role(Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"


ROLE_LEVEL = {Role.GUEST: 1, Role.USER: 2, Role.ADMIN: 3}


@dataclass
class User:
    user_id: str
    username: str
    role: str = "user"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active": self.active,
        }


# In-memory user store (keyed by user_id)
_USER_STORE: Dict[str, User] = {
    "admin": User(user_id="admin", username="Administrator", role="admin"),
    "gh:majiahui": User(user_id="gh:majiahui", username="majiahui", role="user"),
}

# In-memory tool permission overrides (tool_name -> required_role)
_TOOL_ROLE_OVERRIDES: Dict[str, str] = {}


def get_user(user_id: str) -> Optional[User]:
    return _USER_STORE.get(user_id)


def list_users() -> List[User]:
    return list(_USER_STORE.values())


def create_user(user_id: str, username: str, role: str = "user") -> User:
    if user_id in _USER_STORE:
        raise ValueError(f"user {user_id} already exists")
    user = User(user_id=user_id, username=username, role=role)
    _USER_STORE[user_id] = user
    logger.info("[user_store] created user %s with role %s", user_id, role)
    return user


def update_user_role(user_id: str, role: str) -> Optional[User]:
    user = _USER_STORE.get(user_id)
    if not user:
        return None
    if role not in ("guest", "user", "admin"):
        raise ValueError(f"invalid role: {role}")
    user.role = role
    user.updated_at = time.time()
    logger.info("[user_store] updated user %s role -> %s", user_id, role)
    return user


def delete_user(user_id: str) -> bool:
    if user_id not in _USER_STORE:
        return False
    del _USER_STORE[user_id]
    logger.info("[user_store] deleted user %s", user_id)
    return True


def upsert_user(user_id: str, username: str, role: str = "user") -> User:
    """Create or update a user"""
    user = _USER_STORE.get(user_id)
    if user:
        user.username = username
        user.role = role
        user.updated_at = time.time()
    else:
        user = User(user_id=user_id, username=username, role=role)
        _USER_STORE[user_id] = user
    return user


# ============================================================
# Tool permission overrides
# ============================================================
def get_tool_role_override(tool_name: str) -> Optional[str]:
    """Get override for a specific tool, None means use default"""
    return _TOOL_ROLE_OVERRIDES.get(tool_name)


def set_tool_role_override(tool_name: str, role: str) -> None:
    if role not in ("guest", "user", "admin"):
        raise ValueError(f"invalid role: {role}")
    _TOOL_ROLE_OVERRIDES[tool_name] = role
    logger.info("[user_store] tool %s required_role -> %s", tool_name, role)


def delete_tool_role_override(tool_name: str) -> bool:
    if tool_name in _TOOL_ROLE_OVERRIDES:
        del _TOOL_ROLE_OVERRIDES[tool_name]
        logger.info("[user_store] tool %s role override removed", tool_name)
        return True
    return False


def list_tool_role_overrides() -> Dict[str, str]:
    return dict(_TOOL_ROLE_OVERRIDES)


def get_effective_tool_role(tool_name: str, default_role: str) -> str:
    """Get effective role for a tool (override takes precedence)"""
    return _TOOL_ROLE_OVERRIDES.get(tool_name, default_role)
