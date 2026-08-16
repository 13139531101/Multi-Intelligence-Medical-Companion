"""阶段41-1: Skill + Tool HTTP 端点"""
import logging
from fastapi import APIRouter, Request
from ..skills import get_skill_registry, get_tool_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2", tags=["skills-tools"])


def _get_user_from_request(req: Request) -> dict:
    """从请求解析用户身份和角色（从 Authorization header 解 JWT）"""
    auth = req.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return {"user_id": "", "role": "guest"}
    token = auth[7:]
    try:
        from .oauth2 import decode_token
        payload = decode_token(token, "access")
        return {
            "user_id": payload.get("sub", ""),
            "role": payload.get("role", "user"),
        }
    except Exception as e:
        logger.debug("JWT decode failed: %s", e)
        return {"user_id": "", "role": "guest"}


@router.get("/skills")
async def list_skills(category: str = None):
    """列出所有 skills"""
    return {"skills": get_skill_registry().list_skills(category=category)}


@router.post("/skills/match")
async def match_skills(req: Request):
    """根据文本选 skills
    body: {text, top_k?}
    """
    body = await req.json()
    text = body.get("text", "")
    top_k = body.get("top_k", 2)
    skills = get_skill_registry().select_skills(text, top_k=top_k)
    return {
        "text": text,
        "matched": [s.to_dict() for s in skills],
        "count": len(skills),
    }


@router.get("/tools")
async def list_tools(category: str = None):
    """列出所有工具 + 统计"""
    return {
        "tools": get_tool_registry().list_tools(category=category),
        "stats": get_tool_registry().get_stats(),
    }


@router.post("/tools/call")
async def call_tool(req: Request):
    """调用工具（带 RBAC 权限检查）
    body: {name, args}
    需要 Authorization: Bearer <token> header，token 中包含 user_id 和 role
    """
    user = _get_user_from_request(req)
    if not user["user_id"]:
        return {"success": False, "error": "未授权: 缺少有效的认证 token", "code": "UNAUTHORIZED"}
    body = await req.json()
    # args 中的 user_id 会被 call_with_auth 的显式 user_id 覆盖，避免重复
    args = {k: v for k, v in body.get("args", {}).items() if k != "user_id"}
    return get_tool_registry().call_with_auth(
        name=body.get("name", ""),
        user_id=user["user_id"],
        user_role=user["role"],
        **args,
    )


@router.post("/tools/match")
async def match_tools(req: Request):
    """PHASE 6: 根据 query 动态选择最相关的 top_k 工具
    body: {query, top_k?, min_score?}
    """
    body = await req.body()
    import json as _json
    body = _json.loads(body.decode("utf-8"))
    query = body.get("query", "")
    top_k = body.get("top_k", 5)
    min_score = body.get("min_score", 0.05)
    matched = get_tool_registry().select_tools(query, top_k=top_k, min_score=min_score)
    return {
        "query": query,
        "matched": matched,
        "count": len(matched),
    }