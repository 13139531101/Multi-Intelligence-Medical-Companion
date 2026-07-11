"""
PHA v2 OAuth2 HTTP 端点（阶段20）
"""
import os
import logging
import time
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Header, Response

from . import oauth2

logger = logging.getLogger(__name__)

# 单独 router
oauth_router = APIRouter(prefix="/v2/oauth", tags=["oauth2"])


# ============================================================
# 1. 跳转到 GitHub 授权
# ============================================================
@oauth_router.get("/authorize")
async def authorize(
    redirect_to: str = Query(default="/", description="登录成功后跳转"),
    scope: str = Query(default=None, description="自定义 scope"),
):
    """
    构造 GitHub 授权 URL 并 302 跳转
    """
    try:
        state = oauth2.generate_state()
        url = oauth2.build_authorize_url(state=state, scope=scope)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return Response(
        status_code=302,
        headers={
            "Location": url,
            "Set-Cookie": f"oauth_state={state}; Path=/; Max-Age=600; HttpOnly; SameSite=Lax",
        },
    )


# ============================================================
# 2. GitHub 回调
# ============================================================
@oauth_router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    oauth_state: Optional[str] = None,  # 从 cookie 取（这里简化）
):
    """
    GitHub 回调：用 code 换 JWT
    """
    # 实际生产应校验 state == cookie 中的 oauth_state（防 CSRF）
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    try:
        result = await oauth2.complete_oauth_flow(code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OAuth flow failed")
        raise HTTPException(status_code=500, detail="oauth flow failed")
    oauth2._stats.issued += 1
    return result


# ============================================================
# 3. 用 refresh token 换新 token
# ============================================================
@oauth_router.post("/refresh")
async def refresh(refresh_token: str = Query(...)):
    """
    客户端带 refresh_token 来换新 access + refresh
    轮转：旧 refresh 撤销
    """
    try:
        result = await oauth2.refresh_tokens(refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    oauth2._stats.refreshes += 1
    return result


# ============================================================
# 4. 主动撤销 token
# ============================================================
@oauth_router.post("/revoke")
async def revoke(authorization: Optional[str] = Header(None), refresh_token: Optional[str] = Query(None)):
    """
    撤销 access token（从 Authorization header 拿）
    或撤销 refresh token（从 query 拿）
    """
    revoked_any = False
    # 撤销 access
    if authorization:
        token = oauth2.extract_bearer(authorization)
        if token:
            try:
                payload = oauth2.decode_token(token, expected_type="access")
                await oauth2.revoke_token(payload["jti"], payload["exp"])
                revoked_any = True
            except ValueError:
                pass
    # 撤销 refresh
    if refresh_token:
        try:
            payload = oauth2.decode_token(refresh_token, expected_type="refresh")
            await oauth2.revoke_token(payload["jti"], payload["exp"])
            revoked_any = True
        except ValueError:
            pass
    if not revoked_any:
        raise HTTPException(status_code=400, detail="no valid token to revoke")
    oauth2._stats.revokes += 1
    return {"revoked": True}


# ============================================================
# 5. 拿当前用户信息
# ============================================================
@oauth_router.get("/userinfo")
async def userinfo(authorization: Optional[str] = Header(None)):
    """从 Authorization header 拿当前 user_id"""
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    user_id = oauth2.get_current_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return {"user_id": user_id}


# ============================================================
# 6. 测试模式发 token（仅 PHA_OAUTH_TEST_MODE=true）
# ============================================================
@oauth_router.post("/test-issue")
async def test_issue(user_id: str = Query(default="test_user"), scope: str = Query(default="user")):
    """开发用：直接发 token，不走 GitHub"""
    if os.getenv("PHA_OAUTH_TEST_MODE", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="test mode disabled (set PHA_OAUTH_TEST_MODE=true)")
    try:
        result = oauth2.issue_test_token(user_id, scope)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    oauth2._stats.issued += 1
    return result


# ============================================================
# 7. OAuth 统计
# ============================================================
@oauth_router.get("/stats")
async def stats():
    """OAuth 服务统计"""
    # 清理过期撤销
    cleaned = _stats_revoked._store and oauth2._revoked.cleanup_expired() or 0
    return {
        **_stats_dump(),
        "revoked_cleaned_this_call": cleaned,
    }


# 简化 stats 输出
def _stats_dump():
    return oauth2._stats.to_dict()


# 兼容 monitor 引用
_stats_revoked = oauth2._revoked  # type: ignore
