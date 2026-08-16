"""
PHA v2 Admin API — 用户管理 + 工具权限配置

仅允许 admin 角色访问。
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, HTTPException

from .user_store import (
    list_users,
    get_user,
    create_user,
    update_user_role,
    delete_user,
    upsert_user,
    get_tool_role_override,
    set_tool_role_override,
    delete_tool_role_override,
    list_tool_role_overrides,
)
from .oauth2 import decode_token, extract_bearer
from ..skills import get_tool_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/admin", tags=["admin"])


def _get_admin_user(req: Request) -> dict:
    """验证 admin 角色"""
    auth = req.headers.get("authorization", "")
    token = extract_bearer(auth)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    try:
        payload = decode_token(token, "access")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    role = payload.get("role", "guest")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return {"user_id": payload.get("sub", ""), "role": role}


# ============================================================
# User Management
# ============================================================
@router.get("/users")
async def api_list_users(req: Request):
    """列出所有用户"""
    _get_admin_user(req)
    users = list_users()
    return {
        "users": [u.to_dict() for u in users],
        "total": len(users),
    }


@router.get("/users/{user_id}")
async def api_get_user(user_id: str, req: Request):
    """获取单个用户"""
    _get_admin_user(req)
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()


@router.post("/users")
async def api_create_user(req: Request):
    """创建用户"""
    _get_admin_user(req)
    body = await req.json()
    user_id = body.get("user_id", "")
    username = body.get("username", "")
    role = body.get("role", "user")
    if not user_id or not username:
        raise HTTPException(status_code=400, detail="user_id and username required")
    try:
        user = create_user(user_id, username, role)
        return user.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/users/{user_id}/role")
async def api_update_user_role(user_id: str, req: Request):
    """更新用户角色"""
    _get_admin_user(req)
    body = await req.json()
    role = body.get("role", "")
    if role not in ("guest", "user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user = update_user_role(user_id, role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()


@router.delete("/users/{user_id}")
async def api_delete_user(user_id: str, req: Request):
    """删除用户"""
    _get_admin_user(req)
    if user_id == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin user")
    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True}


@router.post("/users/upsert")
async def api_upsert_user(req: Request):
    """创建或更新用户（自动注册）"""
    _get_admin_user(req)
    body = await req.json()
    user_id = body.get("user_id", "")
    username = body.get("username", "Unknown")
    role = body.get("role", "user")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    user = upsert_user(user_id, username, role)
    return user.to_dict()


# ============================================================
# Tool Permission Configuration
# ============================================================
@router.get("/tools/permissions")
async def api_list_tool_permissions(req: Request):
    """列出所有工具及其当前 effective 权限配置"""
    _get_admin_user(req)
    registry = get_tool_registry()
    all_tools = registry.list_tools()
    overrides = list_tool_role_overrides()
    result = []
    for tool in all_tools:
        name = tool["name"]
        effective = overrides.get(name, tool.get("required_role", "guest"))
        result.append({
            "name": name,
            "description": tool.get("description", ""),
            "category": tool.get("category", ""),
            "default_role": tool.get("required_role", "guest"),
            "effective_role": effective,
            "is_overridden": name in overrides,
            "stats": tool.get("stats", {}),
        })
    return {"tools": result, "total": len(result)}


@router.put("/tools/{tool_name}/permission")
async def api_set_tool_permission(tool_name: str, req: Request):
    """设置工具的 required_role（覆盖默认值）"""
    _get_admin_user(req)
    body = await req.json()
    role = body.get("role", "")
    if role not in ("guest", "user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    # Verify tool exists
    registry = get_tool_registry()
    if tool_name not in [t["name"] for t in registry.list_tools()]:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    set_tool_role_override(tool_name, role)
    return {
        "tool_name": tool_name,
        "effective_role": role,
        "is_overridden": True,
    }


@router.delete("/tools/{tool_name}/permission")
async def api_delete_tool_permission(tool_name: str, req: Request):
    """删除工具的权限覆盖（恢复默认值）"""
    _get_admin_user(req)
    deleted = delete_tool_role_override(tool_name)
    return {"tool_name": tool_name, "deleted": deleted}


@router.get("/tool-permission-overrides")
async def api_get_overrides(req: Request):
    """获取所有工具权限覆盖"""
    _get_admin_user(req)
    return {"overrides": list_tool_role_overrides()}
