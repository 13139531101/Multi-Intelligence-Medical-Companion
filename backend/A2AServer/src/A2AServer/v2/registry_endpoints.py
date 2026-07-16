"""阶段41-3: Skill/MCP 管理端点（增删改）"""
import json
import logging
from fastapi import APIRouter, Request
from .skills import get_skill_registry, Skill
from .mcp_loader import get_mcp_loader, MCPStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/registry", tags=["registry"])


# ============================================================
# Skills 管理
# ============================================================
@router.get("/skills")
async def list_skills():
    """列出所有 skills（含 enabled 状态）"""
    return {"skills": get_skill_registry().list_skills()}


@router.post("/skills/{name}/enable")
async def enable_skill(name: str):
    """启用 skill"""
    skill = get_skill_registry().get_skill(name)
    if not skill:
        return {"error": f"skill not found: {name}"}
    skill.enabled = True
    return {"enabled": True, "skill": skill.to_dict()}


@router.post("/skills/{name}/disable")
async def disable_skill(name: str):
    """禁用 skill"""
    skill = get_skill_registry().get_skill(name)
    if not skill:
        return {"error": f"skill not found: {name}"}
    skill.enabled = False
    return {"disabled": True, "skill": skill.to_dict()}


@router.post("/skills")
async def create_skill(req: Request):
    """创建自定义 skill
    body: {name, display_name, description, category?, tools?, keywords?, priority?, icon?, system_prompt_addon?}
    """
    body = await req.json()
    name = body.get("name")
    if not name:
        return {"error": "name required"}
    if get_skill_registry().get_skill(name):
        return {"error": f"skill already exists: {name}"}

    skill = Skill(
        name=name,
        display_name=body.get("display_name", name),
        description=body.get("description", ""),
        category=body.get("category", "custom"),
        tools=body.get("tools", []),
        system_prompt_addon=body.get("system_prompt_addon", ""),
        keywords=body.get("keywords", []),
        priority=body.get("priority", 50),
        icon=body.get("icon", "🆕"),
        enabled=body.get("enabled", True),
    )
    get_skill_registry().register_skill(skill)
    return {"created": True, "skill": skill.to_dict()}


@router.delete("/skills/{name}")
async def delete_skill(name: str):
    """删除 skill（不能删 6 个默认的）"""
    from .skills import DEFAULT_SKILLS
    default_names = {s.name for s in DEFAULT_SKILLS}
    if name in default_names:
        return {"error": f"cannot delete default skill: {name}"}
    reg = get_skill_registry()
    skill = reg.get_skill(name)
    if not skill:
        return {"error": f"skill not found: {name}"}
    if hasattr(reg, "_skills"):
        reg._skills.pop(name, None)
    return {"deleted": True, "name": name}


# ============================================================
# MCP 管理
# ============================================================
@router.get("/mcp/servers")
async def list_mcp_servers():
    """列出所有 MCP servers"""
    return {"servers": get_mcp_loader().list_servers()}


@router.post("/mcp/servers")
async def register_mcp(req: Request):
    """注册远程 MCP
    body: {name, url, type?, display_name?, description?}
    """
    body = await req.json()
    name = body.get("name")
    url = body.get("url")
    mcp_type = body.get("type", "http")
    if not name or not url:
        return {"error": "name and url required"}
    from .mcp_loader import MCPType
    server = get_mcp_loader().register_remote(
        name=name, url=url, mcp_type=MCPType(mcp_type),
        display_name=body.get("display_name"),
        description=body.get("description", ""),
    )
    return {"registered": server.to_dict()}


@router.post("/mcp/servers/{name}/enable")
async def enable_mcp(name: str):
    """启用 MCP server"""
    loader = get_mcp_loader()
    if name not in loader._servers:
        return {"error": f"MCP not found: {name}"}
    loader._servers[name].status = MCPStatus.CONNECTED
    return {"enabled": True, "server": loader._servers[name].to_dict()}


@router.post("/mcp/servers/{name}/disable")
async def disable_mcp(name: str):
    """禁用 MCP server"""
    loader = get_mcp_loader()
    if name not in loader._servers:
        return {"error": f"MCP not found: {name}"}
    loader._servers[name].status = MCPStatus.DISABLED
    return {"disabled": True, "server": loader._servers[name].to_dict()}


@router.delete("/mcp/servers/{name}")
async def delete_mcp(name: str):
    """删除 MCP server（不能删 4 个默认本地）"""
    default_names = {"health_records_mcp", "visit_summary_mcp",
                     "medication_reminder_mcp", "health_advisor_mcp"}
    if name in default_names:
        return {"error": f"cannot delete default MCP: {name}"}
    loader = get_mcp_loader()
    if name not in loader._servers:
        return {"error": f"MCP not found: {name}"}
    loader._servers.pop(name, None)
    return {"deleted": True, "name": name}


@router.post("/mcp/servers/{name}/health")
async def check_mcp_health(name: str):
    """对单个 MCP 做健康检查"""
    loader = get_mcp_loader()
    if name not in loader._servers:
        return {"error": f"MCP not found: {name}"}
    server = loader._servers[name]
    if server.mcp_type.value == "local":
        server.health_ok = True
        server.status = MCPStatus.CONNECTED
    else:
        loader._try_connect(server)
    return {"server": server.to_dict()}