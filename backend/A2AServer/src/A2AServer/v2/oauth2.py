"""
PHA v2 OAuth2 鉴权（阶段20）

实现：
- GitHub 授权码流程（OAuth 2.0 Authorization Code）
- JWT access token（15 分钟短命）+ refresh token（7 天长命）
- Refresh token 轮转（每次 refresh 颁发新 token，旧 token 撤销）
- Token 撤销列表（in-memory fallback，未来可接 Redis）
- Token 签发速率限制（防滥用）

端点（在 oauth2_endpoints.py）：
  GET  /v2/oauth/authorize        跳转到 GitHub
  GET  /v2/oauth/callback         GitHub 回调
  POST /v2/oauth/refresh          用 refresh 换 access
  POST /v2/oauth/revoke           主动撤销
  GET  /v2/oauth/userinfo         拿当前用户信息

依赖：
  - httpx（GitHub API 调用）
  - PyJWT（已 auth.py 装好）
  - 现有 JWT_SECRET_KEY
"""
import os
import time
import json
import hmac
import hashlib
import secrets
import logging
import asyncio
import urllib.parse
from typing import Optional, Dict, Any
from collections import deque
from dataclasses import dataclass, field

import httpx
import jwt

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "pha-v2-default-secret-change-me")
JWT_ALGORITHM = "HS256"

# Access 15 分钟，Refresh 7 天
ACCESS_TOKEN_TTL = int(os.getenv("PHA_ACCESS_TOKEN_TTL", "900"))  # 15 min
REFRESH_TOKEN_TTL = int(os.getenv("PHA_REFRESH_TOKEN_TTL", "604800"))  # 7 day

# GitHub OAuth 配置
GITHUB_OAUTH_CLIENT_ID = os.getenv("GITHUB_OAUTH_CLIENT_ID", "")
GITHUB_OAUTH_CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:13002/v2/oauth/callback")
OAUTH_SCOPES = "read:user user:email"  # 拿基本资料 + email

# 签发限流：每 IP 每分钟最多 N 次新签发
ISSUE_RATE_LIMIT_PER_MIN = int(os.getenv("PHA_OAUTH_ISSUE_RATE_LIMIT", "20"))


# ============================================================
# Token 撤销列表（in-memory）
# 生产用 Redis 持久化
# ============================================================
@dataclass
class _RevokedTokenStore:
    """撤销的 token 集合（jti -> expires_at）"""
    _store: Dict[str, float] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def revoke(self, jti: str, expires_at: float) -> None:
        async with self._lock:
            self._store[jti] = expires_at

    async def is_revoked(self, jti: str) -> bool:
        async with self._lock:
            return jti in self._store

    def cleanup_expired(self) -> int:
        """清理已过期的撤销记录（同步）"""
        now = time.time()
        expired = [k for k, v in self._store.items() if v < now]
        for k in expired:
            del self._store[k]
        return len(expired)


_revoked = _RevokedTokenStore()


# ============================================================
# 签发限流（每 IP）
# ============================================================
@dataclass
class _IssueRateLimiter:
    _per_ip: Dict[str, deque] = field(default_factory=dict)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        dq = self._per_ip.setdefault(ip, deque())
        # 60s 窗口
        while dq and dq[0] < now - 60:
            dq.popleft()
        if len(dq) >= ISSUE_RATE_LIMIT_PER_MIN:
            return False
        dq.append(now)
        return True


_issue_limiter = _IssueRateLimiter()


# ============================================================
# JWT 颁发/校验
# ============================================================
def create_access_token(user_id: str, scope: str = "user") -> dict:
    """颁发 access token"""
    now = int(time.time())
    jti = secrets.token_urlsafe(16)
    payload = {
        "sub": user_id,
        "scope": scope,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
        "jti": jti,
        "iss": "pha-v2",
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL,
        "scope": scope,
        "jti": jti,
    }


def create_refresh_token(user_id: str) -> dict:
    """颁发 refresh token（更长的 exp，单独的 jti）"""
    now = int(time.time())
    jti = secrets.token_urlsafe(24)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + REFRESH_TOKEN_TTL,
        "jti": jti,
        "iss": "pha-v2",
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "refresh_token": token,
        "expires_in": REFRESH_TOKEN_TTL,
        "jti": jti,
    }


