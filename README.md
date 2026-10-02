# 个人智能健康助手 (Personal Health Assistant)

> 🤖 基于 **LangChain 1.x + LangGraph 1.x + A2A + MCP + ANP** 五协议生态
> 📊 4 个 sub-agent + 39 个 MCP 工具 + PostgresSaver + AgentRegistry 装饰器
> 🌐 支持 A2A (企业内) + MCP (工具) + ANP (跨组织 agent 互联网)

## 🚀 v2.0 当前状态 (2026-10-02)

**最新**：v2.0-phase48（**CRAG 纠正式检索 + 迭代 ReAct 反思 + AI 操控页面**）

### ✅ 核心能力

| 能力 | 阶段 | 说明 |
|------|------|------|
| **AI 操控页面（AG-UI）** | 48 | AI 直接跳转到某份档案并打开详情，见下文 |
| **CRAG 纠正式检索** | 48 | 检索质量自评 → 不合格则改写重查/转网络搜索 |
| **A2A + MCP + ANP 三协议** | 33 | agent 跨组织/跨云互联 |
| **多 agent 并行编排** | 30 | 4 agent 同时跑 + worker 状态查询 |
| **AgentRegistry 装饰器** | 31 | 加 agent = 1 个 class，其他全自动 |
| **PostgresSaver 持久化** | 30 | state 写入 PostgreSQL，崩溃恢复 |
| **LangGraph StateGraph** | 28-29 | LangChain 1.x + LangGraph 1.x |
| **RAG Stage 1-3** | 34-37 | 多跳检索 + 知识图谱 + 实体关系 |
| **ReAct + Critique 反思** | 36 | 反思模式 + Skills 动态注入 |
| **动态 Skills/MCP** | 37 | `skills/` + `mcp/` 目录 YAML 动态加载 |
| **OAuth2 + JWT** | 24 | GitHub OAuth + JWT 双 token + 轮转 + 限流 |
| **多模型协同** | 24 | DeepSeek + Qwen + Claude + Local（路由 + fallback） |
| **CI/CD** | 24 | GitHub Actions：test + lint + build + release |
| **写操作审计** | 24 | 5 端点 |
| **3 层限流** | 24 | 全局 + user + agent |

## 🧰 技术栈

### 后端

| 层 | 选型 | 用途 |
|----|------|------|
| **编排** | LangChain 1.x + LangGraph 1.x | StateGraph 多节点编排、条件路由、HITL 中断 |
| **状态持久化** | PostgresSaver (`langgraph-checkpoint`) | 图状态落 PostgreSQL，进程崩溃后可恢复 |
| **协议层** | A2A（agent↔agent）· MCP（agent↔工具）· AG-UI（agent↔用户）· ANP（跨组织） | 四协议分层，各自解耦 |
| **工具层** | FastMCP + `langchain-mcp-adapters` | 每个 agent 一个独立 MCP server；另有 AST 静态扫描作为冷启动兜底 |
| **Web** | FastAPI + Uvicorn | HTTP + SSE 流式；含 OAuth2/JWT、三层限流、写操作审计 |
| **数据库** | PostgreSQL 16 + pgvector（`pgvector/pgvector:pg16`） | 业务表 + 向量检索（`rag_chunks.embedding vector(384)` + ivfflat 索引） |
| **缓存** | Redis 7 | 会话记忆（`langchain_memory`）与热点数据缓存 |
| **LLM** | `deepseek-chat` · `qwen-plus` / `qwen-vl-plus`（DashScope）· `gpt-4o-mini` · `claude-3-5-haiku` | 多模型路由 + 自动 fallback |
| **Embedding / Rerank** | DashScope `text-embedding-v4` · `gte-rerank-v2` | **全部走云端 HTTP API，不在本地部署模型**；rerank 失败自动降级不阻塞 |
| **OCR** | 阿里云 OCR（`alibabacloud-ocr-api`） | 检查单/处方单图片文字识别 |
| **检索增强** | CRAG 纠正式 RAG + 知识图谱 | 检索质量自评 → 不合格则改写重查或转网络搜索（DuckDuckGo） |
| **可观测** | Prometheus · Grafana 11 · Loki 3.2 · Promtail | 指标采集 + 日志聚合 + 可视化面板 |
| **加密** | `cryptography`（Fernet） | 健康档案正文加密存储 |

