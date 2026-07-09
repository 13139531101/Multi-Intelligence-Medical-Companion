# PHA v2 架构总览

> **版本**：v2.0.0
> **更新时间**：2026-07
> **状态**：✅ 5 阶段全部完成，9 个 tag 推送完成

---

## 1. 什么是 PHA v2？

**PHA (Personal Health Assistant)** 是一个基于多智能体的个人健康助理系统。**v2** 是对 v1 的**完整重构**，从以下三个维度升级：

| 维度 | v1 | v2 |
|------|----|----|
| 智能体框架 | 手写 `BasicAgent` (1800 行) | LangChain 1.0 `create_agent` |
| 编排 | 3 层 `if/else` 路由 | LangGraph 1.0 `StateGraph` |
| 工具接入 | 18 个 MCP 工具 | **36 个真实 MCP 工具** |
| LLM 兼容 | 仅 DeepSeek | DeepSeek / OpenAI / 国产 V4 |
| 状态管理 | 内存 | InMemorySaver / PostgresSaver |
| 协议 | 私有 | **a2a-sdk 0.3.x 标准 JSON-RPC 2.0** |
| 可观测 | log | LangSmith / Langfuse / OTel |

**业务能力**不变，**技术栈**全部升级。

---

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 / 小程序                            │
│                  (Web + WeChat Mini Program)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   hostAgentAPI (FastAPI) :10010                  │
│                                                                  │
│   _send_message() 入口                                          │
│   ┌────────────────────────────────────────────────┐             │
│   │ Header X-Use-V2=true / X-PHA-Version=v2?       │             │
│   │ 环境变量 PHA_USE_V2=true?                      │             │
│   └────────────────────────────────────────────────┘             │
│           │                                       │              │
│          YES                                      NO              │
│           ▼                                       ▼              │
│   ┌──────────────────────┐              ┌────────────────────┐  │
│   │ v2_bridge.py         │              │ adk_host_manager   │  │
│   │ v2_process_message() │              │ (v1, fallback)     │  │
│   └──────────┬───────────┘              └─────────┬──────────┘  │
│              │                                    │             │
└──────────────┼────────────────────────────────────┼─────────────┘
               │                                    │
               ▼                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                  PHA v2 HostGraph (LangGraph 1.0)              │
