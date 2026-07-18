"""阶段48-13: user_id 注入中间件.

LangChain 1.0 create_agent 支持 middleware 列表.
我们在 `tools_to_call` / `before_tool_call` 钩子里
如果 LLM 没传 user_id, 自动从 runtime context 注入.

runtime context 通过 V2Agent.stream(user_id=...) 传入.
"""
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware


class UserIdInjectionMiddleware(AgentMiddleware):
    """阶段48-13: 自动给 tool 调用注入 user_id 字段.

    LangChain 1.0 API:
      - AgentMiddleware.tools_to_call(state, runtime): 可改写要调用的工具集
      - before_tool_call(state, runtime): 在 tool 真的被 invoke 前 return ToolCall

    我们实际只关心 LLM 没传 user_id 的情况 — 这时我们改写 tool call args
    注入 runtime context 中的 user_id.
    """

    def __init__(self, user_id_provider: Callable[[], str] = None):
        """user_id_provider: 函数, 返回当前 user_id."""
        self._get_user_id = user_id_provider or (lambda: "")

    @property
    def name(self) -> str:
        return "user_id_injection"

    def before_tool_call(self, tool_call, runtime):  # noqa: ANN001
        """tool_call 是 dict: {"name": ..., "args": ..., "id": ...}."""
        try:
            args = tool_call.get("args") or {}
            if not isinstance(args, dict):
                # 有些模型给的是 JSON string
                import json
                try:
                    args = json.loads(args) if args else {}
                except Exception:
                    args = {}

            if "user_id" not in args or args.get("user_id") in (None, ""):
                uid = self._get_user_id()
                if uid:
                    new_args = dict(args)
                    new_args["user_id"] = uid
                    # return 类型可能是 ToolCall 或 None
                    return {**tool_call, "args": new_args}
        except Exception:
            pass
        return tool_call
