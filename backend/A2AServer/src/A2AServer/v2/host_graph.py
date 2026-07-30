"""
PHA v2 HostGraph - 编排器（阶段3）

**作用**：替代 `adk_host_manager.py` 的 3 层 if/else 路由，改为 LangGraph 1.0 显式 `StateGraph`

**节点设计**：
- classify    : 第 1 层路由 - 检查 metadata.selected_agent
- route       : 第 2 层路由 - 关键词启发 + LLM 委派（合二为一的图节点）
- invoke_X    : 4 个子 Agent 调用节点
- aggregate   : 汇总结果
- error       : 错误处理

**边设计**：
- START -> classify
- classify -> route（如果需要更智能的判断）
- route -> invoke_health | invoke_records | invoke_medication | invoke_summary
- invoke_X -> aggregate
- aggregate -> END
- any -> error -> END

**优势**：
- 路由决策可观测（LangSmith 自动 trace）
- 状态可恢复（PostgresSaver）
- 业务改动零侵入（v1 adk_host_manager 仍可工作）
"""
from __future__ import annotations

import logging
import os
from typing import AsyncIterable, Any, Literal, Optional

logger = logging.getLogger(__name__)

# ---- LangGraph 1.0 探测 ----
_LANGGRAPH_OK = False
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver
    _LANGGRAPH_OK = True
except ImportError as e:
    logger.warning("[host_graph] LangGraph 不可用: %s", e)


# ============================================================
# 状态定义：路由决策 + 子 Agent 输出
# ============================================================
from typing import TypedDict, Optional, List, Any


class HostState(TypedDict, total=False):
    """
    PHA HostGraph 状态（TypedDict，LangGraph 1.0 标准）

    字段：
    - query: 用户原始 query
    - conversation_id: 会话 ID
    - user_id: 用户 ID
    - metadata: 消息元数据（selected_agent 等）
    - target_agent: 路由决策结果
    - routing_layer: 命中哪一层
    - agent_response: 子 Agent 输出
    - final_response: 汇总后的最终响应
    - error: 错误信息
    - events: 路由事件流
    - mode: 执行模式（single | multi）阶段30新增
    - parallel_agents: 阶段30新增，多 agent 并行列表
    - parallel_responses: 阶段30新增，每个 agent 的响应
    - parallel_status: 阶段30新增，每个 agent 状态
    - parallel_started_at: 阶段30新增，每个 agent 开始时间
    - parallel_finished_at: 阶段30新增，每个 agent 完成时间
    """
    query: str
    conversation_id: str
    user_id: str
    metadata: dict
    target_agent: str
    routing_layer: int
    agent_response: dict
    final_response: dict
    error: str
    events: List[dict]
    # === 阶段30：多 agent 并行 ===
    mode: str
    parallel_agents: List[str]
    parallel_responses: dict
    parallel_status: dict
    parallel_started_at: dict
    parallel_finished_at: dict
    # === 阶段30-2：每 agent 独立字段（避免 LangGraph 并行写冲突）===
    worker_health_advisor_response: dict
    worker_health_advisor_status: str
    worker_health_advisor_finished_at: float
    worker_health_records_response: dict
    worker_health_records_status: str
    worker_health_records_finished_at: float
    worker_medication_reminder_response: dict
    worker_medication_reminder_status: str
    worker_medication_reminder_finished_at: float
    worker_visit_summary_response: dict
    worker_visit_summary_status: str
    worker_visit_summary_finished_at: float


def _get_query(state) -> str:
    return state.get("query", "") if hasattr(state, "get") else state["query"]


def _get_target(state) -> Optional[str]:
    return state.get("target_agent") if hasattr(state, "get") else state.get("target_agent")


# ============================================================
# Agent 名称映射（与 adk_host_manager.py 保持一致）
# ============================================================
AGENT_ALIAS = {
    # 健康顾问
    "健康顾问": "health_advisor",
    "health_advisor": "health_advisor",
    # 健康档案
    "健康档案": "health_records",
    "健康档案管理员": "health_records",
    "健康档案管理": "health_records",
    "档案管理员": "health_records",
    "health_records": "health_records",
    # 用药提醒
    "用药提醒": "medication_reminder",
    "用药提醒助手": "medication_reminder",
    "medication_reminder": "medication_reminder",
    # 就诊摘要
    "就诊摘要": "visit_summary",
    "就诊摘要生成器": "visit_summary",
    "就诊摘要生成": "visit_summary",
    "就诊摘要助手": "visit_summary",
    "visit_summary": "visit_summary",
}

