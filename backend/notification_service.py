import os
import logging
import time
import json
import uuid
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WeChatNotificationService:
    def __init__(self):
        self.app_id = os.environ.get("WECHAT_APP_ID")
        self.app_secret = os.environ.get("WECHAT_APP_SECRET")
        self.token_cache = {}
        self.redis_url = os.environ.get("REDIS_URL", "").strip()
        self._redis_client = None

        # 模板ID - 需要在微信后台配置并添加到环境变量
        # 默认尝试从环境变量获取，如果没有则使用空字符串（发送时会失败但会有日志）
        self.template_ids = {
            "task_complete": os.environ.get("WECHAT_TEMPLATE_TASK_COMPLETE", ""),
            "health_alert": os.environ.get("WECHAT_TEMPLATE_HEALTH_ALERT", ""),
            "medication_reminder": os.environ.get("WECHAT_TEMPLATE_MEDICATION_REMINDER", ""),
        }
        self.queue_key = os.environ.get("WECHAT_SUBSCRIBE_QUEUE_KEY", "wechat:subscribe_queue").strip() or "wechat:subscribe_queue"

    def _get_redis(self):
        if not self.redis_url:
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis

            self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
            return self._redis_client
        except Exception:
            self._redis_client = None
            return None

    def try_acquire_lock(self, key: str, ttl_sec: int) -> str | None:
        redis_client = self._get_redis()
        if redis_client is None:
            return None
        token = uuid.uuid4().hex
        try:
            ok = redis_client.set(str(key), token, nx=True, ex=max(1, int(ttl_sec)))
            return token if ok else None
        except Exception:
            return None

    def release_lock(self, key: str, token: str) -> bool:
        redis_client = self._get_redis()
        if redis_client is None:
            return False
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) "
            "else return 0 end"
        )
        try:
            res = redis_client.eval(script, 1, str(key), str(token))
            return bool(res)
        except Exception:
            return False

    def try_dedupe(self, key: str, ttl_sec: int) -> bool:
        redis_client = self._get_redis()
        if redis_client is None:
            return True
        try:
            ok = redis_client.set(str(key), "1", nx=True, ex=max(1, int(ttl_sec)))
            return bool(ok)
        except Exception:
            return True

    def enqueue_subscribe_message(
        self,
        *,
        openid: str,
        template_id: str,
        data: Dict[str, Any],
        page: str = "pages/index/index",
        dedupe_key: str = "",
        dedupe_ttl_sec: int = 900,
        extra: Dict[str, Any] | None = None,
    ) -> bool:
        redis_client = self._get_redis()
        if redis_client is None:
            return False
        if not openid or not template_id:
            return False
        if dedupe_key:
            try:
                ok = redis_client.set(
                    str(dedupe_key),
                    "1",
                    nx=True,
                    ex=max(1, int(dedupe_ttl_sec)),
                )
                if not ok:
                    return False
            except Exception:
                return False
        payload = {
            "openid": openid,
            "template_id": template_id,
            "page": page,
            "data": data,
            "extra": extra or {},
            "attempt": 0,
            "enqueued_at": time.time(),
        }
        try:
            redis_client.rpush(self.queue_key, json.dumps(payload, ensure_ascii=False))
            return True
        except Exception:
            return False

    async def get_access_token(self) -> Optional[str]:
        """获取微信 Access Token (带缓存)"""
        if not self.app_id or not self.app_secret:
            logger.error("Missing WECHAT_APP_ID or WECHAT_APP_SECRET")
            return None

        redis_client = self._get_redis()
        if redis_client is not None:
            try:
                cached = redis_client.get(f"wechat:access_token:{self.app_id}")
                if cached:
                    return str(cached)
            except Exception:
                pass

        now = time.time()
        if self.token_cache.get("access_token") and self.token_cache.get("expires_at", 0) > now:
            return self.token_cache["access_token"]

        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={self.app_id}&secret={self.app_secret}"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()

                if "access_token" in data:
                    token = str(data["access_token"])
                    self.token_cache["access_token"] = token
                    # 提前5分钟过期
                    expires_in = int(data.get("expires_in", 7200) or 7200)
                    ttl = max(60, expires_in - 300)
                    self.token_cache["expires_at"] = now + ttl
                    if redis_client is not None:
                        try:
                            redis_client.setex(f"wechat:access_token:{self.app_id}", ttl, token)
                        except Exception:
                            pass
                    return token
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
