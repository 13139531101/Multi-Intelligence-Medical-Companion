# 个人智能健康助手 (Personal Health Assistant)

> 🤖 基于 **LangChain 1.x + LangGraph 1.x + A2A + MCP + ANP** 五协议生态
> 📊 4 个 sub-agent + 36 工具 + PostgresSaver + AgentRegistry 装饰器
> 🌐 支持 A2A (企业内) + MCP (工具) + ANP (跨组织 agent 互联网)

## 🚀 v2.0 当前状态 (2026-08-15)

**最新**：v2.0-stage37（**Stage 3 知识图谱 + 动态 Skills/MCP 重构完成**）

### ✅ 核心能力

| 能力 | 阶段 | 说明 |
|------|------|------|
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

### 📊 HTTP 端点（共 30+）

- `/smart_chat` - 主入口（v2 LangGraph 编排）
- `/v2/agents/status` - 所有 sub-agent 状态（阶段30）
- `/v2/agents/{name}/status` - 单 agent 详情（阶段30）
- `/v2/models/{chat,providers,stats,test-fallback}` - 多模型（阶段24）
- `/v2/rag/*` (5) - RAG 索引/检索/反馈
- `/v2/oauth/*` (7) - OAuth2 + JWT
- `/v2/audit/*` (4) - 写操作审计
- `/anp/agent/{ad.json,interface.json,rpc}` - ANP 协议（阶段33）
- `/anp/agents` - 列出所有 PHA agent（带 DID:WBA）
- `/health` + `/metrics` + `/health/deep` - 监控

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
| 前端 - 用户端 | 30/100 | **缺 Web 聊天界面** |
| 文档完整度 | 60/100 | 11+ 文档待更新 |
| 监控/日志 | 50/100 | 缺 Grafana + Loki |
| 商业化 | 20/100 | 无付费/会员 |
| **综合** | **65/100** | **技术就绪，产品待补** |

**最快可演示**：1 周（补 Web UI + 文档）
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
    - **MCP 工具:** `OCRTool`, `DataExtractionTool`, `StorageTool`

2.  **健康顾问 (HealthAdvisor):**

    - **职责:** 与用户直接交互，回答健康咨询，提供初步建议。
    - **MCP 工具:** `DiagnosisTool`, `KnowledgeTool`

3.  **用药提醒助手 (MedicationReminder):**

    - **职责:** 管理用药计划、发送提醒、跟踪库存。
    - **MCP 工具:** `ReminderTool`, `NotificationTool`

4.  **就诊摘要生成器 (VisitSummaryGenerator):**
    - **职责:** 整合信息，生成就诊摘要和医疗文档分析。
    - **MCP 工具:** `DocumentTool`, `AIAnalysisTool`

### MCP 工具 (核心功能):

#### 健康档案管理工具:

- **`OCRTool`:** 调用阿里云 OCR 服务，识别医疗文档中的文字信息。
- **`DataExtractionTool`:** 从 OCR 文本中提取结构化的医疗信息（患者信息、诊断、药物等）。
- **`StorageTool`:** 安全加密存储健康档案数据到本地数据库。

#### 健康咨询工具:

- **`DiagnosisTool`:** 提供基于症状的健康分析和建议。
- **`KnowledgeTool`:** 医疗知识库查询和健康知识问答。

#### 用药管理工具:

- **`ReminderTool`:** 创建和管理用药提醒计划。
- **`NotificationTool`:** 发送用药提醒和复诊通知。

#### 文档分析工具:

- **`DocumentTool`:** 医疗文档解析和处理。
- **`AIAnalysisTool`:** 智能分析和就诊摘要生成。

#### 信息检索工具:

- **`SearchTool`:** 深度搜索医疗资讯和研究报告。
- **`RAGTool`:** 智能检索和资料查找。

## 🚀 下一步开发计划 (2026-Q4)

| Phase | 内容 | 状态 |
|-------|------|------|
| PHASE 1 | HITL + 主动询问澄清 | ✅ 已完成 |
| PHASE 2 | Agentic RAG Stage 1 | ✅ 已完成 |
| PHASE 3 | ReAct 反思模式 | ✅ 已完成 |
| PHASE 4 | Agentic RAG Stage 2 多跳检索 | ✅ 已完成 |
| PHASE 5 | Agentic RAG Stage 3 知识图谱 | ✅ 已完成 |
| **PHASE 6** | **动态工具选择** | **🔜 下一步** |
| PHASE 7 | 语义缓存优化 | ⏳ |
| PHASE 8 | 推理过程可视化 | ⏳ |
| PHASE 9 | vLLM 部署 + PhaCore 重构收尾 | ⏳ |

---

_本项目基于 A2A-MCP Server 框架进行开发。_