### 前端

| 层 | 选型 | 用途 |
|----|------|------|
| **框架** | React 18 + Vite | SPA |
| **UI** | MUI 5 + Emotion | 组件库与主题 |
| **路由 / 状态** | React Router 6 · Recoil | 页面路由与全局状态 |
| **协议** | `@microsoft/fetch-event-source` · CopilotKit 1.63 | 消费 AG-UI 事件流（SSE） |
| **其他** | dayjs · react-markdown · react-dropzone · crypto-js | 时间处理 / 富文本 / 上传 / 前端加密 |

### 部署

Docker Compose 编排 13 个容器：

| 容器 | 角色 |
|------|------|
| `hostapi` | 网关 + AG-UI 端点 + v2 编排（LangGraph） |
| `health_advisor` / `health_records` / `medication_reminder` / `visit_summary` | 4 个 A2A agent server，各自独立 MCP |
| `multiagent_front` | 用户端（Nginx + Vite 产物） |
| `admin_backend` / `admin_frontend` | 管理端 |
| `postgres` (pgvector) · `redis` | 数据与缓存 |
| `loki` · `grafana` · `promtail` | 日志聚合与可视化 |

### 📊 HTTP 端点（共 30+）

- `/smart_chat` - 主入口（v2 LangGraph 编排）
- `/v2/chat/stream` - v2 SSE 事件流（routing / tool_call / chunk / **page_update** / done）
- `/api/copilotkit` - **AG-UI 端点**：把上面的 SSE 翻译成 AG-UI 事件（TEXT_MESSAGE_* / TOOL_CALL_* / PAGE_UPDATE / RUN_*），前端聊天浮窗走这里
- `/v2/agents/status` - 所有 sub-agent 状态（阶段30）
- `/v2/agents/{name}/status` - 单 agent 详情（阶段30）
- `/v2/models/{chat,providers,stats,test-fallback}` - 多模型（阶段24）
- `/v2/rag/*` (5) - RAG 索引/检索/反馈
- `/v2/oauth/*` (7) - OAuth2 + JWT
- `/v2/audit/*` (4) - 写操作审计
- `/anp/agent/{ad.json,interface.json,rpc}` - ANP 协议（阶段33）
- `/anp/agents` - 列出所有 PHA agent（带 DID:WBA）
- `/health` + `/metrics` + `/health/deep` - 监控

### 🖱️ AI 操控页面（AG-UI）

多数「AI + 前端」项目止步于把回答渲染成文字。本项目让 **AI 直接操作页面**：
用户说「打开上个月的血常规报告」，AI 会自己跳转到档案页并弹出那条记录的详情。

```
用户提问
   └─ MCP 工具 open_health_record(query, month)
        └─ 命中记录 → 返回 page_update.actions[]
             ├─ {component: "PageRouter",        action: "navigateTo"}  ← 跳页
             └─ {component: "HealthRecordsPage", action: "openRecord"}  ← 开详情
                  └─ bridge 扇出 → SSE page_update → AG-UI → 前端组件注册表
```

三个设计要点：

- **导航与操作分离成两条动作。** 跳页时目标页还没挂载，操作必然落空。
  所以前端组件注册表带一个**有界待执行队列**（TTL 10s / 上限 20 / 按签名去重）：
  未注册的动作先入队，等组件挂载时再排空执行一次。
- **`PageRouter` 常驻挂载。** 它渲染 `null` 但始终在 `<Router>` 内，因此无论
  用户停在哪个页面，`navigateTo` 都能立即生效——解决了聊天浮窗挂在 `<Router>`
  之外、拿不到 `useNavigate` 的问题。
