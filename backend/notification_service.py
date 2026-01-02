import os
import json
import logging
import time
import asyncio
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class WeChatNotificationService:
    def __init__(self):
        self.app_id = os.environ.get("WECHAT_APP_ID")
        self.app_secret = os.environ.get("WECHAT_APP_SECRET")
        self.token_cache = {}

        # 模板ID - 需要在微信后台配置并添加到环境变量
        # 默认尝试从环境变量获取，如果没有则使用空字符串（发送时会失败但会有日志）
        self.template_ids = {
            "task_complete": os.environ.get("WECHAT_TEMPLATE_TASK_COMPLETE", ""),
            "health_alert": os.environ.get("WECHAT_TEMPLATE_HEALTH_ALERT", ""),
            "medication_reminder": os.environ.get("WECHAT_TEMPLATE_MEDICATION_REMINDER", ""),
        }

    async def get_access_token(self) -> Optional[str]:
        """获取微信 Access Token (带缓存)"""
        if not self.app_id or not self.app_secret:
            logger.error("Missing WECHAT_APP_ID or WECHAT_APP_SECRET")
            return None

        now = time.time()
        if self.token_cache.get("access_token") and self.token_cache.get("expires_at", 0) > now:
            return self.token_cache["access_token"]

        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={self.app_id}&secret={self.app_secret}"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()

                if "access_token" in data:
                    self.token_cache["access_token"] = data["access_token"]
                    # 提前5分钟过期
                    self.token_cache["expires_at"] = now + data.get("expires_in", 7200) - 300
                    return data["access_token"]
                else:
                    logger.error(f"Failed to get access token: {data}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching access token: {e}")
            return None

    async def send_subscribe_message(self, openid: str, template_id: str, data: Dict[str, Any], page: str = "pages/index/index") -> bool:
        """发送订阅消息"""
        token = await self.get_access_token()
        if not token:
            return False

        url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"

        payload = {
            "touser": openid,
            "template_id": template_id,
            "page": page,
            "data": data,
            "miniprogram_state": "developer" if os.environ.get("ENV") == "dev" else "formal",
            "lang": "zh_CN"
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload)
                res_data = resp.json()

                if res_data.get("errcode") == 0:
                    logger.info(f"Notification sent to {openid}")
                    return True
                else:
                    logger.error(f"Failed to send notification: {res_data}")
                    return False
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    async def code_to_session(self, code: str) -> Optional[Dict[str, Any]]:
        """Code 换取 OpenID"""
        if not self.app_id or not self.app_secret:
            return None

        url = f"https://api.weixin.qq.com/sns/jscode2session?appid={self.app_id}&secret={self.app_secret}&js_code={code}&grant_type=authorization_code"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if "openid" in data:
                    return data
                else:
                    logger.error(f"Code2Session failed: {data}")
                    return None
        except Exception as e:
            logger.error(f"Code2Session error: {e}")
            return None

# 全局单例
notification_service = WeChatNotificationService()