def decode_token(token: str, expected_type: str = "access") -> dict:
    """
    解码 token，校验签名 + 类型 + 是否被撤销
    expected_type: "access" / "refresh"
    返回 payload dict
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("token expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"invalid token: {e}")
    if payload.get("type") != expected_type:
        raise ValueError(f"token type mismatch (expected {expected_type}, got {payload.get('type')})")
    # 同步检查撤销（这里不能 await）
    jti = payload.get("jti", "")
    if jti in _revoked._store and _revoked._store[jti] > time.time():
        raise ValueError("token revoked")
    return payload


async def revoke_token(jti: str, exp: int) -> None:
    """撤销 token（异步）"""
    await _revoked.revoke(jti, float(exp))


async def refresh_tokens(refresh_token: str) -> dict:
    """
    用 refresh token 换新的 access + refresh
    轮转：旧 refresh 撤销
    """
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = payload["sub"]
    old_jti = payload["jti"]
    old_exp = payload["exp"]

    # 撤销旧 refresh
    await revoke_token(old_jti, old_exp)

    # 颁发新 access + refresh
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    return {
        "access_token": access["access_token"],
        "token_type": "Bearer",
        "expires_in": access["expires_in"],
        "refresh_token": refresh["refresh_token"],
        "refresh_expires_in": refresh["expires_in"],
        "scope": access["scope"],
    }


# ============================================================
# GitHub OAuth 2.0 授权码流程
# ============================================================
def build_authorize_url(state: str, scope: str = None) -> str:
    """构造 GitHub 授权 URL"""
    if not GITHUB_OAUTH_CLIENT_ID:
        raise ValueError("GITHUB_OAUTH_CLIENT_ID not configured")
    scope = scope or OAUTH_SCOPES
    params = {
        "client_id": GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": scope,
        "state": state,
        "response_type": "code",
    }
    return "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)


def generate_state() -> str:
    """生成 CSRF state（32 字节随机）"""
    return secrets.token_urlsafe(32)


async def exchange_code_for_token(code: str) -> str:
    """用 code 换 GitHub access_token"""
    if not GITHUB_OAUTH_CLIENT_ID or not GITHUB_OAUTH_CLIENT_SECRET:
        raise ValueError("GitHub OAuth credentials not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_OAUTH_CLIENT_ID,
                "client_secret": GITHUB_OAUTH_CLIENT_SECRET,
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")
        return data["access_token"]


async def fetch_github_user(github_token: str) -> dict:
    """用 GitHub access_token 拿用户信息"""
    async with httpx.AsyncClient(timeout=10) as client:
        # 1. user info
        r = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        user = r.json()
        # 2. emails (拿主邮箱)
        r2 = await client.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if r2.status_code == 200:
            emails = r2.json()
            primary = next((e for e in emails if e.get("primary")), None)
            if primary:
                user["email"] = primary["email"]
        return {
            "github_id": user["id"],
            "login": user["login"],
            "name": user.get("name") or user["login"],
            "email": user.get("email", ""),
            "avatar_url": user.get("avatar_url", ""),
        }


async def login_or_register_github_user(github_user: dict) -> str:
    """
    用 GitHub 用户信息登录或注册
    返回 PHA user_id
    生产用数据库；测试用 in-memory store
    """
    github_id = str(github_user["github_id"])
    # 简化：user_id = "gh:{login}"
    return f"gh:{github_user['login']}"


async def complete_oauth_flow(code: str) -> dict:
    """
    完整 OAuth2 流程：
      code → GitHub access_token → user info → PHA user_id → JWT
    """
    gh_token = await exchange_code_for_token(code)
    gh_user = await fetch_github_user(gh_token)
    user_id = await login_or_register_github_user(gh_user)
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    return {
        "user_id": user_id,
        "github_user": gh_user,
        "access_token": access["access_token"],
        "token_type": "Bearer",
        "expires_in": access["expires_in"],
        "refresh_token": refresh["refresh_token"],
        "refresh_expires_in": refresh["expires_in"],
        "scope": access["scope"],
    }


# ============================================================
# 测试/开发用：直接发 token（无 GitHub）
# ============================================================
def issue_test_token(user_id: str = "test_user", scope: str = "user") -> dict:
    """
    不走 GitHub，直接发 token（仅 PHA_OAUTH_TEST_MODE=true 时可用）
    """
    if os.getenv("PHA_OAUTH_TEST_MODE", "false").lower() != "true":
        raise PermissionError("test mode disabled")
    access = create_access_token(user_id, scope)
    refresh = create_refresh_token(user_id)
    return {
        "user_id": user_id,
        "access_token": access["access_token"],
        "token_type": "Bearer",
        "expires_in": access["expires_in"],
        "refresh_token": refresh["refresh_token"],
        "refresh_expires_in": refresh["expires_in"],
        "scope": scope,
    }


# ============================================================
# 工具函数：Bearer 解析
# ============================================================
def extract_bearer(auth_header: str) -> Optional[str]:
    """从 Authorization header 提取 Bearer token"""
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def get_current_user_id(auth_header: str) -> Optional[str]:
    """从 Authorization header 拿当前 user_id（access token）"""
    token = extract_bearer(auth_header)
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
        return payload.get("sub")
    except ValueError:
        return None


# ============================================================
# 统计
# ============================================================
@dataclass
class OAuthStats:
    issued: int = 0
    refreshes: int = 0
    revokes: int = 0
    rate_limited: int = 0
    invalid_tokens: int = 0
    expired_tokens: int = 0

    def to_dict(self):
        return {
            "issued": self.issued,
            "refreshes": self.refreshes,
            "revokes": self.revokes,
            "rate_limited": self.rate_limited,
            "invalid_tokens": self.invalid_tokens,
            "expired_tokens": self.expired_tokens,
            "revoked_store_size": len(_revoked._store),
            "config": {
                "access_ttl": ACCESS_TOKEN_TTL,
                "refresh_ttl": REFRESH_TOKEN_TTL,
                "issue_rate_limit_per_min": ISSUE_RATE_LIMIT_PER_MIN,
                "github_configured": bool(GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET),
                "test_mode": os.getenv("PHA_OAUTH_TEST_MODE", "false").lower() == "true",
            },
        }


_stats = OAuthStats()