- **一次工具调用可返回多个动作。** `page_update.actions[]` 按序扇出，同时兼容
  旧的单动作写法。

配套修复（阶段48）：

- **MCP 返回值解包。** 同一工具走 in-process 路径返回 `dict`，走 MCP 路径返回
  `[{"type":"text","text":"<json>"}]`。此前只认前者，导致 MCP 通路下工具明明
  返回了 `page_update` 却被静默丢弃——表现为「档案找到了，但页面不跳」。
- **存在性提问也走检索。** 「有没有心电图检查报告」过去不触发档案检索，退到
  向量库（正文加密、未入库）必然答「未找到」。现在工具同时覆盖导航类与存在性
  提问，并把「有没有/吗/我做过/在吗」等虚词纳入关键词化简。

### 🏷️ Tag 历史

```
v2.0-stage37-refactor           ← 最新 动态 Skills/MCP 目录重构
v2.0-stage36-react              ← ReAct + Critique 反思模式
v2.0-stage35kg                  ← 知识图谱 + 实体关系抽取
v2.0-stage34                    ← 多跳 RAG Hop1/Hop2 合并
v2.0-stage33-anp                ← ANP 协议集成
v2.0-stage30-orchestration      ← 多 agent 并行 + PostgresSaver
v2.0-stage29-flow
v2.0-stage28-e2e
v2.0-stage28-langgraph
v2.0-stage24
... 共 37 个 v2.0 tag 全部推送
```

### 📈 距完整产品差距

详见 [PHASE_STATUS_PRODUCT.md](PHASE_STATUS_PRODUCT.md)

| 维度 | 得分 | 关键缺口 |
|------|------|----------|
| 后端技术 | 95/100 | 几乎完成 |
| 前端 - 用户端 | 70/100 | 已有聊天浮窗 + Dashboard + 档案页 + AI 操控页面；缺移动端适配 |
| 文档完整度 | 60/100 | 11+ 文档待更新 |
| 监控/日志 | 50/100 | 缺 Grafana + Loki |
| 商业化 | 20/100 | 无付费/会员 |
| **综合** | **70/100** | **技术就绪，产品待补** |

**最快可演示**：3 天（补文档 + 走查）
**可上线内测**：2 周（+ 监控/告警/ANP 签名）
**可商业化**：4-6 周（+ 压测/安全/付费/多租户）

---

## 📖 项目愿景

本项目旨在打造一个私密、智能、贴心的个人健康管理助手。通过利用先进的 AI 技术（多智能体、RAG、OCR），我们将用户的个人病历、检查报告、用药记录等信息，安全地整合为一个个人健康知识库。在此基础上，系统提供从日常健康咨询、用药提醒到辅助就医沟通的全方位智能服务，成为用户值得信赖的健康伙伴。

**核心理念：** 本项目是一个**辅助性**的健康管理工具，**不提供、也绝不替代**任何形式的医疗诊断、治疗建议。所有输出内容仅供参考，用户在做出任何医疗决策前，必须咨询专业医生。

## 核心功能

### 1. 个人健康知识库构建

- **多模态信息录入:** 支持用户通过拍照（OCR 识别）、上传文件（PDF, Word, 图片）或手动输入的方式，将纸质或电子版的病历、化验单、检查报告、处方单等信息录入系统。
- **结构化数据处理:** 系统自动提取关键信息（如诊断名称、检查指标、药物名称、用法用量），并将其结构化存储。
- **安全私密的存储:** 所有个人健康数据都将进行加密存储，确保用户隐私安全。

### 2. 智能健康咨询

- **症状初步问询:** 当用户感到不适时，可以向智能体描述症状。智能体将基于用户的个人健康知识库（过往病史、过敏史等），提出一些可能的缓解建议（如多喝水、注意休息），并**强烈建议**用户及时就医。
- **健康知识问答:** 解答用户关于常见疾病、药物作用、健康生活方式等方面的一般性问题。

### 3. 辅助就医与医患沟通

