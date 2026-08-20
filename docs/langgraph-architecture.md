# PHA v2 LangGraph 架构文档

## 现状（阶段48-A2A）

**已有大量 LangGraph 基础设施，不需要从头构建：**

| 组件 | 文件 | 状态 |
|------|------|------|
| `StateGraph` + `HostState` | `v2/host_graph.py` | ✅ 已有 |
| `V2Agent` 基类 | `v2/v2_agent.py` | ✅ 已有 |
| 3层路由 | `v2/host_graph.py` | ✅ 已有 |
| Magentic RAG | `v2/magnetic_rag.py` | ✅ 已有 |
| ReAct Critique | `v2/react_critique.py` | ✅ 已有 |
| ANP RPC + DID | `v2/anp_bridge.py`, `did_wba.py` | ✅ 已有 |
| Checkpoint (InMemory) | `langgraph.checkpoint.memory` | ✅ 已有 |
| 流式输出 | `V2Agent.stream()` | ✅ 已有 |

**真正缺的部分（待改）：**

| 问题 | 说明 |
|------|------|
| Sub-agent 还是 BasicAgent | `forward_to_a2a` 是存根，没调用 V2Agent |
| ANP → V2Agent 未打通 | `/anp/agent/rpc` 收请求但没调用 agent |
| Sub-agent 不是 LangGraph | 只有 hostapi 用 host_graph，sub-agent 没有 |

---

## 目标架构

```
                    ┌─────────────────────────┐
                    │  用户请求                 │
                    │  (前端 → hostapi:13002) │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼───────────────┐
                    │   host_graph (LangGraph)  │
                    │                           │
                    │ classify → clarify        │
                    │   → rag_retrieve          │
                    │   → invoke (LLM 路由)     │
                    │   → critique (反思)       │
                    │   → aggregate             │
                    └───────────┬───────────────┘
                                │ ANP RPC
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
  │ health_records│     │ medication_   │     │ visit_summary │
  │ V2Agent       │◄───►│  V2Agent      │◄───►│ V2Agent       │
  │ (LangGraph)   │     │  (LangGraph)  │     │ (LangGraph)   │
  └───────────────┘     └───────────────┘     └───────────────┘
```

---

## 改造计划

### Phase 1: Sub-agent V2Agent 化

**目标：** BasicAgent → V2Agent，sub-agent 内部变成 LangGraph

每个 sub-agent 的 `main.py` 中：
```python
# 旧：BasicAgent
agent = BasicAgent(config_path=mcp_config, ...)

# 新：V2Agent
from A2AServer.v2.v2_agent import V2Agent

class HealthAdvisorV2(V2Agent):
    name = "health_advisor"
    system_prompt = "你是专业健康顾问..."

    def get_tools(self):
        return [mcp_tool_1, mcp_tool_2, ...]
```

### Phase 2: ANP → V2Agent 打通

**目标：** `forward_to_a2a` 真正调用 `agent.stream()`

```python
# main.py ANP handler
async def anp_rpc(request: Request):
    body = await request.json()
    task = body.get("params", {}).get("task", {})
    query = task.get("message", {}).get("parts", [{}])[0].get("text", "")
    user_id = params.get("user_id", "anonymous")

    # 真正调用 V2Agent.stream()
    result_parts = []
    async for chunk in agent.stream(query, session_id, user_id):
        if chunk.get("content"):
            result_parts.append({"type": "text", "text": chunk["content"]})

    return JSONResponse({
        "result": {
            "status": "ok",
            "parts": result_parts,
            "is_task_complete": True,
        }
    })
```

### Phase 3: Supervisor 增强

**目标：** host_graph 增加更复杂的路由逻辑、多 agent 协作

改进 `classify_node` 和 `route_decision`，让 LLM 真正做路由决定而非简单 if-else。

---

## V2Agent vs BasicAgent 对比

| | BasicAgent | V2Agent |
|---|---|---|
| 框架 | 手写 ReAct 循环 | LangChain `create_agent` |
| 流式 | yield 手写格式 | 标准化 chunk |
| 工具调用 | 手动处理 | Middleware 自动处理 |
| 单例缓存 | 无 | 类级别 `_agent_instance_cache` |
| 状态管理 | session dict | LangGraph state |

---

## V2Agent 使用示例

```python
from A2AServer.v2.v2_agent import V2Agent
from langchain_core.tools import tool

@tool
def get_health_records(user_id: str) -> str:
    """查健康档案"""
    ...

class HealthAdvisorV2(V2Agent):
    name = "health_advisor"
    system_prompt = "你是一个专业、严谨的健康顾问..."

    def get_tools(self):
        return [get_health_records]

# 使用
agent = HealthAdvisorV2()
async for event in agent.stream("我有头疼", session_id, user_id):
    print(event)
    # {"is_task_complete": False, "content": "...", "type": "normal"}
```

---

## 依赖

```bash
pip install langgraph langchain-core langchain-openai
```
