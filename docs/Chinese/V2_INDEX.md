# PHA v2 文档总索引

> **PHA v2 完整交付文档**
> 5 阶段 90/90 验收通过 · 9 个 tag 全部推送 · 生产就绪

---

## 🚀 30 秒快速开始

```bash
# 1. 配置 .env
DEEPSEEK_API_KEY=sk-xxx

# 2. 跑验收（确保一切正常）
cd i:\A2A\3\A2AServer
python scripts/verify_stage5.py  # 20/20

# 3. 启动服务
python frontend/hostAgentAPI/server.py     # 10010 端口
python -m A2AServer.v2.a2a_sdk_server     # 10020 端口

# 4. 测一下
curl -X POST http://localhost:10010/message/send \
  -H "X-Use-V2: true" -H "Content-Type: application/json" \
  -d '{"params":{"message":{"role":"user","parts":[{"text":"我头疼"}]}}}'
```

---

## 📚 文档目录

### 🎯 所有人必读

| 文档 | 时长 | 适合谁 |
|------|------|-------|
| **[V2_ARCHITECTURE.md](V2_ARCHITECTURE.md)** | 10 min | 所有人（架构总览 + 架构图）|
| **[V2_INDEX.md](V2_INDEX.md)** | 2 min | 所有人（本文档）|

### 👨‍💻 开发者

| 文档 | 时长 | 内容 |
|------|------|------|
| **[V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md)** | 20 min | 开发环境、新增 Agent/工具、调试技巧 |
| **[V2_API_REFERENCE.md](V2_API_REFERENCE.md)** | 15 min | 完整 API 文档（HTTP + a2a-sdk + Python SDK）|

### 🚀 运维 / SRE

| 文档 | 时长 | 内容 |
|------|------|------|
| **[V2_OPERATIONS.md](V2_OPERATIONS.md)** | 15 min | 部署、监控、灰度切流、回滚预案 |

### 🔄 接棒者

| 文档 | 时长 | 内容 |
|------|------|------|
| **[V2_MIGRATION_NOTES.md](V2_MIGRATION_NOTES.md)** | 15 min | 从 v1 迁移、兼容性矩阵、风险评估 |

---

## 📊 阶段完成度

| 阶段 | 内容 | 验收 | Tag |
|------|------|------|-----|
| 1 | 依赖升级 + 可观测基础 | 12/12 ✅ | v2.0-stage1 |
| 2 | V2Agent 入口 | 12/12 ✅ | v2.0-stage2 |
| 2.1 | langgraph 1.0 兼容性修复 | - | v2.0-stage2.1 |
| 2.2 | DeepSeek 端到端跑通 | - | v2.0-stage2.2 |
| 2.5 | **36 个真实 MCP 工具接入** | 14/14 ✅ | v2.0-stage2.5 |
| 3 | **HostGraph LangGraph 编排** | 21/21 ✅ | v2.0-stage3 |
| 4 | v2 接入 hostAgentAPI（灰度路由）| 11/11 ✅ | v2.0-stage4 |
| 5 | **a2a-sdk 0.3.x 协议升级** | 20/20 ✅ | v2.0-stage5 |
| **合计** | **6 个阶段** | **90/90** | **9 个 tag** |

---

## 🎯 v2 vs v1 核心差异

| 维度 | v1 | v2 | 提升 |
|------|----|----|------|
| 智能体框架 | 手写 BasicAgent (1800 行) | LangChain 1.0 create_agent | **-72%** |
| 编排 | 3 层 if/else | LangGraph 1.0 StateGraph | **可观测** |
| 工具接入 | 18 个 MCP 工具 | **36 个真实 MCP 工具** | **+100%** |
| 路由 | 隐式 if/else | 显式 StateGraph 节点 | **可恢复** |
| 协议 | PHA 私有 | a2a-sdk 0.3.x 标准 | **标准化** |
| 状态管理 | 内存 | InMemorySaver / PostgresSaver | **可持久化** |
| 接入 | 单一入口 | v1/v2 灰度 + fallback | **可灰度切流** |

---

## 🔑 关键能力

### 4 个智能体

| Agent | 工具数 | 业务领域 |
|-------|--------|----------|
| HealthAdvisorV2 | 11 | 症状咨询、AI 诊断、疾病信息、健康评估 |
| HealthRecordsV2 | 11 | OCR 识别、文档解析、档案管理、用药提醒 |
| MedicationReminderV2 | 8 | 药物互作、用药通知、复诊提醒 |
| VisitSummaryV2 | 6 | 健康趋势分析、就诊摘要生成 |

