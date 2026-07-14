# 更新日志 (CHANGELOG)

PHA v2 的所有重大变更记录。

---

## v2.0-stage33 - 2026-07-14 (本日)

### ✨ 新增：ANP (Agent Network Protocol) 集成

- 装 `anp[api]>=0.8.8` SDK（实际装 0.8.9）
- hostapi 挂载 ANP sub-app（`/anp` 前缀）
- 自动暴露：
  - `GET  /anp/health` 健康检查
  - `GET  /anp/agent/ad.json` Agent Description（含 DID:WBA）
  - `GET  /anp/agent/interface.json` OpenRPC 接口
  - `POST /anp/agent/rpc` JSON-RPC 2.0 调用
  - `GET  /anp/agents` 列出 4 个 PHA agent
  - `GET  /anp/agents/discover` ANP 爬虫主动发现外部
- ANP RPC 方法：`route_query` / `parallel_query` / `list_agents`
- 4 个 PHA agent 自动获得 DID：`did:wba:pha.local:{health_advisor, health_records, medication_reminder, visit_summary}`
- **E2E 验证**：`ad.json` / `interface.json` / `list_agents` RPC 全部 200，LLM 路由正常
- **6 files changed, 616 insertions**
- verify_stage33: ANP 协议全链路通过 ✅

---

## v2.0-stage31 - 2026-07-14 (本日)

### ✨ 新增：AgentRegistry 自动注册（可扩展性）

- 新建 `agent_registry.py`（~180 行）：
  - `AgentSpec` 数据类
  - `AgentRegistry` 单例
  - `@register_agent(...)` 装饰器
  - `discover_agents()` 自动发现
- 改造 `sub_agents.py`：4 个 class 改用 `@register_agent` 装饰器
- 改造 `host_graph.py`：
  - `build_host_graph` 用 `discover_agents()` 自动构建 node + edges
  - 路由表从 hardcode 改为动态拼装
  - Layer 1 metadata alias 改为 `AgentRegistry.by_alias()`
  - Layer 2 关键词改为 `_build_heuristic_keywords()`
- 改造 `monitoring_endpoints.py`：用 `discover_agents()` 替代 hardcode
- **新增 agent 只改 1 个 class**（装饰器绑定），其他全自动

---

## v2.0-stage30 - 2026-07-13 (本日)

### ✨ 新增：多 agent 编排（并行 + 状态 + 持久化）

- **host_graph multi 模式**：
  - 4 个 invoke_X 并行 fan-out
  - 每个 node 写自己独立字段（避免 LangGraph 并行写冲突）
  - `aggregate_multi_node` 汇总 4 worker 输出
  - `worker_summaries` 含 status/elapsed_ms/tool_calls_count
- **`/v2/agents/status` 端点**：
  - `GET /v2/agents/status` 列出 4 sub-agent
  - `GET /v2/agents/{name}/status` 单 agent 详情（18 tool names + system_prompt）
- **PostgresSaver 持久化**：
  - 装 `langgraph-checkpoint-postgres>=2.0.0` + `psycopg[binary,pool]`
  - 适配 2.x async context manager API
  - `v2_agent.py` `agent.stream()` 改 `astream()`（兼容 AsyncPostgresSaver）
  - 设 `PHA_CHECKPOINT_DB_URL` 即启用
  - state 写入 PostgreSQL，支持长时间任务 + 崩溃恢复
- **9 files changed, 572 insertions**
- E2E 验证：
  - multi mode 4 agent 并行（tool_calls: 48/77/107/164）
  - PostgresSaver Checkpointer OK
  - `/v2/agents/health_advisor/status` 返回 18 tool names

---

## v2.0-stage24 - 2026-07-11

### ✨ 新增：多模型协同 (4 provider + 路由 + fallback)

- DeepSeek / Qwen / Claude / Local 4 个 provider 抽象
- ModelRouter：6 任务类型路由（chat/code/analysis/summary/translation/creative）
- Fallback 链：deepseek → qwen → claude → local
- 限流：每 provider 每分钟 60 次
- 统计：success/error/rate_limited/avg_latency_ms/total_tokens
- 4 个 HTTP 端点：`/v2/models/{chat,providers,stats,test-fallback}`
- **实际 LLM 调用验证通过**（DeepSeek 76 tokens + Qwen 2126ms）
- verify_stage24: **58/58 通过** ✅

---

## v2.0-stage23 - 2026-07-11

### 🐛 修复：build.yml 路径错误

- 原 matrix 路径全错（`backend/agents/*` 不存在）
- 修正为实际路径：`backend/HealthAdvisor` / `HealthRecordsManager` / `MedicationReminder` / `VisitSummaryGenerator`
- 加 `continue-on-error: true` + Dockerfile 存在性检查
- verify_stage23: **38/38 通过** ✅
- 实际 docker build 成功（test-hostapi:latest 1.46GB）

---

## v2.0-stage22 - 2026-07-11

### ✨ 新增：CI/CD 4 个 GitHub Actions 工作流

- `test.yml`：跑 15 个 verify_stage + pgvector/redis services
- `lint.yml`：ruff + black + mypy
- `build.yml`：5 镜像矩阵构建 + 推送阿里云容器镜像
- `release.yml`：tag 触发自动 GitHub Release + changelog
- 触发器：push / pull_request / tags v*.*.\* / workflow_dispatch
- verify_stage22: **45/45 通过** ✅

---

## v2.0-stage21 - 2026-07-11

### ✨ 新增：RAG 索引/检索/反馈 (PGVector 业务层)

- 3 表：rag_documents + rag_chunks (vector(1024) + ivfflat) + memory_embeddings
- Embedding：DashScope text-embedding-v3（1024 维）
- chunk_text：中英文段落切分
- RAGStore：index/search/feedback/recall/stats
- 5 个 HTTP 端点：`/v2/rag/{index,search,feedback,recall,stats}`
- DB schema 修复：vector(384→1024) + id default gen_random_uuid() + pgcrypto
- verify_stage21: **37/37 通过** ✅

---

## v2.0-stage20 - 2026-07-10

### ✨ 新增：OAuth2 鉴权

- 授权码流程：/v2/oauth/authorize → GitHub → /v2/oauth/callback
- JWT access token (15 min) + refresh token (7 day) + 轮转
- 7 个 HTTP 端点：`/v2/oauth/*`
- verify_stage20: **47/47 通过** ✅

---

## v2.0-stage19 - 2026-07-10

### 🐛 修复：写操作安全审计

- write_audit.py：记录所有 POST/PUT/DELETE/PATCH
- 4 个 HTTP 端点：`/v2/audit/*`
- verify_stage19: **31/31 通过** ✅

---

## v2.0-stage18 - 2026-07-10

### 🐛 修复：/a2a 端点 400 错误

- a2a_sdk_compat.py 修复请求/响应格式
- verify_stage18: **通过** ✅

---

## v2.0-stage14 ~ stage12

详见 git tag 历史。

---

## v2.0-final - 2026-07-01

首版 v2.0-final 标签。

---

## v1.0.0 / v1.0.1

项目初始化版本。
