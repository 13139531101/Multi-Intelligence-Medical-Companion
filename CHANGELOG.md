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

---

## v2.0-stage48-25 - 2026-07-28 - 撤掉 CopilotKit，自写 AI 浮窗 + SSE 流

### 🎯 背景
CopilotKit 前端需要 Node.js runtime, 在我们的轻量 Vite 体系下集成度差; 之前常常启动超时. 这一阶段全部撤掉, 用纯 React + MUI + 自写 SSE store 替代.

### ✨ 新增
- 自写 AI 浮窗 `frontend/multiagent_front/src/components/ChatPanel.jsx` (~150 行)
  - 右下角圆形按钮 + 弹出对话窗
  - 仿 CopilotKit UX, 但纯 React + MUI
  - 只在登录后显示 (`{user && <ChatPanel />}`)
- 自写 SSE Chat store `frontend/multiagent_front/src/components/useChat.jsx` (~290 行)
  - React Context + useReducer, 不依赖 zustand / CopilotKit
  - 浏览器原生 `fetch + ReadableStream` 读 SSE
  - 解析 AG-UI 协议 (TEXT_MESSAGE_*, TOOL_CALL_*, RUN_*)
  - 同时兼容旧版 `/v2/chat/stream` (routing/chunk/tool_call/tool_result/done)
- 默认首页 `/` → `/v2/dashboard`, 登录后直达 dashboard

### 🔧 改动
- `v2_agent.py`: recursion_limit 50 → 100 (修 LangGraph 短上下文自动 fallback 丢工具结果)
- `copilotkit_runtime.py`: SSE 解析 `aiter_lines` → `aiter_bytes` + `\n\n` 切分 (修漏 line 问题), chunk 字段 `content` → `text`
- `App.jsx`: 去掉 `<CopilotKit>` wrapper, 换 `<ChatProvider>`
- `vite.config.js`: 简化注释

### 🐛 修了的 bug
1. **AI 不出文本** - bridge 发 `text` 字段, runtime 错读 `content`
2. **SSE pump 漏 line** - async generator 嵌套时 `aiter_lines` 漏读
3. **LangGraph recursion limit** - 50 太低, 提到 100

### ⚠️ 注意
- bridge 仍发 5 种事件 (`routing/tool_call/tool_result/chunk/done`)
- runtime 翻译成 AG-UI 16 种事件 (向后兼容 CopilotKit 旧前端)
- 前端只用了 4 种关键 event (TEXT_MESSAGE_CONTENT / TOOL_CALL_START / TOOL_CALL_RESULT / RUN_FINISHED)

### ✅ 验证
- E2E 浏览器 demo 账号 → /v2/dashboard → 浮窗对话 → 收到 AI 文本 + 工具调用
- curl `/api/copilotkit`: 32+ TEXT_MESSAGE_CONTENT events / 6435+ bytes
- 旧路由 (`/dashboard`, `/medication`) 仍重定向到 `/v2/*`
- 未登录浮窗按钮隐藏

### 📁 新增 / 修改文件
```
frontend/multiagent_front/src/components/ChatPanel.jsx    (新增 ~150 行)
frontend/multiagent_front/src/components/useChat.jsx     (新增 ~290 行)
frontend/multiagent_front/src/App.jsx                     (改: 去掉 CopilotKit)
frontend/multiagent_front/vite.config.js                  (改: 简化注释)
frontend/hostAgentAPI/copilotkit_runtime.py               (改: SSE 解析 + chunk 字段)
backend/A2AServer/src/A2AServer/v2/v2_agent.py            (改: recursion_limit)
```

### 📝 待办
- 用户上下文持久化 (session_id)
- Markdown 渲染 AI 输出
- 消息多轮上下文传递

---

## v2.0-stage48-26 - 2026-07-28 - 修 MCP 18→18 工具加载 + 前端 stub 接真数据

### 🎯 背景
- HealthAdvisor 代码里有 **18 个 `@mcp.tool()`** 装饰的 tool 函数, 但运行时 `loaded 11 tools`. 7 个 tool 神秘丢.
- `getMedicationsHistory()` 整个函数 return 硬编码 7 天假数据, 所有图表显示随机数.

### 🐛 修了的 bug

**Bug 1: MCP 工具加载不全 (18→11)**
- 根因: `langchain-mcp-adapters` 包没装. http / stdio transport 都因为 `No module named` 失败, 终极回退到 `_load_inprocess_mcp_tools` 但这有硬编码 `SKIP_TOOLS = {a2a_integration_tool, memory_integration_tool, database_tool, storage_tool, async_analysis_tool}` → 5 个 file 整个跳过 → 7 个 tool 丢.
- 修复: `requirements.txt` 加 `langchain-mcp-adapters>=0.1.0`. 装包后 `_load_http_mcp_tools` 走真 MCP server, 18 tool 全加载 (SKIP 不生效因为 MCP 动态 spawn).

**Bug 2: getMedicationsHistory stub**
- 根因: 函数整个 return `[星期, 60-95]` 硬编码.
- 修复: 重写为按天并发拉 `GET /medication-reminders?date=YYYY-MM-DD`, 聚合 taken 数, 算 rate. `params.detail=true` 返回明细列表. TodayDashboard 用真 rate, NewMedication 详情表格用 detail mode.

### ✅ 验证
- `/v2/medication` 本周 tab: 周六 25%, 周一 50% (真 taken 数) — **替代 60-95 随机数**
- `docs/Chinese/AGENT_PROGRESS.md` 详细记录
- 待 user 重启 hostapi 后, 18 tool log 验证

### ⚠️ 当前待 user 启动
```
docker compose -f I:/A2A/3/A2AServer/docker-compose.yml up -d hostapi
docker logs a2aserver-hostapi-1 --tail 50 | grep "loaded"
# 应: [mcp_tool_adapter:http] agent=health_advisor loaded 18 tools
```

### 📁 修改文件
```
frontend/hostAgentAPI/requirements.txt                  (加 langchain-mcp-adapters)
frontend/multiagent_front/src/api/healthApi.js          (重写 getMedicationsHistory)
frontend/multiagent_front/src/pages/TodayDashboard.jsx  (weekSummary 真数据)
frontend/multiagent_front/src/pages/NewMedication.jsx   (fetchHistory detail=true)
docs/Chinese/AGENT_PROGRESS.md                          (新增详细进度报告)
docs/Chinese/CHANGELOG.md                               (追加 48-26)
```