- **生成“就诊前摘要”:** 在用户去看医生前，系统可以自动生成一份简洁的摘要，包括：
  - 近期主要不适症状的描述。
  - 智能体与用户近期的对话要点（用户主诉和智能体的初步建议）。
  - 完整的个人过往病史、手术史、过敏史列表。
  * 关键检查的历史结果回顾。
- **方便医生快速了解情况:** 患者可以将这份摘要出示给医生，帮助医生在短时间内全面了解患者的健康状况和近期问题，提升沟通效率。

### 4. 贴心的用药与复诊提醒

- **智能用药管家:**
  - 根据处方自动创建服药提醒（每日多次、特定时间）。
  - 记录每次服药情况，生成服药依从性报告。
- **药品库存预警:**
  - 根据处方和用药天数，提前提醒用户药品即将用完，建议及时复诊或购药。
- **复诊提醒:**
  - 根据医嘱或常规健康检查周期，设置并发送复诊提醒。

## 🤖 智能体与 MCP 工具设计

### 智能体角色:

#### 核心健康智能体:

1.  **健康档案管理员 (HealthRecordsManager):**

    - **职责:** 负责处理所有健康数据的录入、解析和存储。
    - **MCP 工具:** `OCRTool`, `DataExtractionTool`, `StorageTool`, `PageControlTool`, `ReminderTool`

2.  **健康顾问 (HealthAdvisor):**

    - **职责:** 与用户直接交互，回答健康咨询，提供初步建议。
    - **MCP 工具:** `DiagnosisTool`, `KnowledgeTool`, `A2AIntegrationTool`

3.  **用药提醒助手 (MedicationReminder):**

    - **职责:** 管理用药计划、发送提醒、跟踪库存。
    - **MCP 工具:** `ReminderTool`, `NotificationTool`, `DrugSafetyTool`

4.  **就诊摘要生成器 (VisitSummaryGenerator):**
    - **职责:** 整合信息，生成就诊摘要和医疗文档分析。
    - **MCP 工具:** `DocumentTool`, `AIAnalysisTool`, `DatabaseTool`

### 工具加载与跳过

工具由 `mcp_discover` 从各 agent 的 `mcpserver/` 目录发现：优先走 MCP 子进程（HTTP/stdio），
失败则退回 **AST 静态扫描**，因此宿主启动不依赖任何 agent 进程先就绪。

当前共声明 60 个工具，其中 **39 个可加载**。以下 5 个模块默认跳过（`mcp_tool_adapter.SKIP_TOOLS`），
因为它们会在 import 期建数据库连接或依赖外部 worker：

| 跳过的模块 | 原因 |
|---|---|
| `storage_tool` · `database_tool` | import 时即建 DB 连接 |
| `a2a_integration_tool` | 避免 agent 间循环调用 |
| `memory_integration_tool` | 记忆系统独立部署 |
| `async_analysis_tool` | 依赖外部 worker |

> ⚠️ 已知副作用：`storage_tool` 被跳过意味着档案读取一度只剩 `page_control_tool` 一条路。
> 该工具现已同时覆盖导航类与存在性提问，见上文「AI 操控页面」。

### MCP 工具 (核心功能):

#### 健康档案管理工具:

- **`OCRTool`:** 调用阿里云 OCR 服务，识别医疗文档中的文字信息。
- **`DataExtractionTool`:** 从 OCR 文本中提取结构化的医疗信息（患者信息、诊断、药物等）。
- **`StorageTool`:** 安全加密存储健康档案数据到本地数据库。
- **`PageControlTool`:** 检索用户档案并**操控前端页面**——跳转到档案页、打开指定记录的详情弹窗。导航类（"打开上个月的血常规报告"）与存在性提问（"有没有心电图检查报告"）都走它。返回体只带 id/标题/类型，不含档案正文。

#### 健康咨询工具:

- **`DiagnosisTool`:** 提供基于症状的健康分析和建议。
- **`KnowledgeTool`:** 医疗知识库查询和健康知识问答。

#### 用药管理工具:

