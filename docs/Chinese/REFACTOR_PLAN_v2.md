# Multi-Intelligence Medical Companion — 重构方案 v2.0

> **版本**：v2.0（全部依赖锁定 2025-Q4 ~ 2026-Q1 最新版）
> **作者**：架构组
> **日期**：2026-03
> **目标**：把项目从"自研 BasicAgent + ADK 调度 + 手写记忆"重构为 **LangChain 1.x + LangGraph 1.x + 官方 A2A SDK + A2A v0.3** 的工业级多智能体平台
> **设计原则**：不破坏现有业务、按层替换、可灰度、可回滚

---

## 附: 子计划索引

| 子计划 | 内容 | 状态 |
|---|---|---|
| [PHACORE_REFACTOR_PLAN.md](./PHACORE_REFACTOR_PLAN.md) | **阶段 48-19**: 把 4 个 agent 重复实现的 OCR / reminder / storage / analysis 抽到统一的 `backend/PhaCore/` 共享库, 消除 66 个 `@mcp.tool()` 工具名重复 | 📝 已立项 (待执行) |

---

## 1. 重构目标

| 维度       | 现状（v1）                                             | 目标（v2）                                                                  |
| ---------- | ------------------------------------------------------ | --------------------------------------------------------------------------- |
| 智能体框架 | 自写 `BasicAgent._build_initial_conversation / stream` | LangChain 1.0 `create_agent` + Middleware                                   |
| 编排调度   | ADK `adk_host_manager.py` 三层 if/else                 | LangGraph 1.0 `StateGraph`（Supervisor 模式）                               |
| Agent 协议 | 手写 JSON-RPC 2.0 + 自定义 Message 格式                | Google A2A v0.3 官方协议 + Python SDK                                       |
| 会话记忆   | `ConversationBufferMemory`（老 LangChain，已弃用）     | LangGraph `PostgresSaver` Checkpointer                                      |
| 长期记忆   | Python 侧手算 cosine 相似度                            | `langchain-postgres` 的 `PGVectorStore`（pgvector 原生 ANN）                |
| 工具集成   | 自写 MCP 客户端 + 10 个手写 provider                   | 官方 `langchain-mcp-adapters` + 各厂商 `langchain-{openai,deepseek,tongyi}` |
| API 网关   | 自写 FastAPI + JWT 透传                                | FastAPI 0.128+ + OAuth2 client_credentials + OPA 策略                       |
| 观测       | print + 分散 log                                       | LangSmith + OpenTelemetry + Langfuse                                        |
| 部署       | docker-compose（部分容器化）                           | docker-compose v2 + uv + multi-stage Docker                                 |

---

## 2. 技术栈选型（2025-12 ~ 2026-03 实际可装版本）

> **所有版本都已联网核实可直接 `pip install`**

### 2.1 AI 框架层

| 组件          | 包名                                 | 锁定版本        | 说明                                              |
| ------------- | ------------------------------------ | --------------- | ------------------------------------------------- |
| Agent 框架    | `langchain`                          | `>=1.2.10,<2.0` | 1.0 主入口 `create_agent`、Middleware、标准内容块 |
| Agent Runtime | `langgraph`                          | `>=1.0.2,<1.1`  | 持久化、中断、Human-in-the-loop                   |
| Checkpoint    | `langgraph-checkpoint-postgres`      | `>=3.0.2,<4.0`  | 替代 `langchain.memory`，生产级持久化             |
| Tool Runtime  | `langchain-mcp-adapters`             | `>=0.1.0`       | MCP 工具→LangChain `BaseTool` 自动转换            |
| Deep Agents   | `langchain` `deepagents` 子包        | `>=1.2.10`      | 复杂长任务规划（替代 Custom ReAct）               |
| 模型-OpenAI   | `langchain-openai`                   | `>=0.3.0`       | OpenAI / 兼容协议（DeepSeek、Tongyi 都支持）      |
| 模型-DeepSeek | `langchain-deepseek`                 | `>=0.1.0`       | 国产模型（可选，与 OpenAI 协议二选一）            |
| 嵌入          | `langchain-openai`                   | 同上            | text-embedding-3-small / 国产 bge-m3              |
| 向量库        | `langchain-postgres` `PGVectorStore` | `>=0.0.15`      | **替代** 旧的 `PGVector`，原生 ANN                |
| 协议          | `a2a-sdk`                            | `>=0.3.0`       | Google A2A v0.3 官方 Python SDK                   |
| 实验跟踪      | `langsmith`                          | `>=0.2.0`       | 替代分散 print/log，tracing                       |