# 关键词 → Agent 映射（阶段31 改为动态从 AgentRegistry 拼）
# 保留 HEURISTIC_KEYWORDS 仅为向后兼容
HEURISTIC_KEYWORDS = {
    "visit_summary": ["摘要", "总结", "就诊", "summary"],
    "medication_reminder": ["药", "吃药", "提醒", "medication", "服药", "用药", "剂量"],
    "health_records": ["体检", "报告", "record", "检查单", "上传档案", "录入档案"],
    "health_advisor": [
        "头疼", "发烧", "痛", "医生", "建议", "咨询", "症状", "不舒服", "难受",
        "health", "symptom", "咳嗽", "感冒", "头晕", "头痛",
        "档案", "健康档案", "有哪些档案", "查档案", "看档案",
    ],
}


def _build_heuristic_keywords():
    """阶段31：从 AgentRegistry 动态拼关键词表"""
    try:
        from .agent_registry import discover_agents
        specs = discover_agents()
        return {s.name: list(s.keywords) for s in specs if s.keywords}
    except Exception as e:
        logger.warning("[host_graph] _build_heuristic_keywords failed: %s, fallback to static", e)
        return HEURISTIC_KEYWORDS


# ============================================================
# 路由函数（替代 if/else）
# ============================================================
def _layer1_metadata(state: HostState) -> str:
    """第 1 层：检查 metadata.selected_agent（阶段31 支持 registry alias 自动映射）"""
    metadata = state.get("metadata") or {}
    selected = metadata.get("selected_agent")
    if isinstance(selected, str) and selected.strip():
        name = selected.strip()
        # 阶段31：先查静态 AGENT_ALIAS，再查 AgentRegistry.by_alias
        canonical = AGENT_ALIAS.get(name, name)
        # 阶段31：如果 AGENT_ALIAS 没命中，尝试通过 alias 找
        if canonical == name:
            try:
                from .agent_registry import AgentRegistry
                spec = AgentRegistry.by_alias(name)
                if spec is not None:
                    canonical = spec.name
            except Exception:
                pass
        # 校验是否是注册过的 agent
        try:
            from .agent_registry import AgentRegistry
            if AgentRegistry.get(canonical) is not None:
                state["target_agent"] = canonical
                state["routing_layer"] = 1
                state.setdefault("events", []).append({
                    "type": "route",
                    "layer": 1,
                    "reason": f"metadata.selected_agent={selected}",
                    "target": canonical,
                })
                logger.info("[host_graph] layer1 metadata: %s -> %s", selected, canonical)
                return canonical
        except Exception:
            # fallback 到 hardcode 校验（向后兼容）
            if canonical in {"health_advisor", "health_records", "medication_reminder", "visit_summary"}:
                state["target_agent"] = canonical
                state["routing_layer"] = 1
                state.setdefault("events", []).append({
                    "type": "route",
                    "layer": 1,
                    "reason": f"metadata.selected_agent={selected}",
                    "target": canonical,
                })
                logger.info("[host_graph] layer1 metadata: %s -> %s", selected, canonical)
                return canonical
    return ""  # 未命中


def _layer2_heuristic(state: HostState) -> str:
    """第 2 层：关键词启发（阶段31 动态从 AgentRegistry 拼）"""
    text = (state.get("query") or "").lower()
    keywords_map = _build_heuristic_keywords()
    for agent_name, keywords in keywords_map.items():
        if any(kw in text for kw in keywords):
            state["target_agent"] = agent_name
            state["routing_layer"] = 2
            state.setdefault("events", []).append({
                "type": "route",
                "layer": 2,
                "reason": f"keyword match: {[k for k in keywords if k in text]}",
                "target": agent_name,
            })
            logger.info("[host_graph] layer2 heuristic: text=%s -> %s", text[:30], agent_name)
            return agent_name
    return ""


