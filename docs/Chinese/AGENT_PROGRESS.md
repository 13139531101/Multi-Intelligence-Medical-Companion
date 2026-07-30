# PHA v2 - 智能体 & 前端集成进度报告

> 截至 2026-07-28
> 阶段: 48-25 / 48-26

---

## 一、整体状态

| 系统层 | 状态 | 说明 |
|---|---|---|
| 后端 agent: health_advisor | ⚠️ 11 tool (待修到 18) | 已知 bug, 需装 `langchain-mcp-adapters` 包 + 重启 hostapi |
| 后端 agent: health_records | ✅ 健康 | |
| 后端 agent: medication_reminder | ✅ 健康 | |
| 后端 agent: visit_summary | ✅ 健康 | |
| AI 浮窗 (前端) | ✅ 工作中 | 撤掉 CopilotKit, 自写 SSE 解析, AG-UI 兼容 |
| 数据: reminder logs | ✅ 历史表有数据 | 但前端 stub 之前没用 |
| 数据: AI 上下文 (session_id) | ❌ 缺失 | 每轮对话无记忆 |

---

## 二、今阶段已完成 (48-25 / 48-26)

### ✅ 撤掉 CopilotKit (48-25)
**问题**: CopilotKit Node.js runtime 在我们轻量 Vite + MUI 体系下集成差, 启动慢/超时. AI 浮窗一半时间点不出来.

**做法**:
- 撤掉 `frontend/hostAgentAPI` 里的 CopilotKit SDK wrapper
- 自写 `frontend/multiagent_front/src/components/ChatPanel.jsx` (~150 行) — 右下角机器人按钮, 弹出对话框
- 自写 `frontend/multiagent_front/src/components/useChat.jsx` (~290 行) — React Context + useReducer + 原生 `fetch + ReadableStream` 读 SSE
- 解析 AG-UI 协议 (TEXT_MESSAGE_START / TEXT_MESSAGE_CONTENT / TOOL_CALL_START / TOOL_CALL_RESULT / RUN_FINISHED / RUN_ERROR) + 兼容旧版 /v2/chat/stream (routing / chunk / tool_call / tool_result / done)
- 浮窗只在登录后显示 (`{user && <ChatPanel />}`)
- 后端 `v2_agent.py` `recursion_limit` 50 → 100 (修短 prompt 自动 fallback)
- 后端 `copilotkit_runtime.py` SSE 解析 `aiter_lines` → `aiter_bytes` + `\n\n` 切分 (修 SSE 漏 line)
- 后端 `copilotkit_runtime.py` chunk 字段 `content` → `text` (修 bridge 字段不一致)

**验证**: 浏览器 demo 账号登录 → `/v2/dashboard` → 右下机器人 → 输入 "帮我看看体检报告并给我建议" → 收到 32 个 `TEXT_MESSAGE_CONTENT` chunk, 6435+ 字节.

---

### ⚠️ 修 MCP 工具加载 18→18 (48-26)
**问题**: 后端 `hostapi` 启动 log 显示:
```
[mcp_discover] agent=health_advisor found 18 MCP tools in 5 files
[mcp_tool_adapter] agent=health_advisor loaded 11 tools
```
AI 实际可用工具比代码声明少 **7 个**, 影响能力面 (取药/历史/记忆等).

**根因**:
1. `_load_real_mcp_tools` 走 3-tier fallback: streamable_http → stdio → in-process
2. streamable_http 和 stdio 都用 `langchain_mcp_adapters.load_mcp_tools`, 但**包没装** → `No module named 'langchain_mcp_adapters'` → 返 0 tool
3. 终极 fallback `_load_inprocess_mcp_tools` 有 hardcoded `SKIP_TOOLS = {a2a_integration_tool, memory_integration_tool, database_tool, storage_tool, async_analysis_tool}` → 5 个 tool file 整个 skip, 7 个 tool 被丢
4. 7 个 tool = a2a_integration(5) + database(2)

**修复**:
- `frontend/hostAgentAPI/requirements.txt` 加包:
  ```diff
  + # LangChain MCP 适配器 (stdio / streamable_http transport 必需)
  + langchain-mcp-adapters>=0.1.0
  ```
- 装包后, `_load_http_mcp_tools` 真 MCP server 跑起来, **18 个工具全加载** (MCP server 模式无 SKIP 限制)

**当前状态**: **Build 完成, hostapi 未重启**. 需要 user 跑 `docker compose up -d hostapi` 才能生效. 现在生产环境仍是 11 tool.

---

