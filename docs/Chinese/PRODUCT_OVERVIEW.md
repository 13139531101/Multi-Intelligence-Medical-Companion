# PHA v2 产品架构总览（PRODUCT_OVERVIEW）

> **目的**: 一份文档说清 PHA v2 的全部架构、设计决策、文件位置、未来规划
> **对应代码**: `git log --oneline --all | head -50`（45+ tags）
> **更新日期**: 2026-07-16

---

## 1. 产品定位

**PHA (Personal Health Assistant)** —— 个人健康智能助手

- 🎯 **3 大智能体协同**: health_advisor / health_records / medication_reminder / visit_summary
- 🌐 **3 大协议**: A2A (Agent-to-Agent) + MCP (Model Context Protocol) + ANP (Agent Network Protocol)
- 🤖 **多 LLM**: DeepSeek + Qwen + Claude + OpenAI（自动 fallback）
- 🧠 **3 层记忆**: L1 内存 + L2 Redis + L3 PostgreSQL + Embedding 语义检索
- 🔐 **DID:WBA**: 去中心化身份 + 签名验证

---

## 2. 系统架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    用户层 (User Layer)                        │
├──────────────────────────────────────────────────────────────┤
│  📱 微信小程序 (WeChat Mini Program)                          │
│  🌐 Web Dashboard (新) — http://hostapi:13002/test/dashboard │
│  📊 Grafana (监控)                                            │
└──────────────┬────────────────────────┬──────────────────────┘
               │                        │
               ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│              HostAPI  (FastAPI, port 13002)                   │