### 36 个 MCP 工具

跨 4 个 backend 业务模块，所有工具通过 `@mcp.tool()` 装饰器声明，**自动发现**。

### 3 层路由

1. **Layer 1**: `metadata.selected_agent` 显式指定
2. **Layer 2**: 关键词启发（中文 + 英文）
3. **Layer 3**: LLM 委派（DeepSeek）—— 兜底

### 双协议入口

- **hostAgentAPI (10010)**: PHA 私有协议，**前端零修改**
- **a2a-sdk Server (10020)**: a2a-sdk 0.3.x 标准 JSON-RPC 2.0

### 灰度切流

- Header: `X-Use-V2: true` / `X-PHA-Version: v2`
- 环境变量: `PHA_USE_V2=true`（全量切流）
- **失败自动 fallback v1**

---

## 📦 模块结构

```
backend/A2AServer/src/A2AServer/v2/
├── __init__.py             # 包入口
├── v2_runtime.py           # LangChain 1.x 探测 + Checkpointer
├── v2_agent.py             # V2Agent 基类
├── sub_agents.py           # 4 个子 Agent
├── mcp_discover.py         # AST 扫描 + 动态加载
├── mcp_tool_adapter.py     # MCP 工具 → BaseTool
├── host_graph.py           # LangGraph StateGraph
├── bridge.py               # A2A 灰度路由
├── a2a_sdk_compat.py       # PHA ↔ a2a-sdk 协议转换
└── a2a_sdk_server.py       # a2a-sdk 标准 FastAPI server
```

---

## 🧪 验收脚本

```bash
python scripts/verify_stage1.py     # 阶段1：依赖 + 可观测 (12/12)
python scripts/verify_stage2.py     # 阶段2：V2Agent 入口 (12/12)
python scripts/verify_stage2_5.py   # 阶段2.5：36 个真实 MCP 工具 (14/14)
python scripts/verify_stage3.py     # 阶段3：HostGraph (21/21)
python scripts/verify_stage4.py     # 阶段4：v2 接入 hostAgentAPI (11/11)
python scripts/verify_stage5.py     # 阶段5：a2a-sdk 协议 (20/20)
python scripts/discover_mcp_tools.py  # 静态扫描 63 个 MCP 工具

# 单测脚本
python scripts/discover_mcp_tools.py  # 工具发现
```

---

## 🌐 服务地址

| 服务 | 端口 | 启动命令 |
|------|------|---------|
| hostAgentAPI (主入口) | 10010 | `python frontend/hostAgentAPI/server.py` |
| a2a-sdk Server (标准) | 10020 | `python -m A2AServer.v2.a2a_sdk_server` |
| Admin Backend | 8000 | `python frontend/adminBackend/app.py` |
| Admin Frontend | 3002 | `cd frontend/adminFrontend && npm start` |
| PostgreSQL | 5432 | `docker compose up -d postgres` |

---

## 🔧 关键环境变量

```bash
# 必须
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx  # 可同 DEEPSEEK
DATABASE_URL=postgresql://...

# v2 开关
PHA_USE_V2=false              # 默认 false（v1 路径）
PHA_LLM_MODEL=deepseek-chat   # 可改 gpt-4o
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 可选
PHA_A2A_SDK_PORT=10020
LANGSMITH_API_KEY=            # LangSmith 追踪
```

---

## 📅 版本

| 版本 | 状态 | Tag |
|------|------|-----|
| v1.0.0 / v1.0.1 | 稳定（旧）| v1.0.0, v1.0.1 |
| v2.0.0 | 稳定（新）| v2.0-stage1 → v2.0-stage5 |

---

## 💡 推荐阅读顺序

1. **[V2_ARCHITECTURE.md](V2_ARCHITECTURE.md)** - 先看架构图
2. **[V2_MIGRATION_NOTES.md](V2_MIGRATION_NOTES.md)** - 了解与 v1 差异
3. **[V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md)** - 学会开发
4. **[V2_OPERATIONS.md](V2_OPERATIONS.md)** - 学会部署
5. **[V2_API_REFERENCE.md](V2_API_REFERENCE.md)** - 学会调用

---

## 🤝 贡献

- GitHub: `13139531101/Multi-Intelligence-Medical-Companion`
- Gitee: `ma-jiahuichenzui222/Multi-Intelligence-Medical-Companion`
- 分支: `refactor/v2`（v2 重构主分支）