### ✅ 修前端 stub (48-26)
**问题**: 多页面 mock 数据, 不是用户真数据:
- `TodayDashboard.jsx:142` — "上周 5 天按时吃药" 硬编码
- `NewMedication.jsx:317` — `Math.random() * 35` 60-95 随机数
- `getMedicationsHistory()` 整个函数 return 硬编码 7 天数组

**修复**:
- `healthApi.js` 重写 `getMedicationsHistory(params)`: 并发拉 `GET /medication-reminders?date=YYYY-MM-DD` 每一天, 聚合 taken 数, 算 rate
- `param.detail=true` 返回明细列表 (历史表格用)
- `TodayDashboard.jsx` `weekSummary` 用真 rate (≥80% 算按时)
- `NewMedication.jsx` fetchHistory 加 `detail: true`

**验证 (浏览器 `/v2/medication` 本周 tab)**:
- 周四 0%, 周五 0%, **周六 25%** (橙色条, 真 taken), 周日 0%, **周一 50%** (深蓝条), 周二 0%, 今日 (空)
- 跟 DB `reminder_logs` 实际记录一致 (周一 4/8 = 50%, 周六 2/8 = 25%)

---

## 三、智能体能力面 (4 agents + 18 tools)

### HealthAdvisor (HealthAdvisorV2) — 18 MCP tools
| Tool | 文件 | 描述 |
|---|---|---|
| `analyze_symptoms` | diagnosis_tool | 症状分析 (含历史) |
| `get_disease_info` | diagnosis_tool | 疾病信息查询 |
| `generate_health_assessment` | diagnosis_tool | 健康评估生成 |
| `ai_medical_diagnosis` | diagnosis_tool | AI 医疗诊断 |
| `save_consultation` | database_tool | 保存咨询记录 ← **当前 stub SKIP** |
| `get_consultation_history` | database_tool | 查咨询历史 ← **当前 stub SKIP** |
| `search_symptom_info` | knowledge_tool | 知识库搜症状 |
| `search_medication_info` | knowledge_tool | 搜药品信息 |
| `get_health_tips` | knowledge_tool | 健康小贴士 (deprecated) |
| `analyze_health_concern` | knowledge_tool | 综合健康分析 |
| `upsert_medical_kb_document` | knowledge_tool | 知识库 upsert |
| `delete_medical_kb_document` | knowledge_tool | 知识库删除 |
| `list_medical_kb_documents` | knowledge_tool | 知识库列表 |
| `get_medication_overview` | a2a_integration_tool | A2A 调 MedicationAgent ← **当前 stub SKIP** |
| `get_visit_summary_overview` | a2a_integration_tool | A2A 调 VisitSummaryAgent ← **当前 stub SKIP** |
| `aggregate_health_report` | a2a_integration_tool | 整合 health_records ← **当前 stub SKIP** |
| `get_health_records_history` | a2a_integration_tool | 体检历史 ← **当前 stub SKIP** |
| `generate_consultation_summary` | a2a_integration_tool | 咨询摘要 ← **当前 stub SKIP** |

**Active (11)**: knowledge_tool 6 + diagnosis_tool 4 + upsert_medical_kb... 等于 4 + 6 + 1 (memory_integration 0) = 11.
**修复后 (18)**: 加 a2a_integration (5) + database (2) = +7 → 18.

### HealthRecords — N/A (用 PhaCore shared tools)
### MedicationReminder — N/A (用 PhaCore shared tools)
### VisitSummary — N/A (用 PhaCore shared tools)

---

## 四、还没做的工作

### 🔴 高优先级

1. **重启 hostapi** — 验证 18 tool 全加载
2. **AI 浮窗 session_id** — 多轮对话无上下文, 每发一次是新 session
   - 改 `ChatProvider` 维护 threadId, 调 `/api/copilotkit` 时传 messages[]
   - 后端 checkpointer (`langgraph-checkpoint-postgres`) 已经支持 thread_id
3. **写 E2E test** — 验证 AI 真调 tools, e.g.:
   - "我血压偏高怎么办" → AI 应该调 `analyze_symptoms`
   - "我的体检报告" → AI 应该调 `get_health_records_history`
   - "今天吃什么药" → AI 应该调 `get_medication_overview`
4. **其他 3 个 agent 验证** — 现在只确认 HealthAdvisor, health_records / medication_reminder / visit_summary 的 tool 数量同样需要 audit

### 🟡 中优先级