├──────────────────────────────────────────────────────────────┤
│  /v2/chat/stream        ← SSE 流式 LLM                       │
│  /v2/agents/*           ← Agent registry (灰度)               │
│  /v2/models/*           ← 多 LLM 路由 + 缓存                  │
│  /v2/alerts/*           ← 5 报警规则                         │
│  /v2/mcp/*              ← MCP 管理 + 远程 + 可视化 ⭐          │
│  /v2/skills /v2/tools   ← Skill + Tool registry ⭐            │
│  /anp/agent/*           ← ANP 协议                          │
│  /test/dashboard.html   ← Web 管理界面 ⭐                    │
└──────────────┬────────────────────────┬──────────────────────┘
               │                        │
       ┌───────┴───────┐        ┌───────┴───────┐
       ▼               ▼        ▼               ▼
┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
│  Sub-Agent │  │  4 MCPs   │  │  记忆系统   │  │  LLM Provider│
│            │  │ (本地)     │  │            │  │             │
│ health_    │  │ - health_  │  │ PHAHealth  │  │ DeepSeek    │
│  advisor   │  │   records  │  │ PHAEntity  │  │ Qwen        │
│ health_    │  │ - visit_   │  │ PHALayered │  │ Claude      │
│  records   │  │   summary  │  │            │  │ OpenAI      │
│ med_       │  │ - med_     │  │ + AgentMe- │  │             │
│  reminder  │  │   reminder │  │   morySystem│ │ (fallback链)│
│ visit_     │  │ - health_  │  │ (Postgres)  │  └────────────┘
│  summary   │  │   advisor  │  │            │                  │
│            │  │            │  │ + Redis    │                  │
│ (LangGraph │  │ + 远程 MCP │  │   (L2)     │                  │
│  1.x)      │  │   (HTTP)   │  │            │                  │
└────────────┘  └────────────┘  └────────────┘                  │
                                                                │
       ┌────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                  存储层                                        │
├──────────────────────────────────────────────────────────────┤
│  PostgreSQL (pgvector) - 长期记忆 + 4 关联表 + 业务数据      │
│  Redis - 短期缓存 + access token + 会话上下文                │
│  Pinecone/ChromaDB (可选) - 向量检索 (备选)                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 关键文件位置

### 3.1 后端 (Backend)

```
backend/A2AServer/src/A2AServer/v2/
├── v2_agent.py              # 主 Agent 框架（LangChain 1.x）
├── v2_runtime.py            # 运行时（单例 + checkpointer + middleware）
├── host_graph.py            # LangGraph 主图
├── sub_agents.py            # 4 个 sub-agent
├── multi_model.py           # 多 LLM 路由器 + fallback
├── monitoring.py            # Prometheus metrics
├── alerting.py              # 报警系统
├── semantic_cache.py        # LLM 响应缓存
├── langchain_memory.py      # 3 个 langchain 风格记忆 ⭐ 阶段40-1
├── skills.py                # Skill 系统 + @tool 工具 ⭐ 阶段41-1
├── skills_endpoints.py      # Skills HTTP 端点 ⭐
├── mcp_loader.py            # MCP 加载器 + 远程 MCP ⭐ 阶段41-2
├── mcp_endpoints.py         # MCP HTTP 端点 + SSE 可视化 ⭐
├── did_wba.py               # DID 签名验证
├── anp_crawler.py           # ANP 爬虫
├── rate_limit.py            # 限流
├── tool_cache.py            # 工具缓存
└── *_endpoints.py           # 各模块的 FastAPI 端点
```

### 3.2 前端 (Frontend)

```
frontend/
├── wechat_mini_program/     # 📱 微信小程序
│   ├── pages/agent_chat/    # 聊天页（待重构）
│   ├── pages/index/         # 主页（待重构）
│   └── utils/api.js         # 1600+ 行 API 客户端
├── hostAgentAPI/            # 🌐 后端服务代码
│   ├── api.py               # FastAPI 主入口
│   ├── Dockerfile
│   └── dashboard.html       # Admin Dashboard（阶段41-5）
├── dashboard.html           # 主 Dashboard 入口
├── test_simple.html         # 简单测试页（已挂载）
└── test_page.html           # 完整测试页
```

### 3.3 记忆系统

```
backend/AgentMemorySystem/
├── memory_system.py         # 主类
├── memory_storage.py        # Postgres CRUD
├── memory_retrieval.py      # Embedding 检索
├── memory_manager.py        # 关联图谱
├── database_config.py       # 4 张表 schema
└── embedding_service.py     # sentence-transformers / API

backend/HealthAdvisor/memory_service.py        # health_advisor 专用
backend/HealthRecordsManager/memory_service.py # health_records 专用
backend/MedicationReminder/memory_service.py  # medication 专用
backend/VisitSummaryGenerator/memory_service.py # visit_summary 专用
```

---

## 4. 4 个 Sub-Agent

| Agent | 职责 | LLM | Tools |
|-------|------|-----|-------|
| **health_advisor** | 健康问答 + 知识库 | deepseek | 18 个 (RAG + 计算 + 搜索) |
| **health_records** | 病历管理 + OCR | deepseek | upload/OCR/检索 |
| **medication_reminder** | 用药计划 + 提醒 | qwen | 提醒/检查/统计 |
| **visit_summary** | 就诊小结 | deepseek | 生成/提取 |

**协同流程** (HostGraph):
1. 用户发问 → health_advisor 分类意图
2. 需要病历 → 转发 health_records
3. 需要开药 → 转发 medication_reminder
4. 需要就诊 → 转发 visit_summary
5. 所有 agent 共享同一对话上下文

---

## 5. 关键设计决策

### 5.1 提示词架构 (从拼接 → Skill)

**之前** (❌ 难维护):
```python
system_prompt = BASE_PROMPT + "\n" + tool_docs + "\n" + agent_specific
```

**现在** (✅ 阶段41-1):
```python
from A2AServer.v2.skills import build_smart_prompt
prompt, used_skills = build_smart_prompt(
    base="你是健康助手",
    user_text="我最近血压高",
    top_k=2,
)
# 自动选 medication + vital_signs skill，动态拼接
```

**6 个默认 Skill**:
- 📋 health_records (病历)
- 💊 medication (用药)
- 📊 vital_signs (体征)
- 📅 visit_booking (预约)
- 💉 drug_query (药品查询)
- 💬 general_chat (闲聊)

### 5.2 MCP 加载 (从手动 → 动态 + 远程)

**之前** (❌ 硬编码):
```python
# 每个 agent 内部 import + tool
from backend.HealthRecordsManager import ...
```

**现在** (✅ 阶段41-2):
```python
# 统一注册
loader = get_mcp_loader()
# 4 个本地 MCP 自动注册
loader.register_remote(name="remote-mcp", url="https://...")
# 调用 + 可视化
result = loader.call("health_records_mcp", "search", args)
```

**4 个本地 + N 个远程** (HTTP/SSE/WebSocket)

### 5.3 记忆系统 (langchain + 自研)

**用 langchain 的**:
- `langchain.agents.create_agent` (Agent 框架)
- `langchain_openai.ChatOpenAI` (LLM 接口)
- `langgraph.checkpoint.postgres` (会话状态)
- `langchain.agents.middleware` (摘要 + PII)

**自研的** (langchain 没有医疗领域):
- PHAHealthMemory: 重要性评分 + 6 类医疗 tag
- PHAEntityMemory: 5 类医疗实体 + 中英双语
- PHALayeredMemory: L1 内存 + L2 Redis + L3 PG

### 5.4 LLM 缓存 (按 hash)

- 精确 hash (task_type + tokens + temp + content)
- 相似 hash (忽略 temp/tokens)
- 命中率统计
- 集成到 `/v2/models/stream` SSE 端点

### 5.5 报警系统 (5 默认规则)

1. request_error_rate > 10% (warning)
2. request_error_rate > 30% (critical)
3. llm_error_rate > 20% (error)
4. request.p95 > 10s (warning)
5. cache.hit_rate < 30% (info)

**自动评估 + webhook + 100 条历史**

---

## 6. HTTP API 端点（60+）

### 6.1 Agent
```
GET  /v2/agents/registry
POST /v2/agents/registry/{name}/enable
POST /v2/agents/registry/{name}/disable
GET  /v2/agents/registry/alias/{alias}
```

### 6.2 LLM
```
POST /v2/chat/stream       (SSE 流式)
POST /v2/models/stream     (SSE 多模型)
GET  /v2/models/cache/stats
GET  /v2/models/cache/entries
POST /v2/models/cache/clear
```

### 6.3 Skills & Tools (阶段41)
```
GET  /v2/skills
POST /v2/skills/match
GET  /v2/tools
POST /v2/tools/call
```

### 6.4 MCP (阶段41)
```
GET  /v2/mcp/servers
GET  /v2/mcp/calls/active
GET  /v2/mcp/calls/history
POST /v2/mcp/register       (远程 MCP)
POST /v2/mcp/call/{name}
GET  /v2/mcp/health
GET  /v2/mcp/visualize/stream  (SSE 实时可视化)
```

### 6.5 报警
```
GET  /v2/alerts/active
GET  /v2/alerts/rules
POST /v2/alerts/evaluate
POST /v2/alerts/rule/add
```

### 6.6 记忆
```
GET  /v2/memory/entities/{user_id}
GET  /v2/memory/history/{user_id}
```

### 6.7 监控
```
GET  /health
GET  /health/deep
GET  /metrics   (Prometheus)
```

### 6.8 协议
```
GET  /anp/agent/ad.json
GET  /anp/agent/interface.json
POST /anp/agent/rpc
GET  /anp/agents/crawl
GET  /anp/did/list
POST /anp/did/verify
POST /anp/did/sign
```

### 6.9 Web UI (阶段41-5)
```
GET  /test/dashboard.html    ← Admin Dashboard
GET  /test/test_simple.html
GET  /test/test_page.html
```

---

## 7. 前端设计 (待重构)

### 7.1 现状问题
- ❌ 聊天页 MD 渲染只支持 4 种语法（应该用完整 markdown）
- ❌ 主页交互不直观
- ❌ 没有统一的设计语言
- ❌ 没有可视化的 MCP/工具调用过程
- ❌ 后台管理缺失

### 7.2 重构方向 (阶段42-45)
- 完整 markdown 渲染器（200 行 JS，支持所有语法）
- 统一设计语言（Material Design / Ant Design 风格）
- MCP 实时调用流可视化
- 主页重设计（卡片式 + 操作流）
- 完整 Admin Dashboard（已有 /test/dashboard.html）
- Grafana 集成

---

## 8. 部署架构

### 8.1 Docker 服务

```yaml
services:
  hostapi:        port 13002 (FastAPI)
  pha-postgres:   port 5432  (PostgreSQL + pgvector)
  pha-redis:      port 6379  (Redis 7)
  grafana:        port 3000  (监控面板)
  prometheus:     port 9090  (指标抓取)
```

### 8.2 启动命令

```bash
# 启动所有服务
docker compose up -d

# 单独启动 hostapi
docker run -d --name hostapi \
  --network a2aserver_default \
  -p 13002:13002 \
  -e PYTHONPATH=/app:/app/backend \
  -e DEEPSEEK_API_KEY=... \
  -e DASHSCOPE_API_KEY=... \
  a2aserver-hostapi:stage41
```

---

## 9. 测试覆盖

| 阶段 | 脚本 | 测试数 | 状态 |
|------|------|--------|------|
| 36-37 | test_sse_miniapp.py | 4 | ✅ |
| 38-1 | test_anp_crawler.py | 4 | ✅ |
| 38-2 | test_multi_model.py | 5 | ✅ |
| 38-3 | test_alerting.py | 7 | ✅ |
| 39-1+2 | test_did_wba.py | 8 | ✅ |
| 39-3 | test_semantic_cache.py | 8 | ✅ |
| 39-4 | test_e2e_miniapp.py | 6 | ✅ |
| 40-1 | test_langchain_memory.py | 9 | ✅ |
| 41-1+2 | test_skills_mcp.py | 10 | ✅ |
| **总计** | | **61** | **✅** |

---

## 10. 后续规划 (Roadmap)

### 阶段42: 小程序重构
- [ ] 完整 markdown 渲染
- [ ] 主页重设计
- [ ] MCP 调用流可视化
- [ ] 统一设计语言

### 阶段43: Web Dashboard 完善
- [ ] Grafana 集成（端口 3000）
- [ ] Prometheus 指标抓取
- [ ] 自定义 dashboard
- [ ] 报警推送（webhook + 邮件）

### 阶段44: Admin 后台
- [ ] 用户管理 CRUD
- [ ] 对话审核
- [ ] 记忆审查
- [ ] 数据导出

### 阶段45: 完善文档
- [ ] API 文档自动生成（OpenAPI）
- [ ] 架构图自动更新
- [ ] 部署文档
- [ ] 用户手册

---

## 11. 关键 Tag 列表

```bash
git tag -l 'v2.0-stage*' | tail -20
# v2.0-stage35-miniapp-v2
# v2.0-stage36-asyncfix
# v2.0-stage37-sse
# v2.0-stage37sse-fix
# v2.0-stage38-1-crawler
# v2.0-stage38-2-multimodel
# v2.0-stage38-3-alerting
# v2.0-stage38-4-snapshot
# v2.0-stage39-1-2-registry-did
# v2.0-stage39-3-semantic-cache
# v2.0-stage39-4-e2e
# v2.0-stage39-5-docs
# v2.0-stage40-1-langchain-memory
# v2.0-stage41-skills-mcp
```

---

## 12. 关键文件 URL

| 资源 | URL |
|------|-----|
| hostapi health | http://localhost:13002/health |
| Admin Dashboard | http://localhost:13002/test/dashboard.html |
| 测试页 | http://localhost:13002/test/test_simple.html |
| Metrics (Prometheus) | http://localhost:13002/metrics |
| Skills | http://localhost:13002/v2/skills |
| Tools | http://localhost:13002/v2/tools |
| MCP Servers | http://localhost:13002/v2/mcp/servers |
| MCP 可视化 (SSE) | http://localhost:13002/v2/mcp/visualize/stream |

---

> **最后更新**: 阶段41 完成
> **下次更新**: 阶段42 (小程序重构)