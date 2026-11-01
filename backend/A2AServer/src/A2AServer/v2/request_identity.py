# -*- coding: utf-8 -*-
"""
请求身份与客户端元数据的**唯一收口点**。

背景
----
F-001 / F-002 / F-003 / F-012（见 llm-security-lab/findings.md）都出自同一处：
`/v2/chat/stream` 让**请求体参与了安全决策**。

    user_id = body.get("user_id") or token_uid or "default_user"   # 请求体压过 token
    metadata = {"conversation_id": ..., "user_id": ..., **metadata}  # ** 在后 → 客户端覆盖服务端

两处都是同一个错误：**把 Asserted（客户端/模型自报）的值当成了 Subject（已认证身份）**。

为什么抽成独立模块
------------------
安全决策埋在 5000 行的 api.py 里，等于不可测：
改一处忘另一处，没人会发现，因为没人能独立跑它。收进纯函数后：

  - 单元测试毫秒级、不依赖 DB / 网络 / LLM → 能当 CI 阻塞门禁
  - 修一次只需要改这一处 → **收口优于过滤**

本模块不依赖任何重组件，import 即可用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

# 客户端**可以**指定的元数据 key。
# 下游 bridge.py 真正会读的只有这三个（bridge.py:434 v2_mode / 435 selected_agent /
# 437-438 parallel_agents）。
# 身份类（user_id / conversation_id）不在其中 —— 它们必须由服务端生成。
CLIENT_META_ALLOWED = ("selected_agent", "v2_mode", "parallel_agents")


class MissingIdentity(Exception):
    """请求没有可用的已认证身份。

    fail-closed 的载体：调用方必须把它转成 401，而不是退回到某个兜底身份。
    """


@dataclass(frozen=True)
class RequestIdentity:
    """一次请求的最终身份与元数据。"""

    user_id: str
    conversation_id: str
    client_metadata: Dict[str, Any]
    metadata: Dict[str, Any]


def token_subject_id(token_user: Any) -> str:
    """从**已验证**的 token 主体取 user_id。取不到返回 ""（不猜、不兜底）。"""
    if not token_user:
        return ""
    if isinstance(token_user, Mapping):
        raw = (
            token_user.get("id")
            or token_user.get("user_id")
            or token_user.get("uid")
            or ""
        )
    else:
        raw = (
            getattr(token_user, "id", None)
            or getattr(token_user, "user_id", None)
            or getattr(token_user, "uid", None)
            or ""
        )
    return str(raw).strip()


def client_metadata_from_body(body: Any) -> Dict[str, Any]:
    """客户端自带的元数据（未过滤）。"""
    if not isinstance(body, Mapping):
        return {}
    raw = body.get("metadata")
    out: Dict[str, Any] = dict(raw) if isinstance(raw, Mapping) else {}
    # body 顶层的 selected_agent 同样是客户端可控输入，原实现也一并收进来
    top_agent = body.get("selected_agent")
    if top_agent:
        out["selected_agent"] = top_agent
    return out


def _allowlisted(meta: Dict[str, Any]) -> Dict[str, Any]:
    """只保留白名单 key。

    身份类 key（user_id / conversation_id）不在白名单里 → 天然被丢弃。
    白名单比黑名单的根本优势在这里：黑名单要穷举危险输入（无穷），
    白名单只列安全输入（有限），新增下游字段时默认进不来。
    """
    return {k: v for k, v in meta.items() if k in CLIENT_META_ALLOWED}


def resolve_request_identity(
    token_user: Any,
    body: Any,
    conversation_id: str = "",
) -> RequestIdentity:
    """解析一次请求的身份与元数据。

    修复要点
    --------
    1. **身份只来自 token** —— 请求体里的任何东西都不能影响它
    2. **没有已认证身份就抛 MissingIdentity**（fail-closed），不退回任何兜底身份
    3. **客户端元数据只放行白名单 key**
    4. **服务端字段最后写入** —— 即使白名单漏了，客户端也覆盖不掉

    第 4 条是纵深防御：前三条任一被绕过，第 4 条仍然拦住。
    """
    body = body if isinstance(body, Mapping) else {}
    token_uid = token_subject_id(token_user)
    if not token_uid:
        # fail-closed：宁可拒绝，也不能落到 "default_user" 或任何全局兜底
        # （退到兜底身份 = 用别人的数据回答 = 静默的越权）
        raise MissingIdentity(
            "请求没有已认证身份（token 主体缺失或不含 user_id），拒绝服务"
        )

    user_id = token_uid

    client_meta = _allowlisted(client_metadata_from_body(body))

    # 服务端字段**最后**写：客户端字段在前，无法覆盖
    metadata = {
        **client_meta,
        "conversation_id": conversation_id,
        "user_id": user_id,
    }

    return RequestIdentity(
        user_id=user_id,
        conversation_id=conversation_id,
        client_metadata=client_meta,
        metadata=metadata,
    )
