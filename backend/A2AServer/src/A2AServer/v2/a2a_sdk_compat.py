"""
PHA v2 a2a-sdk 协议适配层（阶段5）

**作用**：在 PHA 现有 A2A 协议（TaskSendParams/Message） 与 a2a-sdk 标准协议
（SendMessageRequest/MessageSendParams）之间做转换。

**为什么需要适配层**：
- 现有 PHA 客户端发的是 `TaskSendParams(id, sessionId, message, acceptedOutputModes)`
- a2a-sdk 0.3.x 标准是 `SendMessageRequest(id, jsonrpc, method, params=MessageSendParams)`
- 字段名 / 嵌套结构完全不同，但语义等价

**降级机制**：
- a2a-sdk 不可用 → 用本地纯 dict 模拟协议（不破坏 v1）

**协议映射表**：
| PHA 现有 | a2a-sdk | 说明 |
|----------|---------|------|
| TaskSendParams.id | SendMessageRequest.id | JSON-RPC id |
| TaskSendParams.sessionId | MessageSendParams.contextId | 会话 ID |
| TaskSendParams.message | MessageSendParams.message | 用户消息 |
| TaskSendParams.acceptedOutputModes | MessageSendParams.configuration.acceptedOutputModes | 接受格式 |
| Message.parts | Message.parts | 文本/文件 parts |
| Task.id | Task.id | 任务 ID |
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---- a2a-sdk 0.3.x 探测 ----
_A2A_SDK_OK = False
try:
    from a2a.types import (
        Message as SdkMessage,
        TextPart as SdkTextPart,
        Part as SdkPart,
        Role as SdkRole,
        MessageSendParams as SdkMessageSendParams,
        SendMessageRequest as SdkSendMessageRequest,
        SendMessageResponse as SdkSendMessageResponse,
        AgentCard as SdkAgentCard,
    )
    _A2A_SDK_OK = True
    logger.info("[a2a_sdk_compat] a2a-sdk 0.3.x detected, using SDK types")
except ImportError as e:
    logger.warning("[a2a_sdk_compat] a2a-sdk 不可用: %s, 将使用 dict 协议", e)


# ============================================================
# PHA -> a2a-sdk 转换
# ============================================================
def pha_to_sdk_message(pha_message) -> Optional[Any]:
    """
    PHA Message -> a2a-sdk Message

    PHA: Message(role=..., parts=[TextPart(text='hi')], metadata={...})
    SDK: Message(messageId=..., role='user', parts=[Part(TextPart)], ...)
    """
    if not _A2A_SDK_OK:
        return None

    # 提取 text parts
    sdk_parts = []
    if hasattr(pha_message, "parts") and pha_message.parts:
        for p in pha_message.parts:
            text = getattr(p, "text", None) or (getattr(p, "root", None) and getattr(p.root, "text", None))
            if text:
                sdk_parts.append(SdkPart(root=SdkTextPart(text=str(text))))

    if not sdk_parts:
        sdk_parts.append(SdkPart(root=SdkTextPart(text=" ")))

    # role 转换
    pha_role = getattr(pha_message, "role", "user")
    sdk_role = SdkRole.user if pha_role in ("user", "client", "human") else SdkRole.agent

    return SdkMessage(
        messageId=str(uuid.uuid4()),
        role=sdk_role,
        parts=sdk_parts,
        metadata=getattr(pha_message, "metadata", None),
        # 0.3.25 中 contextId 通过 model_validate 设置更可靠
    )


def pha_to_sdk_request(pha_params: dict) -> Optional[Any]:
    """
    PHA TaskSendParams dict -> a2a-sdk SendMessageRequest

    PHA: {id, sessionId, message, acceptedOutputModes, metadata}
    SDK: SendMessageRequest(id, jsonrpc='2.0', method='message/send', params=MessageSendParams)
    """
    if not _A2A_SDK_OK:
        return None

    # 提取 message
    pha_msg = pha_params.get("message")
    sdk_msg = pha_to_sdk_message(pha_msg) if pha_msg else None

    # 构造 MessageSendParams（a2a-sdk 0.3.25+：contextId 在 Message 上，不在 params 上）
    if sdk_msg is not None:
        session_id = pha_params.get("sessionId") or pha_params.get("contextId")
        if session_id:
            # 0.3.25 pydantic alias: 用 model_validate 设置
            try:
                sdk_msg = SdkMessage.model_validate({
                    **sdk_msg.model_dump(exclude_none=True),
                    "contextId": session_id,
                })
            except Exception:
                pass  # 某些 SDK 版本不支持
    send_params = SdkMessageSendParams(
        message=sdk_msg,
        metadata=pha_params.get("metadata"),
    )

    # 构造 SendMessageRequest
    return SdkSendMessageRequest(
        id=pha_params.get("id") or str(uuid.uuid4()),
        params=send_params,
    )


# ============================================================
# a2a-sdk -> PHA 转换
# ============================================================
def sdk_to_pha_message(sdk_message) -> Optional[Any]:
    """
    a2a-sdk Message -> PHA Message

    SDK: Message(messageId, role, parts=[...], metadata)
    PHA: Message(role='agent', parts=[TextPart(text='hi')], metadata)
    """
    try:
        from A2AServer.common.A2Atypes import Message, TextPart
    except ImportError as e:
        logger.error("[a2a_sdk_compat] 导入 PHA Message 失败: %s", e)
        return None

    text_parts = []
    if hasattr(sdk_message, "parts") and sdk_message.parts:
        for p in sdk_message.parts:
            # SDK Part 是 root=TextPart / FilePart
            inner = getattr(p, "root", p)
            text = getattr(inner, "text", None)
            if text:
                text_parts.append(TextPart(text=str(text)))

    if not text_parts:
        text_parts.append(TextPart(text=" "))

    role_str = "agent"
    if hasattr(sdk_message, "role"):
        sdk_role = sdk_message.role
        role_str = "user" if str(sdk_role).lower() in ("user", "client", "human") else "agent"

    # metadata 合并
    meta = dict(getattr(sdk_message, "metadata", None) or {})
    msg_id = getattr(sdk_message, "messageId", None)
    if msg_id:
        meta.setdefault("message_id", msg_id)

    return Message(
        role=role_str,
        parts=text_parts,
        metadata=meta or None,
    )


# ============================================================
# AgentCard 构造（a2a-sdk 协议级发现）
# ============================================================
def build_pha_agent_card(
    *,
    name: str = "PHA HostGraph v2",
    description: str = "PHA 多智能体健康助理 (v2 HostGraph 编排)",
    url: str = "http://localhost:10010",
    version: str = "2.0.0",
) -> Optional[Any]:
    """构造 a2a-sdk AgentCard（用于协议级服务发现）"""
    if not _A2A_SDK_OK:
        return None
    return SdkAgentCard(
        name=name,
        description=description,
        url=url,
        version=version,
        capabilities={
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        defaultInputModes=["text", "text/plain"],
        defaultOutputModes=["text", "text/plain"],
        skills=[],
    )


# ============================================================
# 协议探测 / 开关
# ============================================================
def is_a2a_sdk_available() -> bool:
    """a2a-sdk 是否可用"""
    return _A2A_SDK_OK


def get_protocol_version() -> str:
    """返回当前 a2a-sdk 版本"""
    if not _A2A_SDK_OK:
        return "n/a"
    try:
        from importlib.metadata import version
        return f"a2a-sdk {version('a2a-sdk')}"
    except Exception:
        return "a2a-sdk unknown"