### 2.2 服务层

| 组件             | 包名                   | 锁定版本                                 |
| ---------------- | ---------------------- | ---------------------------------------- |
| Web 框架         | `fastapi`              | `>=0.128.0`                              |
| ASGI             | `uvicorn[standard]`    | `>=0.32.0`                               |
| 数据校验         | `pydantic`             | `>=2.9.0`                                |
| 异步 PG 驱动     | `psycopg[binary,pool]` | `>=3.2.3`                                |
| 异步 PG 异步引擎 | `sqlalchemy[asyncio]`  | `>=2.0.36`                               |
| 缓存             | `redis`                | `>=5.2.0`                                |
| 包管理           | `uv`                   | `>=0.5.0`（替代 pip/poetry，速度快 10x） |

### 2.3 基础设施

| 组件     | 选型                                     |
| -------- | ---------------------------------------- |
| 容器     | Docker 27+ / docker compose v2           |
| 数据库   | PostgreSQL 16 + pgvector 0.7+            |
| 缓存     | Redis 7.2+                               |
| 反向代理 | Caddy 2.8 / Nginx 1.27                   |
| 鉴权     | OAuth2 client_credentials（自建 Issuer） |
| 策略     | OPA（Open Policy Agent）1.0+             |
| 监控     | Prometheus + Grafana + Loki              |
| 链路追踪 | OpenTelemetry 1.27+ + Langfuse 2.x       |
| 部署     | Kubernetes 1.30+ / 单机 docker compose   |

---

## 3. 目标架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (不重构)                          │
│  wechat_mini_program / admin-dashboard                        │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS / OAuth2 JWT
┌───────────────────────────▼──────────────────────────────────┐
│  API Gateway (FastAPI 0.128)                                  │
│   - 统一鉴权 (OAuth2 / JWT 验签)                                │
│   - 限流 / CORS / TraceID 注入                                  │
│   - OpenTelemetry → Langfuse                                  │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  LangServe / LangGraph Runtime                                 │
│   ┌──────────────────────────────────────────────────┐       │
│   │ SupervisorGraph (LangGraph 1.0 StateGraph)        │       │
│   │  Nodes: classify_intent → route → agent → verify  │       │
│   │  Checkpointer: AsyncPostgresSaver                 │       │
│   └──────────────────────────────────────────────────┘       │
└───────────────────────────┬──────────────────────────────────┘
                            │ A2A JSON-RPC v0.3 (HTTP + gRPC)
┌───────────────────────────▼──────────────────────────────────┐
│  Sub-Agents (LangChain 1.0 create_agent)                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│  │ HealthAdvisor│ │ HealthRecords│ │ Medication   │           │
│  │  create_agent│ │  create_agent│ │  create_agent│   ...     │
│  │ + 8 BaseTool │ │ + 6 BaseTool │ │ + 5 BaseTool │           │
│  │  + A2A Server│ │  + A2A Server│ │  + A2A Server│           │
│  └──────────────┘ └──────────────┘ └──────────────┘           │
│  通信: a2a-sdk (官方 Python SDK, A2A v0.3)                   │
│  工具: langchain-mcp-adapters (MCP 工具自动转 BaseTool)       │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  Shared Services                                              │
│   - PostgreSQL 16 + pgvector 0.7   (业务/向量/Checkpoint)    │
│   - Redis 7.2                      (会话缓存/限流)           │
│   - OPA 1.0                        (统一策略)               │
│   - Langfuse 2.x                   (LLM 可观测)              │
│   - Temporal / Inngest             (长任务编排，可选)         │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 关键改造点（与现状一一对应）