- **`ReminderTool`:** 创建和管理用药提醒计划。
- **`NotificationTool`:** 发送用药提醒和复诊通知。

#### 文档分析工具:

- **`DocumentTool`:** 医疗文档解析和处理。
- **`AIAnalysisTool`:** 智能分析和就诊摘要生成。

#### 信息检索:

检索不在 MCP 工具层，而是 v2 编排图内的独立节点（`v2/rag.py` + `v2/crag/`）：

- **向量检索:** pgvector 相似度检索（`rag_chunks`），多跳合并 Hop1/Hop2。
- **知识图谱:** `kg_entities` / `kg_relations` 实体关系扩展召回。
- **CRAG 纠正:** 检索结果自评质量，不合格则改写 query 重查，仍不合格转网络搜索。
- **网络搜索:** DuckDuckGo（`v2/crag/web_search.py`），作为兜底来源。

## 🚀 后续计划

### ✅ 已完成里程碑

| 阶段 | 内容 |
|------|------|
| 24 | OAuth2/JWT 双 token + 轮转、多模型路由、三层限流、写操作审计 |
| 28-29 | LangGraph StateGraph 重构（LangChain 1.x + LangGraph 1.x） |
| 30 | 多 agent 并行编排 + PostgresSaver 持久化 |
| 31 | AgentRegistry 装饰器（加 agent = 1 个 class） |
| 33 | ANP 协议集成 |
| 34-37 | RAG Stage 1-3：多跳检索 + 知识图谱 + 动态 Skills/MCP |
| 36 | ReAct + Critique 反思模式 |
| **48** | **CRAG 纠正式检索 · 迭代 ReAct 反思 · AI 操控页面（AG-UI）** |

### 🔧 近期：质量与技术债（1-2 周）

按优先级排列，均为已定位、有明确复现路径的问题：

| # | 事项 | 说明 |
|---|------|------|
| 1 | **修复 prompt 解析** | `_load_prompt` 按固定顺序探测并返回首个命中文件，而 Dockerfile 只 COPY 了其中一个 agent 的 prompt → 容器里四个 agent 实际共用 HealthRecordsManager 的 prompt，各自的兜底文案从未生效 |
| 2 | **CI 门禁真正生效** | `verify_stage1.py` 没有 `sys.exit(1)`，失败也返回 0，`continue-on-error: false` 形同虚设；stage3/25 会真调 LLM，需改为 mock 或注入假响应 |
| 3 | **多轮对话上下文** | 目前每轮基本独立，指代（"那份"、"上次那个"）无法消解 |
| 4 | **档案写入幂等** | 心电图 / 血常规 / 体检报告等各存在重复行，写入路径缺去重 |
| 5 | **清理死代码与仓库杂物** | 未被引用的组件契约常量、被聊天浮窗完全遮挡的 FAB 按钮、硬编码的 localhost 地址 |
| 6 | **工具结果截断** | 序列化上限 20000 字符，超限会静默破坏下游 JSON 解析（`v2_agent.py:564`）；LLM 摘要路径每条只取前 300 字符（`bridge.py:573`） |

### 📈 中期：产品化（2-6 周）

| 事项 | 说明 |
|------|------|
| **移动端适配** | 当前仅桌面端布局 |
| **监控告警** | Grafana/Loki/Promtail 已部署，缺告警规则与通知渠道 |
| **压测与性能基线** | 建立并发/延迟基线，定位数据库连接池与 MCP 冷启动瓶颈 |
| **多租户与数据隔离** | 当前单租户；需行级隔离 + 审计强化 |
| **付费 / 会员体系** | 无商业化能力 |

### 🔭 长期方向

- **多模态理解**：检查报告图像直接理解，减少 OCR → 结构化的信息损耗
- **可穿戴设备接入**：心率/血压/睡眠数据流式入库，驱动主动健康提醒
- **医生端 / 家属端**：就诊摘要的双向流转，从"患者自用工具"扩展为"医患沟通介质"

---

_本项目基于 A2A-MCP Server 框架进行开发。_
