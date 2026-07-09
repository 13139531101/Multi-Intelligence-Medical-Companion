"""
PHA v2 智能体基类（V2Agent）

**作用**：
- 替代 `BasicAgent.stream()` 的核心逻辑
- 基于 LangChain 1.0 `create_agent` + Middleware
- 保持与 BasicAgent **完全一致**的流式输出格式（兼容 A2A 协议）

**差异**：
- BasicAgent 内部用 _build_initial_conversation + _stream_response_generator 手写循环
- V2Agent 内部用 create_agent 标准化 + Middleware 自动处理

**向后兼容**：
- 如果 LangChain 1.x 不可用，V2Agent.stream() 会自动降级返回错误事件
- BasicAgent 仍可继续工作
"""
from __future__ import annotations

import logging
import os
from typing import AsyncIterable, Any

from .v2_runtime import get_runtime

logger = logging.getLogger(__name__)


class V2Agent:
    """
    PHA v2 智能体基类

    用法：
        class HealthAdvisorV2(V2Agent):
            name = "health_advisor"
            system_prompt = "你是健康顾问..."

            def get_tools(self):
                return [diagnosis_tool, knowledge_tool, ...]

        agent = HealthAdvisorV2()
        async for event in agent.stream(query, session_id, user_id):
            print(event)
    """

    name: str = "v2_agent"
    system_prompt: str = "You are a helpful AI assistant."

    def __init__(self, model: str | None = None):
        # 自动识别 LLM 提供方：DeepSeek（默认）/ OpenAI / 其它
        if model is None:
            if os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_BASE"):
                # DeepSeek（OpenAI 兼容协议）
                self.model = os.getenv("PHA_LLM_MODEL", "deepseek-chat")
            else:
                self.model = os.getenv("PHA_LLM_MODEL", "openai:gpt-4o-mini")
        else:
            self.model = model
        self._agent = None
        self._tools = None

    def get_tools(self) -> list:
        """子类重写：返回 LangChain BaseTool 列表"""
        return []

    async def _ensure_agent(self):
        """懒加载：第一次调用时创建 agent"""
        if self._agent is not None:
            return self._agent

        runtime = get_runtime()
        if not runtime.available:
            return None

        # 延迟导入 LangChain 1.x（确保失败时不阻塞）
        from langchain.agents import create_agent
        from langchain.chat_models import init_chat_model

        self._tools = self.get_tools()
        checkpointer = await runtime.get_checkpointer()
        middlewares = runtime.get_middlewares(self.model)

        # DeepSeek / 自定义 endpoint：用 ChatOpenAI + base_url
        # DeepSeek 兼容 OpenAI 协议，不需要 langchain-deepseek 单独包
        if self.model.startswith("deepseek"):
            from langchain_openai import ChatOpenAI

            chat_model = ChatOpenAI(
                model=self.model,
                api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                temperature=0,
            )
            self._agent = create_agent(
                model=chat_model,
                tools=self._tools,
                system_prompt=self.system_prompt,
                middleware=middlewares,
                checkpointer=checkpointer,
            )
        elif self.model.startswith("openai:"):
            from langchain_openai import ChatOpenAI

            model_name = self.model.split(":", 1)[1]
            chat_model = ChatOpenAI(
                model=model_name,
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_API_BASE"),  # None 默认 OpenAI 官方
                temperature=0,
            )
            self._agent = create_agent(
                model=chat_model,
                tools=self._tools,
                system_prompt=self.system_prompt,
                middleware=middlewares,
                checkpointer=checkpointer,
            )
        else:
            # 其它直接走 create_agent(model=str) 路径
            self._agent = create_agent(
                model=self.model,
                tools=self._tools,
                system_prompt=self.system_prompt,
                middleware=middlewares,
                checkpointer=checkpointer,
            )

        logger.info(
            "[v2_agent:%s] created: model=%s, tools=%d, middlewares=%d",
            self.name,
            self.model,
            len(self._tools),
            len(middlewares),
        )
        return self._agent

    async def stream(
        self,
        query: str,
        session_id: str,
        user_id: str | None = None,
        user_parts: list | None = None,
    ) -> AsyncIterable[dict[str, Any]]:
        """
        流式推理（与 BasicAgent.stream 保持相同事件格式）

        输出事件类型：
        - {"type": "status", "content": "Processing request..."}
        - {"type": "reasoning", "content": "..."}
        - {"type": "normal", "content": "..."}
        - {"type": "tool_call", "name": "...", "args": {...}}
        - {"type": "tool_result", "name": "...", "output": "..."}
        - {"type": "complete", "content": " "}
        - {"type": "error", "content": "...", "require_user_input": True}
        """
        agent = await self._ensure_agent()
        if agent is None:
            yield {
                "type": "error",
                "content": "LangChain 1.x 不可用，V2Agent 已降级。请安装 langchain>=1.2.10",
                "require_user_input": True,
            }
            return

        # 起始事件（与 BasicAgent 兼容）
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "updates": "Processing request...",
        }

        # thread_id = user_id:session_id（隔离多用户多会话）
        thread_id = f"{user_id or 'anon'}:{session_id}"
        cfg = {"configurable": {"thread_id": thread_id}}

        try:
            # LangGraph 1.0：stream() 在 stream_mode="values" 下是同步生成器
            # 用同步 iter 包一层（不影响异步语义）
            stream_iter = agent.stream(
                {"messages": [{"role": "user", "content": query}]},
                config=cfg,
                stream_mode="values",
            )

            for chunk in stream_iter:
                messages = chunk.get("messages", []) if isinstance(chunk, dict) else []
                for msg in messages:
                    msg_type = getattr(msg, "type", "ai")
                    content = getattr(msg, "content", "")
                    tool_calls = getattr(msg, "tool_calls", []) or []

                    # 工具调用
                    for tc in tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        }

                    # 文本输出
                    if content:
                        if msg_type == "ai":
                            yield {
                                "is_task_complete": False,
                                "require_user_input": False,
                                "content": content,
                                "type": "normal",
                            }
                        elif msg_type == "tool":
                            yield {
                                "type": "tool_result",
                                "name": getattr(msg, "name", ""),
                                "output": str(content)[:500],
                            }

            # 结束事件
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": " ",
                "type": "normal",
            }

        except Exception as e:
            logger.exception("[v2_agent:%s] stream error", self.name)
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "updates": f"Error processing request: {str(e)}",
            }
