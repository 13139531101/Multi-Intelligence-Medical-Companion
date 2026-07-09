"""
PHA v2 桥接器（阶段4）

**作用**：把 A2A Message 转换为 v2 HostGraph 输入，调用 route_and_invoke，
把 v2 final_response 转换回 A2A Message 格式返回。

**协议兼容**：
- 输入：A2A JSON-RPC 2.0 Message（Pydantic）
- 输出：同样的 Message（v2 final_response.content -> Message.parts[0].text）

**降级机制**：
- LangChain 1.x 不可用 → 返回错误但不让 v1 路径阻塞
- v2 路由失败 → 自动 fallback 到 v1 adk_host_manager
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---- PHA v2 路径配置 ----
_PHA_BACKEND = Path(__file__).resolve().parents[5]  # 项目根
if str(_PHA_BACKEND) not in sys.path:
    sys.path.insert(0, str(_PHA_BACKEND))
if str(_PHA_BACKEND / "backend" / "A2AServer" / "src") not in sys.path:
    sys.path.insert(0, str(_PHA_BACKEND / "backend" / "A2AServer" / "src"))


def is_v2_enabled() -> bool:
    """v2 路径是否启用（环境变量控制）"""
    return os.getenv("PHA_USE_V2", "false").lower() in {"true", "1", "yes", "on"}


def is_v2_request(request) -> bool:
    """
    根据 request header 判断是否走 v2 路径

    触发条件（任一）：
    1. Header `X-PHA-Version: v2`
    2. Header `X-Use-V2: true`
    3. 环境变量 `PHA_USE_V2=true`（全量切流）
    """
    if is_v2_enabled():
        return True
    if request is None:
        return False
    try:
        headers = request.headers
        if headers.get("x-pha-version", "").lower() == "v2":
            return True
        if headers.get("x-use-v2", "").lower() == "true":
            return True
    except Exception:
        pass
    return False


def _extract_text_from_message(message) -> str:
    """从 A2A Message 提取用户文本"""
    text = ""
    if hasattr(message, "parts") and message.parts:
        for p in message.parts:
            if hasattr(p, "text") and p.text:
                text += p.text
    return text


def _build_v2_message(
    content: str,
    conversation_id: str,
    *,
    agent: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """从 v2 final_response 构造 A2A Message"""
    try:
        from A2AServer.common.A2Atypes import Message, Part, TextPart

        msg_metadata = dict(metadata or {})
        msg_metadata.setdefault("conversation_id", conversation_id)
        if agent:
            msg_metadata.setdefault("agent", agent)
            msg_metadata.setdefault("selected_agent", agent)
        msg_metadata.setdefault("source", "pha-v2-host-graph")

        return Message(
            role="agent",
            parts=[TextPart(text=content or " ")],
            metadata=msg_metadata,
        )
    except Exception as e:
        logger.error("[v2_bridge] 构造 Message 失败: %s", e)
        return None


async def v2_process_message(message) -> dict:
    """
    v2 主处理函数：调用 HostGraph 返回结果

    Returns:
        dict: {message: A2A Message | None, error: str | None, used_v2: True}
    """
    try:
        from A2AServer.v2 import route_and_invoke
    except ImportError as e:
        logger.error("[v2_bridge] 导入 v2 失败: %s", e)
        return {"message": None, "error": f"v2 import failed: {e}", "used_v2": True}

    # 提取输入
    query = _extract_text_from_message(message)
    if not query:
        return {"message": None, "error": "empty query", "used_v2": True}

    # 提取 metadata
    metadata = getattr(message, "metadata", None) or {}
    conversation_id = (
        metadata.get("conversation_id")
        or getattr(message, "conversation_id", None)
        or "default"
    )
    user_id = (
        metadata.get("user_id")
        or os.getenv("A2A_CURRENT_USER_ID")
        or os.getenv("USER_ID")
        or "default_user"
    )

    # 调 HostGraph
    try:
        result = await route_and_invoke(
            query=query,
            conversation_id=conversation_id,
            user_id=str(user_id),
            metadata=dict(metadata),
        )
    except Exception as e:
        logger.exception("[v2_bridge] route_and_invoke 失败")
        return {"message": None, "error": str(e), "used_v2": True}

    # 构造返回 Message
    agent = result.get("agent", "unknown")
    content = result.get("content", "")
    msg = _build_v2_message(
        content=content,
        conversation_id=conversation_id,
        agent=agent,
        metadata={
            **metadata,
            "v2_routing": result.get("routing", {}),
            "v2_tool_calls": result.get("tool_calls", []),
            "v2_error": result.get("error", False),
        },
    )

    if msg is None:
        return {"message": None, "error": "build message failed", "used_v2": True}

    return {"message": msg, "error": None, "used_v2": True, "result": result}
