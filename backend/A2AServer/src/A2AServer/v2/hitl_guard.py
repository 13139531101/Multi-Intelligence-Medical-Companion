# -*- coding: utf-8 -*-
"""
HITL fail-closed 守卫 —— 判定不可用时，危险工具**不交给模型**。

为什么需要这个模块
------------------
HITL（HumanInTheLoop）能不能生效，取决于两件互相独立的事：

  ① **判定器**算得对不对（哪些工具危险）—— v2/dangerous_tools.py
  ② **拦截器**在不在（HumanInTheLoopMiddleware 装上了没）—— v2/v2_runtime.py

两件事都会坏。而坏掉之后的默认行为如果是「照常跑」，
那等于 **判定失效 = 全部危险操作无人确认直接执行**。

修复前的现状（v2_runtime.py 的 HITL 段）：

    except Exception as e:
        logger.debug("[v2_runtime] HumanInTheLoop 不可用: %s", e)

``logger.debug`` 在默认日志级别下**看不见** —— 静默降级 = 静默失守。
这跟 M1 的 ``default_user`` 兜底是同一个错误（fail-open），只是换了马甲。

本模块给出 fail-closed 的具体形态
----------------------------------
    - **HITL 装上了**              → 工具照给，受保护的由 HITL 拦（正常路径）
    - **HITL 没装上，判定器还能用** → **受保护的工具压根不交给模型**
                                   （模型看不见它，就不会调它）
    - **判定器自己也不可用**       → **拒绝启动**（fail-fast）

为什么 fail-closed 是「不给」而不是「拦」
----------------------------------------
HITL 挂不上的时候，「拦住所有危险操作」这个动作本身也不可用了 ——
拦截器就是 HITL。所以 fail-closed 不能实现成「多问一句」，
只能实现成**危险工具不交给模型**。

代价是功能受损，所以降级必须**可见**（logger.error + 状态可查），
否则用户只会说「功能坏了」，不会说「安全了」。

⚠️ 反面提醒：**别走「所有工具都拦」那条路**。
那是审批疲劳 —— 人在场，但闭眼点同意，是 fail-open 的变体。

零依赖：纯标准库，可进 CI 阻塞门禁。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


class HitlUnavailable(RuntimeError):
    """判定器不可用 —— 危险工具集算不出来，必须拒绝启动（fail-fast）。"""


@dataclass(frozen=True)
class HitlStatus:
    """HITL 的落地状态。

    active    —— HumanInTheLoopMiddleware 是否真的装上了
    protected —— 判定器算出的「危险工具」集合（**事实层**）
    reason    —— 降级原因（必须可见、可观测）
    fatal     —— True 表示判定器本身不可用，危险工具集**算不出来**
    """

    active: bool = True
    protected: frozenset = frozenset()
    reason: str = ""
    fatal: bool = False

    @property
    def degraded(self) -> bool:
        """降级了（没装上 HITL），但判定器还在 —— 受保护的工具会被摘掉。"""
        return not self.active and not self.fatal


def tool_name(tool: Any) -> str:
    """取工具名。LangChain 的 BaseTool 有 .name，普通函数用 __name__。"""
    for attr in ("name", "__name__"):
        value = getattr(tool, attr, None)
        if isinstance(value, str) and value:
            return value
    return repr(tool)


def restrict_tools(tools: Sequence[Any], status: HitlStatus):
    """按 HITL 状态决定哪些工具可以交给模型。

    返回 (可用的工具列表, 被摘掉的工具列表)。

    - ``status.active``  → 原样返回（受保护的由 HITL 拦）
    - ``status.fatal``   → 抛 :class:`HitlUnavailable`（拒绝启动）
    - 其它（降级）        → **摘掉受保护的工具**（fail-closed）
    """
    if status.fatal:
        raise HitlUnavailable(
            "HITL 判定不可用，拒绝启动（fail-closed）：%s"
            % (status.reason or "未知原因")
        )
    if status.active:
        return list(tools), []

    protected = status.protected
    kept, removed = [], []
    for tool in tools:
        if tool_name(tool) in protected:
            removed.append(tool)
        else:
            kept.append(tool)
    return kept, removed


__all__ = ["HitlStatus", "HitlUnavailable", "restrict_tools", "tool_name"]