async def _layer3_llm(state: HostState) -> str:
    """第 3 层：LLM 委派（用 DeepSeek/ChatModel 决策）"""
    if not _LANGGRAPH_OK:
        # 无 LangGraph 时默认到健康顾问
        state["target_agent"] = "health_advisor"
        state["routing_layer"] = 3
        state.setdefault("events", []).append({
            "type": "route",
            "layer": 3,
            "reason": "fallback (no langgraph)",
            "target": "health_advisor",
        })
        return "health_advisor"

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=os.getenv("PHA_LLM_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0,
        )

        prompt = f"""你是 PHA 多智能体路由决策器。

可选 Agent：
- health_advisor: 健康顾问，处理症状咨询、健康教育、疾病分析
- health_records: 健康档案管理员，处理检查报告、档案查询
- medication_reminder: 用药提醒助手，处理药品、服药通知
- visit_summary: 就诊摘要生成器，处理就诊记录、就诊总结

用户问题：{state.get('query', '')}

请只回复 4 个 Agent 名称之一，不要解释。"""

        from langchain_core.messages import HumanMessage
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        target = (result.content or "").strip().lower()

        # 校验返回
        if target in {"health_advisor", "health_records", "medication_reminder", "visit_summary"}:
            state["target_agent"] = target
            state["routing_layer"] = 3
            state.setdefault("events", []).append({
                "type": "route",
                "layer": 3,
                "reason": "llm decision",
                "target": target,
            })
            logger.info("[host_graph] layer3 llm: %s", target)
            return target
    except Exception as e:
        logger.warning("[host_graph] layer3 LLM 失败: %s", e)

    # LLM 失败默认到健康顾问
    state["target_agent"] = "health_advisor"
    state["routing_layer"] = 3
    state.setdefault("events", []).append({
        "type": "route",
        "layer": 3,
        "reason": "fallback after LLM failure",
        "target": "health_advisor",
    })
    return "health_advisor"


# ============================================================
# 图节点
# ============================================================
async def classify_node(state: HostState) -> dict:
    """
    分类节点：3 层路由（合并 layer1 + layer2 + layer3）
    返回 dict 更新 state
    """
    state.setdefault("events", [])

    # 第 1 层
    if _layer1_metadata(state):
        return {"target_agent": state["target_agent"], "routing_layer": 1}

    # 第 2 层
    if _layer2_heuristic(state):
        return {"target_agent": state["target_agent"], "routing_layer": 2}

    # 第 3 层
    await _layer3_llm(state)
    return {"target_agent": state["target_agent"], "routing_layer": 3}


def invoke_agent_node(agent_name: str):
    """
    工厂函数：生成 invoke_<agent_name> 节点

    阶段30：支持 single + multi 模式
    - single: 写到 agent_response（向后兼容）
    - multi: 写到 parallel_responses[agent_name]
    """
    import time as _time

    async def node(state: HostState) -> dict:
        started_at = _time.time()
        try:
            # 阶段31：用 AgentRegistry 自动发现，不再 hardcode 4 个 class
            from .agent_registry import AgentRegistry
            from .v2_runtime import get_runtime

            spec = AgentRegistry.get(agent_name)
            if spec is None or spec.cls is None:
                return {"error": f"unknown agent: {agent_name}"}
            agent_cls = spec.cls

            if not get_runtime().available:
                return {"error": "LangChain 1.x 不可用"}

            agent = agent_cls()
            events = []
            full_content = ""
            tool_calls = []

            async for event in agent.stream(
                state.get("query", ""),
                state.get("conversation_id", "default"),
                user_id=state.get("user_id"),
            ):
                events.append(event)
                ev_type = event.get("type", "?")
                if ev_type == "normal":
                    full_content += str(event.get("content", ""))
                elif ev_type == "tool_call":
                    tool_calls.append({
                        "name": event.get("name"),
                        "args": event.get("args"),
                    })

            finished_at = _time.time()
            agent_response = {
                "agent": agent_name,
                "content": full_content,
                "tool_calls": tool_calls,
                "events_count": len(events),
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_ms": int((finished_at - started_at) * 1000),
                "status": "completed",
            }

            mode = state.get("mode", "single")
            if mode == "multi":
                # 多 agent 并行模式：每个 node 写到自己的独立字段
                # LangGraph 1.x 并行 node 不能写同一个 top-level key
                prefix = f"worker_{agent_name}"
                return {
                    f"{prefix}_response": agent_response,
                    f"{prefix}_status": "completed",
                    f"{prefix}_finished_at": finished_at,
                }
            else:
                # 单 agent 模式：写到 agent_response
                return {"agent_response": agent_response}
        except Exception as e:
            logger.exception("[host_graph] invoke_%s failed", agent_name)
            finished_at = _time.time()
            mode = state.get("mode", "single")
            error_resp = {
                "agent": agent_name,
                "content": "",
                "tool_calls": [],
                "events_count": 0,
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_ms": int((finished_at - started_at) * 1000),
                "status": "failed",
                "error": str(e),
            }
            if mode == "multi":
                prefix = f"worker_{agent_name}"
                return {
                    f"{prefix}_response": error_resp,
                    f"{prefix}_status": "failed",
                    f"{prefix}_finished_at": finished_at,
                }
            else:
                return {"agent_response": error_resp, "error": str(e)}

    return node