5. **清理 mock 数据**:
   - `HealthHeader.jsx` `mockNotifications = []` 空数组 — 应该在 useEffect 调真实通知 endpoint
   - `NewMedication.jsx` fetchWeek fallback — 仅当 real API 返空时触发, 但可优化
6. **浮窗 Markdown 渲染** — AI 输出 plain text, 没有 `**bold**` / 表格 / 列表渲染
7. **浮窗 quick action chips** — "今天吃什么药" "帮我看体检报告" 已硬编码在 Dashboard, 浮窗也应该有这 3 个示例
8. **`emergency_tool` / `reminder_tool` 在 HealthRecords / MedicationReminder** — 这些 agent 自己的 tool 也需要 audit 18→? 同样问题
9. **PhaCore 真共享** — `load_phacore_tools(modules=("ocr",))` 现在只能 on-demand load, OCR pipeline 没真接进 4 个 agent

### 🟢 低优先级 (Polish)

10. **Makefile / 部署脚本** — 启动 hostapi 健康检查不是 composition-managed, 偶尔需要手动 restart
11. **rate_limit tuning** — log 里 `llm_qps=30, user_rpm=60` 也许调整 (高峰 QPS 高时 AI 会排队)
12. **错误 UI** — 浮窗 `[错误] xxx` 直接 print 出来, 不友好. 应该弹个 toast
13. **`/api/copilotkit` 需要 admin endpoint** — 当前仅接受 user token, 没法 admin 调
14. **mcp-loader cache** — `_TOOL_CACHE` 内存级, 多进程没共享. 改 Redis cache
15. **`StageLang` middleware Tailwind 化** — 后端 log 出现 `WARNING: A2AServer.v2.MCP_tool_adapter ...`, 全是中文 Unicode 错误日志, 应该换英文

---

## 五、验证清单 (User 启动后自检)

```bash
# 1. 重启 hostapi
docker compose -f I:/A2A/3/A2AServer/docker-compose.yml up -d hostapi

# 2. 看 log, 应该看到 "loaded 18 tools"
docker logs a2aserver-hostapi-1 --tail 50 | grep "loaded"
# 期望: [mcp_tool_adapter:http] agent=health_advisor loaded 18 tools via http://127.0.0.1:9101

# 3. 浏览器测试
# 登录 → /v2/dashboard → 点右下 AI 按钮 → 输入 "我今天该吃什么药"
# AI 应该调 get_medication_overview → 显示完整用药列表 (不是 fallback stub)
```

---

## 六、关键文件清单

```
# 后端
backend/A2AServer/src/A2AServer/v2/
├── v2_agent.py                    recursion_limit, debug 日志
├── mcp_discover.py                AST 静态发现, 路径定位
├── mcp_tool_adapter.py            3-tier transport (http/stdio/inprocess), SKIP_TOOLS
├── sub_agents.py                  4 agent class 注册
├── v2_runtime.py                  Checkpointer, middleware
└── rate_limit.py                  QPS / RPM 控制

frontend/hostAgentAPI/
├── copilotkit_runtime.py          AG-UI ←→ /v2/chat/stream 翻译
├── server.py                      FastAPI 入口
├── api.py                         业务路由 (medication-reminders, health-records, …)
└── requirements.txt               + langchain-mcp-adapters (48-26 修复)

# 前端
frontend/multiagent_front/src/
├── App.jsx                        <ChatProvider> + 路由
├── components/
│   ├── ChatPanel.jsx              自写 AI 浮窗 UI
│   └── useChat.jsx                自写 SSE store (Context + useReducer)
├── api/
│   └── healthApi.js               + getMedicationsHistory 重写 (48-26)
└── pages/
    ├── TodayDashboard.jsx         + weekSummary 真数据
    └── NewMedication.jsx          + fetchHistory detail=true
```

---

## 七、相关 log 锚点

| Log | 含义 |
|---|---|
| `[mcp_discover] agent=health_advisor found 18 MCP tools in 5 files` | 真 tool 数 |
| `[mcp_tool_adapter] agent=health_advisor loaded 11 tools` | 当前激活 (含 7 个被 SKIP) |
| `[mcp_tool_adapter:http] agent=health_advisor load失败: No module named 'langchain_mcp_adapters'` | 修复前根因 |
| `[mcp_tool_adapter:stdio] agent=health_advisor 加载失败: No module named 'langchain_mcp_adapters'` | 同上 |
| `[v2_agent:trace] USING messages mode, recursion_limit=100` | 已修复 debug 日志 |
| `Response POST /v2/chat/stream status=200 elapsed_ms=315` | 单次 chat 端到端耗时 (315ms 健康) |