### 4.1 智能体推理核心：`BasicAgent` → `langchain.agents.create_agent`

**现状**（`backend/A2AServer/src/A2AServer/agent.py`）：

```python
# 手写 prompt 拼装 + tool loop + 异步生成器
async def stream(self, query, sessionId, user_id, user_parts):
    response_generator = await self.run_inference(...)
    async for chunk in response_generator:
        yield {...}
```

**目标**：

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    SummarizationMiddleware, PIIRedactionMiddleware, HumanInTheLoopMiddleware
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

agent = create_agent(
    model="openai:gpt-4o-mini",          # 1.0 新写法：provider 前缀字符串
    tools=[diagnosis, knowledge, ...],   # 现有 mcpserver/*_tool.py 改造成 BaseTool
    system_prompt="...",
    middleware=[
        PIIRedactionMiddleware(["email", "phone"]),
        SummarizationMiddleware(model=model),
        # HumanInTheLoopMiddleware(interrupt_on={"diagnosis": True}),  # 医疗场景必开
    ],
    checkpointer=AsyncPostgresSaver.from_conn_string(DB_URL),
)

async def stream_reply(user_id, session_id, query):
    cfg = {"configurable": {"thread_id": f"{user_id}:{session_id}"}}
    async for chunk in agent.stream(
        {"messages": [{"role": "user", "content": query}]},
        config=cfg,
        stream_mode="values",
    ):
        yield chunk
```

**收益**：

- 删掉 ~400 行手写代码（`_build_initial_conversation / run_inference / _stream_response_generator`）
- 错误重试、PII 脱敏、上下文压缩**全免费**
- 可观测：每次 LLM 调用自动上报 Langfuse

---

### 4.2 编排调度：`adk_host_manager.py` → LangGraph `StateGraph`

**现状**（`frontend/hostAgentAPI/adk_host_manager.py`）：

```python
# 3 层 if/else：selected_agent → heuristic → LLM
if message.metadata.get('selected_agent'):
    target_agent_name = message.metadata['selected_agent']
elif "头疼" in text_content:
    target_agent_name = "健康顾问"
else:
    async for event in self._host_runner.run_async(...):
        self.add_event(event)
```

**目标**（Supervisor 模式 + 显式状态图）：

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.postgres import PostgresSaver

# 4 个子 Agent 全部用 create_agent 统一
health_agent  = create_agent(model="openai:gpt-4o-mini", tools=health_tools, ...)
records_agent = create_agent(model="openai:gpt-4o-mini", tools=record_tools, ...)
medication    = create_agent(model="openai:gpt-4o-mini", tools=med_tools, ...)
summary       = create_agent(model="openai:gpt-4o-mini", tools=sum_tools, ...)

def build_supervisor():
    g = StateGraph(MessagesState)
    g.add_node("classify", classify_intent_node)
    g.add_node("health",   lambda s: health_agent.invoke(s))
    g.add_node("records",  lambda s: records_agent.invoke(s))
    g.add_node("medication", lambda s: medication.invoke(s))
    g.add_node("summary",  lambda s: summary.invoke(s))
    g.add_node("aggregate", aggregate_node)

    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route, {
        "health": "health", "records": "records",
        "medication": "medication", "summary": "summary",
    })
    for n in ["health", "records", "medication", "summary"]:
        g.add_edge(n, "aggregate")
    g.add_edge("aggregate", END)
    return g.compile(checkpointer=PostgresSaver.from_conn_string(DB_URL))
```

**收益**：

- 路由决策**可观测**（LangSmith 看到每一步走的哪个节点）
- 状态**可恢复**（服务挂了能接着上次执行）
- **可回放**（调试时直接 `get_state_history` 拉过去任意时刻）
- 0 if/else，全是图

