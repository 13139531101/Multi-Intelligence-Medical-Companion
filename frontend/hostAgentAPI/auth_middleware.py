#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
认证中间件
用于保护需要认证的API路由
"""

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging
from auth import auth_service

logger = logging.getLogger(__name__)

class AuthMiddleware:
    """认证中间件类"""
    
    def __init__(self):
        self.security = HTTPBearer(auto_error=False)
        # 定义不需要认证的路由
        self.public_routes = {
            "/ping",
            "/auth/register",
            "/auth/login",
            "/docs",
            "/openapi.json",
            "/redoc"
        }
    
    def is_public_route(self, path: str) -> bool:
        """检查是否为公开路由"""
        # 检查精确匹配
        if path in self.public_routes:
            return True
        
        # 检查路径前缀匹配
        for public_route in self.public_routes:
            if path.startswith(public_route):
                return True
        
        return False
    
    async def get_current_user_from_request(self, request: Request) -> Optional[Dict[str, Any]]:
        """从请求中获取当前用户"""
        try:
            # 检查是否为公开路由
            if self.is_public_route(request.url.path):
                return None
            
            # 获取Authorization header
            authorization = request.headers.get("Authorization")
            if not authorization:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="缺少认证信息",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # 解析Bearer token
            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的认证格式",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            token = authorization.split(" ")[1]
            
            # 验证token并获取用户信息
            payload = auth_service.verify_jwt_token(token)
            user = auth_service.get_user_by_id(payload['user_id'])
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"认证失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证失败",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    async def __call__(self, request: Request) -> Optional[Dict[str, Any]]:
        """中间件调用方法"""
        return await self.get_current_user_from_request(request)

# 创建认证中间件实例
auth_middleware = AuthMiddleware()

# 依赖注入函数
async def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    """可选的用户认证依赖（用于可选认证的路由）"""
    try:
        return await auth_middleware.get_current_user_from_request(request)
    except HTTPException:
        return None

async def get_current_user_required(request: Request) -> Dict[str, Any]:
    """必需的用户认证依赖（用于需要认证的路由）"""
    user = await auth_middleware.get_current_user_from_request(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user