async def aggregate_node(state: HostState) -> dict:
    """汇总节点：把 agent_response 包装成 final_response"""
    if state.get("error"):
        return {
            "final_response": {
                "role": "agent",
                "content": f"处理失败：{state['error']}",
                "agent": state.get("target_agent"),
                "error": True,
            }
        }

    agent_resp = state.get("agent_response", {})
    return {
        "final_response": {
            "role": "agent",
            "content": agent_resp.get("content", ""),
            "agent": agent_resp.get("agent"),
            "tool_calls": agent_resp.get("tool_calls", []),
            "routing": {
                "layer": state.get("routing_layer"),
                "target": state.get("target_agent"),
            },
        }
    }


async def aggregate_multi_node(state: HostState) -> dict:
    """
    阶段30新增：多 agent 并行汇总节点

    等所有 parallel_agents 都完成后，合并它们的结果。
    输出：包含每个 agent 的 content + tool_calls + 状态
    """
    parallel_agents = state.get("parallel_agents", [])

    # 汇总每个 worker 的输出
    combined_content = ""
    all_tool_calls = []
    worker_summaries = []
    parallel_responses = {}
    parallel_status = {}

    for agent_name in parallel_agents:
        prefix = f"worker_{agent_name}"
        resp = state.get(f"{prefix}_response", {})
        status = state.get(f"{prefix}_status", "unknown")
        content = resp.get("content", "")
        tool_calls = resp.get("tool_calls", [])
        elapsed_ms = resp.get("elapsed_ms", 0)
        error = resp.get("error", "")

        parallel_responses[agent_name] = resp
        parallel_status[agent_name] = status

        worker_summaries.append({
            "agent": agent_name,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "tool_calls_count": len(tool_calls),
            "content_len": len(content),
            "error": error,
        })
        all_tool_calls.extend([{**tc, "agent": agent_name} for tc in tool_calls])

        if content:
            combined_content += f"\n【{agent_name}】\n{content}\n"

    if not parallel_responses:
        return {
            "final_response": {
                "role": "agent",
                "content": "没有 worker 返回结果",
                "agent": None,
                "error": True,
            }
        }

    return {
        "final_response": {
            "role": "agent",
            "content": combined_content.strip(),
            "agent": None,
            "tool_calls": all_tool_calls,
            "routing": {
                "mode": "multi",
                "parallel_agents": parallel_agents,
                "worker_summaries": worker_summaries,
            },
            "parallel_responses": parallel_responses,
            "parallel_status": parallel_status,
        }
    }


async def fanout_node(state: HostState) -> dict:
    """
    阶段30新增：fan-out 节点

    把 parallel_agents 列表里所有 agent 标记为 running，并记录开始时间。
    真正的并行执行由 LangGraph 通过多条 invoke_X -> aggregate_multi 边实现。
    """
    import time as _time
    parallel_agents = state.get("parallel_agents", [])
    now = _time.time()
    return {
        "parallel_status": {a: "running" for a in parallel_agents},
        "parallel_started_at": {a: now for a in parallel_agents},
    }