│                                                                  │
│   ┌──────────┐    ┌──────────────────────────────────┐          │
│   │  START   │ -> │  classify_node (3 层路由)        │          │
│   └──────────┘    │  Layer 1: metadata.selected_agent │          │
│                   │  Layer 2: 关键词启发              │          │
│                   │  Layer 3: LLM 委派 (DeepSeek)     │          │
│                   └──────────┬───────────────────────┘          │
│                              │                                   │
│            ┌─────────────────┼─────────────────┐                │
│            ▼                 ▼                 ▼                │
│     ┌──────────┐      ┌──────────┐      ┌──────────┐           │
│     │ invoke   │      │ invoke   │      │ invoke   │           │
│     │ _health  │      │ _records │      │ _med     │           │
│     └─────┬────┘      └─────┬────┘      └────┬─────┘           │
│           │                 │                │                  │
│     ┌──────────┐      ┌──────────┐      ┌──────────┐           │
│     │ invoke   │      │          │      │          │           │
│     │ _summary │      │          │      │          │           │
│     └─────┬────┘      └──────────┘      └──────────┘           │
│           │                                                     │
│           ▼                                                     │
│     ┌──────────┐                                                │
│     │aggregate │ -> final_response                              │
│     └──────────┘                                                │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              V2Agent (LangChain 1.0 create_agent)              │
│                                                                  │
│   ┌────────────────────────────────────────────────────┐        │
│   │  HealthAdvisorV2       (DeepSeek + 11 MCP 工具)   │        │
│   │  HealthRecordsV2       (DeepSeek + 11 MCP 工具)   │        │
│   │  MedicationReminderV2  (DeepSeek +  8 MCP 工具)   │        │
│   │  VisitSummaryV2        (DeepSeek +  6 MCP 工具)   │        │
│   └────────────────────────────────────────────────────┘        │
│                                                                  │
│   模型: ChatOpenAI + base_url=https://api.deepseek.com         │
│   工具: 自动从 backend/<Agent>/mcpserver/*_tool.py 发现        │
│   Checkpointer: InMemorySaver (开发) / PostgresSaver (生产)    │
│   Middleware: PIIRedaction + Summarization (待启用)            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  backend/<Agent>/mcpserver/                    │
│                                                                  │
│   HealthAdvisor/      → 18 个 @mcp.tool() 函数                  │
│     ├─ diagnosis_tool.py    (症状分析、AI 诊断)                │
│     ├─ knowledge_tool.py    (知识库、搜索)                      │
│     └─ a2a_integration_tool (A2A 集成)                          │
│                                                                  │
│   HealthRecordsManager/  → 19 个 @mcp.tool() 函数              │
│     ├─ ocr_tool.py          (OCR 文本提取)                      │
│     ├─ data_extraction_tool (结构化信息提取)                    │
│     ├─ storage_tool.py      (档案 CRUD)                        │
│     └─ reminder_tool.py     (提醒管理)                          │
│                                                                  │
│   MedicationReminder/  → 14 个 @mcp.tool() 函数                │
│     ├─ reminder_tool.py     (用药提醒)                          │
│     ├─ drug_safety_tool.py  (药物互作)                          │
│     └─ notification_tool.py (通知发送)                          │
│                                                                  │
│   VisitSummaryGenerator/  → 12 个 @mcp.tool() 函数             │
│     ├─ document_tool.py     (文档解析)                          │
│     ├─ database_tool.py     (数据查询)                          │
│     └─ ai_analysis_tool.py  (AI 分析)                          │
│                                                                  │
│   合计: 63 个 MCP 工具 (其中 36 个 v2 接入)                     │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│              独立 a2a-sdk Server :10020 (可选部署)              │
│                                                                  │
│   GET  /.well-known/agent-card.json   (服务发现)               │
│   POST /                              (JSON-RPC 2.0)            │
│     ├─ message/send                   (a2a-sdk 标准)            │
│     ├─ message/stream                 (a2a-sdk 流式)            │
│     └─ agent/card                     (返回 AgentCard)          │
│                                                                  │
│   标准 a2a-sdk 0.3.x 协议，任意 a2a 客户端可调用              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    外部 LLM / 嵌入 / 存储                      │
│                                                                  │
│   LLM:       DeepSeek API   (https://api.deepseek.com)         │
│   Embedding: DashScope      (text-embedding-v4)                │
│   Database:  PostgreSQL 16  (Docker Compose)                    │
│   Search:    (待接入) 长期记忆 → PGVector                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块

### 3.1 v2 包结构

```
backend/A2AServer/src/A2AServer/v2/
├── __init__.py           # 包入口，导出所有 API
├── v2_runtime.py         # LangChain 1.x 探测 + Checkpointer
├── v2_agent.py           # V2Agent 基类（替代 BasicAgent）
├── sub_agents.py         # 4 个子 Agent
├── mcp_discover.py       # AST 扫描 @mcp.tool() 装饰器
├── mcp_tool_adapter.py   # 真实 MCP 工具 → BaseTool
├── host_graph.py         # LangGraph StateGraph 编排
├── bridge.py             # A2A Message 灰度路由
├── a2a_sdk_compat.py     # PHA 协议 ↔ a2a-sdk 协议
└── a2a_sdk_server.py     # a2a-sdk 标准 FastAPI server
```

### 3.2 各模块职责

| 模块 | 行数 | 职责 |
|------|------|------|
| `v2_runtime` | 90 | 探测 LangChain 1.x 可用性，管理 Checkpointer |
| `v2_agent` | 170 | V2Agent 基类，封装 `create_agent()` + `stream()` |
| `sub_agents` | 100 | 4 个子 Agent 声明（name/system_prompt/tools）|
| `mcp_discover` | 200 | AST 静态扫描 + 动态 importlib 加载（含超时保护）|
| `mcp_tool_adapter` | 280 | 把 MCP tool 函数包装成 LangChain BaseTool |
| `host_graph` | 467 | LangGraph StateGraph：classify → invoke_X → aggregate |
| `bridge` | 213 | 灰度路由（X-Use-V2 header + PHA_USE_V2 env）|
| `a2a_sdk_compat` | 213 | 协议双向转换（PHA TaskSendParams ↔ SDK SendMessageRequest）|
| `a2a_sdk_server` | 230 | a2a-sdk 0.3.x 标准 FastAPI server（独立 port 10020）|
| **合计** | **~1963 行** | **比 v1 adk_host_manager + BasicAgent (-72%)** |

---

## 4. 数据流

### 4.1 用户请求 → v2 响应

```
1. 前端 HTTP POST /message/send
   Header: X-Use-V2: true (或 PHA_USE_V2=true)
   Body: A2A Message {role: user, parts: [TextPart(text="我头疼")], metadata: {user_id, conversation_id}}

2. hostAgentAPI._send_message
   → sanitize_message
   → 检测 header → 走 v2_bridge

3. v2_bridge.v2_process_message
   → 提取 query / conversation_id / user_id
   → 调 v2.route_and_invoke

4. v2.route_and_invoke (HostGraph)
   → graph.ainvoke(initial_state)
   → classify_node: 3 层路由
     • Layer 1: metadata.selected_agent
     • Layer 2: 关键词启发
     • Layer 3: LLM 委派 (fallback)
   → invoke_X_node: V2Agent.stream()
     • create_agent(model=deepseek-chat, tools=[...])
     • 真实 MCP 工具调用
   → aggregate_node: 汇总

5. V2Agent.stream()
   → agent.stream({messages: [...]}, config={thread_id})
   → DeepSeek API 调用
   → 工具调用 (analyze_symptoms, knowledge_search, ...)
   → 流式返回 events

6. v2 final_response
   → {role: agent, content: "建议...", agent: "health_advisor", v2_routing: {...}}

7. 注入 conversation.messages
   → 通过 WebSocket / SSE 推回前端
```

### 4.2 协议兼容

```
┌─────────────────┐         ┌─────────────────┐
│   PHA 私有协议   │ <─────> │  a2a-sdk 0.3.x  │
│  TaskSendParams │         │  SendMessage    │
│  Message        │         │  Request/Resp   │
│  TextPart       │         │  Part/TextPart  │
└─────────────────┘         └─────────────────┘
        ↑                            ↑
   v1 adk_host_manager         a2a_sdk_server
                                (port 10020)
        ↑                            ↑
   现有前端 (零修改)         标准 a2a 客户端
```

---

## 5. 关键设计决策

### 5.1 为什么用 LangGraph 1.0？

| 选项 | 优势 | 劣势 | 选择 |
|------|------|------|------|
| 手写 if/else (v1) | 简单 | 不可观测、不可恢复 | ❌ |
| LangGraph 1.0 | 显式 StateGraph、可观测、可恢复 | 学习曲线 | ✅ |
| Temporal | 强工作流 | 重 | ❌ |

### 5.2 为什么用 LangChain 1.0 `create_agent`？

| 选项 | 优势 | 劣势 | 选择 |
|------|------|------|------|
| 手写 Agent (v1) | 完全可控 | 1800 行 | ❌ |
| LangChain 1.0 create_agent | LangGraph 集成、Middleware、Checkpointer | 版本要求 1.2+ | ✅ |
| LlamaIndex | RAG 强 | 工具调用弱 | ❌ |

### 5.3 为什么 DeepSeek 兼容 OpenAI 协议？

- **成本低**：1/10 于 GPT-4
- **国产**：合规
- **OpenAI 协议**：LangChain 一行切换

### 5.4 为什么 36/63 个工具而非全接？

- **DB 工具黑名单**：`database_tool` / `storage_tool` 顶层连 DB，本地无容器会失败
- **集成工具黑名单**：`a2a_integration_tool` 避免循环依赖
- **MCP 协议工具**：保留 MCP 协议层调用，独立端口

---

## 6. 性能与可扩展性

### 6.1 当前性能（实测）

| 指标 | v1 | v2 |
|------|----|----|
| 单次请求延迟 | 1-2s | 5-30s (含工具调用) |
| 工具调用并发 | 串行 | 并行（LangGraph）|
| 状态恢复 | 不支持 | Checkpointer (InMemory/Postgres) |
| 流式输出 | Event 粒度 | Token 粒度 + 工具流 |

### 6.2 扩展点

- **加新 Agent**：在 `sub_agents.py` 加 1 个类 + 在 `host_graph.py` 加 1 个节点
- **加新工具**：在 `backend/<Agent>/mcpserver/` 加 `*_tool.py` 即可自动发现
- **换 LLM**：改环境变量 `PHA_LLM_MODEL`（支持 `deepseek-chat` / `openai:gpt-4o` / `anthropic:claude-3`）
- **加可观测**：在 `v2_runtime.py` 加 LangSmith / Langfuse interceptor

---

## 7. 文档目录

| 文档 | 受众 | 内容 |
|------|------|------|
| [V2_ARCHITECTURE.md](V2_ARCHITECTURE.md) | 所有人 | 架构总览（本文档）|
| [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) | 开发者 | 开发环境、调试、新增 Agent/工具 |
| [V2_OPERATIONS.md](V2_OPERATIONS.md) | 运维 | 部署、监控、灰度切流、回滚 |
| [V2_MIGRATION_NOTES.md](V2_MIGRATION_NOTES.md) | 接棒者 | 从 v1 迁移、v1/v2 兼容、风险 |
| [V2_API_REFERENCE.md](V2_API_REFERENCE.md) | 集成方 | 完整 API 文档（hostAgentAPI + a2a-sdk）|

---

## 8. 版本历史

| Tag | 阶段 | 内容 | 验收 |
|-----|------|------|------|
| v2.0-stage1 | 1 | 依赖升级 + 可观测基础 | 12/12 |
| v2.0-stage2 | 2 | V2Agent 入口 | 12/12 |
| v2.0-stage2.1 | 2.1 | langgraph 1.0 兼容性修复 | - |
| v2.0-stage2.2 | 2.2 | DeepSeek 端到端跑通 | - |
| v2.0-stage2.5 | 2.5 | **36 个真实 MCP 工具接入** | 14/14 |
| v2.0-stage3 | 3 | **HostGraph LangGraph 编排** | 21/21 |
| v2.0-stage4 | 4 | v2 接入 hostAgentAPI（灰度路由）| 11/11 |
| v2.0-stage5 | 5 | **a2a-sdk 0.3.x 协议升级** | 20/20 |
| **合计** | - | **9 个 tag 全部推送** | **90/90** |
