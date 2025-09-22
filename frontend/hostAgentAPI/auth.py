#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户认证模块
提供用户注册、登录、JWT验证等功能
"""

import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)

# JWT配置
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'personal_health_assistant'),
    'charset': 'utf8mb4',
    'autocommit': True
}

# 安全相关
security = HTTPBearer()

# 请求/响应模型
class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    last_login_at: Optional[datetime] = None
    login_count: int
    status: int
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse

class AuthService:
    """认证服务类"""
    
    def __init__(self):
        self.db_config = DB_CONFIG
    
    def get_db_connection(self):
        """获取数据库连接"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            return connection
        except Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库连接失败"
            )
    
    def generate_salt(self) -> str:
        """生成密码盐值"""
        return secrets.token_hex(16)
    
    def hash_password(self, password: str, salt: str) -> str:
        """密码哈希"""
        return hashlib.sha256((password + salt).encode()).hexdigest()
    
    def verify_password(self, password: str, salt: str, hashed: str) -> bool:
        """验证密码"""
        return self.hash_password(password, salt) == hashed
    
    def generate_user_id(self) -> str:
        """生成用户ID"""
        return f"user_{secrets.token_hex(16)}"
    
    def create_jwt_token(self, user_data: Dict[str, Any]) -> str:
        """创建JWT token"""
        payload = {
            'user_id': user_data['user_id'],
            'username': user_data['username'],
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """验证JWT token"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token已过期"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的Token"
            )
    
    def register_user(self, user_data: UserRegister) -> Dict[str, Any]:
        """用户注册"""
        connection = self.get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
            # 检查用户名是否已存在
            cursor.execute("SELECT id FROM users WHERE username = %s", (user_data.username,))
            result = cursor.fetchone()
            cursor.fetchall()  # 清除所有剩余结果
            if result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="用户名已存在"
                )
            
            # 检查邮箱是否已存在
            if user_data.email:
                cursor.execute("SELECT id FROM users WHERE email = %s", (user_data.email,))
                result = cursor.fetchone()
                cursor.fetchall()  # 清除所有剩余结果
                if result:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="邮箱已被注册"
                    )
            
            # 检查手机号是否已存在
            if user_data.phone:
                cursor.execute("SELECT id FROM users WHERE phone = %s", (user_data.phone,))
                result = cursor.fetchone()
                cursor.fetchall()  # 清除所有剩余结果
                if result:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="手机号已被注册"
                    )
            
            # 创建新用户
            user_id = self.generate_user_id()
            salt = self.generate_salt()
            password_hash = self.hash_password(user_data.password, salt)
            
            insert_query = """
                INSERT INTO users (user_id, username, password_hash, salt, email, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                user_id, user_data.username, password_hash, salt,
                user_data.email, user_data.phone
            ))
            
            # 提交事务
            connection.commit()
            
            # 关闭当前游标，创建新游标来查询
            cursor.close()
            cursor = connection.cursor(dictionary=True)
            
            # 获取创建的用户信息
            cursor.execute("""
                SELECT user_id, username, email, phone, avatar_url, 
                       last_login_at, login_count, status, created_at
                FROM users WHERE user_id = %s
            """, (user_id,))
            
            user = cursor.fetchone()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="用户创建失败"
                )
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            connection.rollback()
            logger.error(f"用户注册失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="用户注册失败"
            )
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def authenticate_user(self, login_data: UserLogin) -> Dict[str, Any]:
        """用户登录认证"""
        connection = self.get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
            # 获取用户信息
            cursor.execute("""
                SELECT user_id, username, password_hash, salt, email, phone, 
                       avatar_url, last_login_at, login_count, status, created_at
                FROM users WHERE username = %s
            """, (login_data.username,))
            
            user = cursor.fetchone()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="用户名或密码错误"
                )
            
            # 检查用户状态
            if user['status'] != 1:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="账户已被禁用"
                )
            
            # 验证密码
            if not self.verify_password(login_data.password, user['salt'], user['password_hash']):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="用户名或密码错误"
                )
            
            # 更新登录信息
            cursor.execute("""
                UPDATE users 
                SET last_login_at = CURRENT_TIMESTAMP, login_count = login_count + 1
                WHERE user_id = %s
            """, (user['user_id'],))
            
            # 提交事务
            connection.commit()
            
            # 移除敏感信息
            user.pop('password_hash', None)
            user.pop('salt', None)
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            connection.rollback()
            logger.error(f"用户登录失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="登录失败"
            )
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        """根据用户ID获取用户信息"""
        connection = self.get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT user_id, username, email, phone, avatar_url, 
                       last_login_at, login_count, status, created_at
                FROM users WHERE user_id = %s AND status = 1
            """, (user_id,))
            
            user = cursor.fetchone()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="用户不存在"
                )
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="获取用户信息失败"
            )
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def save_user_session(self, user_id: str, token: str, ip_address: str = None, user_agent: str = None):
        """保存用户会话"""
        connection = self.get_db_connection()
        cursor = connection.cursor()
        
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expires_at = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
            
            cursor.execute("""
                INSERT INTO user_sessions (user_id, token_hash, expires_at, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, token_hash, expires_at, ip_address, user_agent))
            
            # 提交事务
            connection.commit()
            
        except Exception as e:
            connection.rollback()
            logger.error(f"保存用户会话失败: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

# 创建认证服务实例
auth_service = AuthService()

# 依赖注入：获取当前用户
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """获取当前登录用户"""
    token = credentials.credentials
    payload = auth_service.verify_jwt_token(token)
    user = auth_service.get_user_by_id(payload['user_id'])
    return user

# 创建路由
router = APIRouter(prefix="/auth", tags=["认证"])

@router.post("/register", response_model=TokenResponse, summary="用户注册")
async def register(user_data: UserRegister):
    """用户注册"""
    # 注册用户
    user = auth_service.register_user(user_data)
    
    # 生成JWT token
    token = auth_service.create_jwt_token(user)
    
    # 保存会话
    auth_service.save_user_session(user['user_id'], token)
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRATION_HOURS * 3600,
        user=UserResponse(**user)
    )

@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(login_data: UserLogin):
    """用户登录"""
    # 认证用户
    user = auth_service.authenticate_user(login_data)
    
    # 生成JWT token
    token = auth_service.create_jwt_token(user)
    
    # 保存会话
    auth_service.save_user_session(user['user_id'], token)
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRATION_HOURS * 3600,
        user=UserResponse(**user)
    )

@router.get("/user", response_model=UserResponse, summary="获取当前用户信息")
async def get_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserResponse(**current_user)

@router.post("/logout", summary="用户登出")
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """用户登出"""
    # 这里可以实现token黑名单或删除会话记录
    return {"message": "登出成功"}

@router.get("/verify", summary="验证Token")
async def verify_token(current_user: Dict[str, Any] = Depends(get_current_user)):
    """验证Token有效性"""
    return {"valid": True, "user_id": current_user['user_id']}