# ============================================================
# 图构建器
# ============================================================
def build_host_graph(*, use_checkpointer: bool = True, mode: str = "single"):
    """
    构建 PHA HostGraph（LangGraph 1.0 StateGraph）

    Args:
        use_checkpointer: 是否启用 checkpointer
        mode: 路由模式
            - "single"（默认）：classify 后只调一个 agent（向后兼容）
            - "multi"：classify 后并行调多个 agent（阶段30新增）

    Returns:
        CompiledStateGraph（如失败返回 None）
    """
    if not _LANGGRAPH_OK:
        logger.warning("[host_graph] LangGraph 不可用，构建失败")
        return None

    # 阶段31：从 AgentRegistry 自动发现所有 agent
    from .agent_registry import discover_agents
    agents = discover_agents()
    if not agents:
        logger.warning("[host_graph] 没有可用 agent")
        return None

    g = StateGraph(HostState)

    # 节点
    g.add_node("classify", classify_node)
    g.add_node("aggregate", aggregate_node)
    # 阶段30新增
    g.add_node("fanout", fanout_node)
    g.add_node("aggregate_multi", aggregate_multi_node)

    # 阶段31：为每个 agent 自动创建 invoke_<name> 节点
    for spec in agents:
        g.add_node(spec.node_name, invoke_agent_node(spec.name))
        logger.debug("[host_graph] added node: %s", spec.node_name)

    # 边
    g.add_edge(START, "classify")

    if mode == "multi":
        # 阶段30：并行模式（自动 fan-out 到所有 agent）
        all_invoke_nodes = [spec.node_name for spec in agents]

        # path 返回 list → LangGraph 自动 fan-out
        def _multi_path(state):
            return all_invoke_nodes

        g.add_conditional_edges("classify", _multi_path)

        # 所有 invoke_X → aggregate_multi
        for node_name in all_invoke_nodes:
            g.add_edge(node_name, "aggregate_multi")
        g.add_edge("aggregate_multi", END)
    else:
        # 原 single 模式（动态从 registry 拼路由表）
        node_by_name = {spec.name: spec.node_name for spec in agents}
        # 默认 fallback 到第一个 agent
        default_node = agents[0].node_name if agents else None

        def _route_decision(state: HostState) -> str:
            target = state.get("target_agent")
            if target and target in node_by_name:
                return node_by_name[target]
            return default_node or END

        # conditional_edges 的 path_map 只需包含所有 invoke_X
        path_map = {spec.node_name: spec.node_name for spec in agents}
        g.add_conditional_edges(
            "classify",
            _route_decision,
            path_map,
        )

        for spec in agents:
            g.add_edge(spec.node_name, "aggregate")
        g.add_edge("aggregate", END)

    # Checkpointer
    checkpointer = None
    if use_checkpointer:
        try:
            checkpointer = InMemorySaver()
        except Exception as e:
            logger.warning("[host_graph] Checkpointer 初始化失败: %s", e)

    return g.compile(checkpointer=checkpointer)


# ============================================================
# 单例 + 便捷调用
# ============================================================
_host_graph = None


def get_host_graph(mode: str = "single"):
    """获取全局 host_graph 单例（懒加载，按 mode 缓存）"""
    global _host_graph, _host_graph_multi
    if mode == "multi":
        if _host_graph_multi is None:
            _host_graph_multi = build_host_graph(use_checkpointer=False, mode="multi")
        return _host_graph_multi
    if _host_graph is None:
        _host_graph = build_host_graph(use_checkpointer=False, mode="single")
    return _host_graph


# 阶段30：多模式单例
_host_graph = None
_host_graph_multi = None


async def route_and_invoke(
    query: str,
    conversation_id: str,
    user_id: str = "default",
    metadata: Optional[dict] = None,
    mode: str = "single",
    parallel_agents: Optional[List[str]] = None,
) -> dict:
    """
    一站式：路由 + 调用 + 汇总

    Args:
        query: 用户原始问题
        conversation_id: 会话 ID
        user_id: 用户 ID
        metadata: 消息元数据
        mode: "single"（默认）或 "multi"（阶段30新增）
        parallel_agents: multi 模式下要并行的 agent 列表（None=全部 4 个）

    Returns:
        final_response dict
    """
    graph = get_host_graph(mode=mode)
    if graph is None:
        return {
            "role": "agent",
            "content": "LangGraph 不可用，V2 HostGraph 已降级",
            "error": True,
        }

    cfg = {"configurable": {"thread_id": f"{user_id}:{conversation_id}"}}

    # multi 模式默认 4 个 agent 全并行
    if mode == "multi" and parallel_agents is None:
        parallel_agents = [
            "health_advisor",
            "health_records",
            "medication_reminder",
            "visit_summary",
        ]

    initial_state = HostState(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        metadata=metadata or {},
        events=[],
        mode=mode,
        parallel_agents=parallel_agents or [],
        parallel_responses={},
        parallel_status={},
        parallel_started_at={},
        parallel_finished_at={},
    )

    try:
        result = await graph.ainvoke(initial_state, config=cfg)
        return result.get("final_response", {"error": "no response"})
    except Exception as e:
        logger.exception("[host_graph] route_and_invoke failed")
        return {
            "role": "agent",
            "content": f"HostGraph 错误：{e}",
            "error": True,
        }