---

### 4.3 Agent 协议：手写 JSON-RPC → A2A v0.3 官方 SDK

**现状**：`backend/A2AServer/src/A2AServer/common/`（手写 Pydantic 模型 + 路由）

**目标**：

```python
# 安装：pip install a2a-sdk>=0.3.0
from a2a.server import A2AServer, AgentCard
from a2a.types import Message, Part, TextPart

# 1. 暴露子 Agent 为 A2A 服务（自动符合协议）
card = AgentCard(
    name="health_advisor",
    description="AI 健康顾问",
    url="https://api.example.com/a2a/health-advisor",
    version="1.0",
    skills=[{"id": "diagnose", "name": "健康咨询"}],
    capabilities={"streaming": True, "pushNotifications": True},
)
app = A2AServer(agent_executor=health_executor, agent_card=card).build()

# 2. HostAgent 调用子 Agent（一行）
from a2a.client import A2AClient
client = A2AClient(url="https://api.example.com/a2a/health-advisor")
async for chunk in client.send_message_streaming(
    message=Message(parts=[Part(root=TextPart(text=query))])
):
    yield chunk
```

**收益**：

- **符合 Google A2A v0.3 规范**（gRPC 支持、签名安全卡、扩展客户端）
- 跨语言/跨框架**互操作**（未来接 CrewAI、AutoGen、ADK 都直接通）
- 删掉 `common/server.py / common/client.py`（~600 行）

---

### 4.4 长期记忆：手算 cosine → `langchain-postgres.PGVectorStore`

**现状**（`backend/AgentMemorySystem/memory_retrieval.py:84-127`）：

```python
# Python 侧遍历所有 memory，逐一算 cosine
candidates = await db.fetch("SELECT * FROM memories WHERE agent_id=$1", agent_id)
results = []
for row in candidates:
    sim = cosine_similarity(query_vec, row['embedding'])
    if sim >= 0.5:
        results.append((row, sim))
results.sort(key=lambda x: x[1], reverse=True)
```

**目标**（pgvector 原生 ANN）：

```python
from langchain_postgres import PGVectorStore
from langchain_openai import OpenAIEmbeddings

store = PGVectorStore(
    connection=DB_URL,
    embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
    collection_name="pha_memories",
    use_jsonb=True,         # metadata 走 jsonb，可索引
)

# 检索（数据库侧 ANN，性能 +10x）
docs = await store.asimilarity_search(
    query=memory_query,
    k=8,
    filter={"user_id": "u_001", "agent_id": "health_advisor"},
)

# 写入
await store.aadd_documents(
    [Document(page_content=text, metadata={"user_id": ..., "agent_id": ..., "source": ...})],
    ids=[memory_id],
)
```

**收益**：

- **万级记忆毫秒级**返回（Python 侧遍历要几百 ms）
- 支持 metadata 过滤（`user_id / agent_id / data_classification`）
- **Memory ACL** 走数据库层（医疗合规）

---

### 4.5 工具集成：手写 MCP Client → `langchain-mcp-adapters`

**现状**：`backend/A2AServer/src/A2AServer/mcp_client/`（10 个手写 provider + 通用 client）

**目标**：

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

# 1. 一行连接所有 MCP 服务
mcp_client = MultiServerMCPClient({
    "health_kb":   {"url": "http://localhost:8001/mcp", "transport": "streamable_http"},
    "health_rec":  {"url": "http://localhost:8002/mcp", "transport": "streamable_http"},
    "medication":  {"url": "http://localhost:8003/mcp", "transport": "streamable_http"},
    "summary":     {"url": "http://localhost:8004/mcp", "transport": "streamable_http"},
})
tools = await mcp_client.get_tools()   # 自动转 BaseTool

# 2. 直接当 LangChain 工具用
agent = create_agent(model="openai:gpt-4o-mini", tools=tools, ...)
```

**收益**：

- **0 行 provider 适配代码**（MCP 协议层统一处理）
- 10 个手写 provider → 0
- 自动支持 streamable_http / sse / stdio 三种 transport

---

### 4.6 鉴权：JWT 透传 → OAuth2 + OPA

**现状**：JWT 在网关解析一次，后面 agent-to-agent 全靠透传，**横向越权风险**

**目标**：

- **服务身份**：每个子 Agent 申请 OAuth2 `client_credentials`，发 `service_token`
- **调用链**：`host-agent → svc-token(target=health-advisor, scope=invoke) → health-advisor`
- **策略中心**：OPA（Rego）做 ABAC（"医生角色才能调健康摘要 agent"）
- **审计**：每次调用写 OpenTelemetry span，OpenAPI 兼容

```python
# 服务间调用前申请 token
from authlib.integrations.httpx_client import AsyncOAuth2Client
client = AsyncOAuth2Client(client_id="host-agent", client_secret=..., scope="invoke:health-advisor")
token = await client.fetch_token("https://auth.internal/oauth/token")

# 注入 header
headers = {"Authorization": f"Bearer {token['access_token']}"}
```

---

## 5. 实施路线（4 阶段，每阶段可灰度）

### 阶段 1：基础设施升级（1-2 周，零业务影响）

- [ ] 升级 Python 3.11 → 3.12
- [ ] 引入 `uv` 替代 pip
- [ ] 升级 FastAPI 0.115 → 0.128+
- [ ] 升级 pydantic 2.x、psycopg 3.2+、SQLAlchemy 2.0+
- [ ] 引入 LangSmith / Langfuse 接 OpenTelemetry
- [ ] 写好 `langchain==1.2.10` / `langgraph==1.0.2` 等依赖的 `pyproject.toml`

**验收**：所有现有接口继续工作，trace 上报 Langfuse

---

### 阶段 2：智能体核心替换（2-3 周，灰度）

- [ ] 把 `mcpserver/*_tool.py` 改造成 `BaseTool`（一次性脚本生成）
- [ ] 替换 4 个子 Agent 的入口为 `create_agent`
- [ ] **保留** A2A 协议层（不动 `common/server.py`），子 Agent **同时**接受 A2A 请求 + LangChain 内部调用
- [ ] 用 `langchain-mcp-adapters` 替换手写 `mcp_client/*`
- [ ] 把 `BasicAgent` 留作 fallback，老请求走它，新请求走新 Agent

**验收**：4 个子 Agent 功能等价，新 Agent 通过 A2A 暴露

---

### 阶段 3：编排升级（2-3 周，灰度）

- [ ] HostAgent 用 `StateGraph` 重写
- [ ] 加 Checkpointer（先 InMemory，再换 PostgresSaver）
- [ ] 加 Middleware（PII 脱敏、Summary、Human-in-the-loop）
- [ ] 老的 `adk_host_manager.py` 保留为 v1 路由，新请求走 v2

**验收**：路由可观测、状态可恢复、HITL 工具调用可中断

---

### 阶段 4：协议与生产化（2-4 周，灰度）

- [ ] 引入 `a2a-sdk>=0.3.0` 替换手写协议
- [ ] Agent Card 走 `/.well-known/agent.json`
- [ ] 鉴权升级 OAuth2 + OPA
- [ ] 长期记忆迁移到 `PGVectorStore`（数据迁移脚本 + 灰度切流）
- [ ] 加 Temporal 做长任务编排（异步 OCR、慢病追踪）
- [ ] 完整 CI/CD（uv 锁版本、multi-stage Docker、K8s 部署）

**验收**：所有流量走 v2，老代码全部移除（保留 git tag）

---

## 6. 依赖清单（pyproject.toml 核心部分）

```toml
[project]
name = "pha-multi-agent"
version = "2.0.0"
requires-python = ">=3.12,<3.13"

dependencies = [
  # === AI 框架（v1.0+）===
  "langchain>=1.2.10,<2.0",
  "langgraph>=1.0.2,<1.1",
  "langgraph-checkpoint-postgres>=3.0.2,<4.0",
  "langchain-postgres>=0.0.15",     # PGVectorStore
  "langchain-openai>=0.3.0",
  "langchain-mcp-adapters>=0.1.0",
  "a2a-sdk>=0.3.0",                  # A2A v0.3
  "langsmith>=0.2.0",

  # === Web / 数据 ===
  "fastapi>=0.128.0",
  "uvicorn[standard]>=0.32.0",
  "pydantic>=2.9.0",
  "psycopg[binary,pool]>=3.2.3",
  "sqlalchemy[asyncio]>=2.0.36",
  "redis>=5.2.0",

  # === 鉴权 / 观测 ===
  "authlib>=1.3.2",
  "opentelemetry-api>=1.27.0",
  "opentelemetry-sdk>=1.27.0",
  "opentelemetry-instrumentation-fastapi>=0.48b0",
  "langfuse>=2.0.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "ruff>=0.6.0",
  "mypy>=1.11",
  "langchain-cli>=0.0.30",
]
```

---

## 7. 风险与避坑

| 风险                                      | 缓解                                                             |
| ----------------------------------------- | ---------------------------------------------------------------- |
| LangChain 1.0 还在演进，升级可能 breaking | 锁版本（`>=1.2.10,<2.0`），CI 跑 `pip check`                     |
| MCP 工具太多拖垮推理                      | 工具白名单 + 按角色裁剪（doctor / patient / caregiver）          |
| 长期记忆迁移数据丢失                      | 先并行运行（双写），校验 100% 一致再切流                         |
| A2A 协议 gRPC 在国内网络难调试            | 保留 HTTP+JSON-RPC fallback                                      |
| LangGraph Checkpoint 数据膨胀             | 配置 TTL + 后台清理（参考 `langgraph-checkpoint-postgres` 文档） |
| Human-in-the-loop 阻塞主流程              | 必须配超时 + 自动 reject 策略（医疗场景尤其重要）                |

---

## 8. 不重构的（明确边界）

以下**保持现状**，不在本次重构范围：

- **小程序前端**（`wechat_mini_program`）：UI 逻辑不动
- **Admin Dashboard**（`admin-dashboard`）：React 18 + Vite 不动
- **数据库 schema**（`personal_health_assistant.sql`）：表结构兼容，仅加 pgvector 列
- **部署文件**（`docker-compose.yml`）：保留，阶段 4 改 multi-stage
- **测试用例**（`tests/`）：保留，作为回归基线

---

## 9. 验收指标

| 指标                      | 现状     | 目标                           |
| ------------------------- | -------- | ------------------------------ |
| 代码行数（智能体核心）    | ~1800 行 | <800 行                        |
| LLM 链路 trace 覆盖率     | 0%       | 100%                           |
| 路由决策可回放            | ❌       | ✅                             |
| 智能体间互操作（跨框架）  | ❌       | ✅（A2A v0.3）                 |
| 长期记忆查询延迟（1k 条） | ~300ms   | <50ms                          |
| 状态可恢复（服务重启）    | ❌       | ✅（PostgresSaver）            |
| 平均 LLM token 消耗       | 100%     | 降低 40%（Summary Middleware） |

---

## 10. 引用与权威信息源

- LangChain 1.0 发布说明：<https://blog.langchain.com/langchain-langgraph-1dot0/>
- LangGraph v1.0.3 生产部署指南：<https://github.com/CodeHalwell/AgentGuides/blob/main/LangGraph_Guide/python/langgraph_production_guide.md>
- A2A v0.3 协议规范：<https://a2a-protocol.org/latest/>
- A2A Python SDK：<https://github.com/a2aproject/A2A>
- langchain-postgres：<https://github.com/langchain-ai/langchain-postgres>
- Google Cloud A2A v0.3 公告：<https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade/>

---

**下一步**：阶段 1 启动，预计 1-2 周完成；阶段 2-4 按上述路线推进。
