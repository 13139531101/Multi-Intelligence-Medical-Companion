# PHA v2 文档总入口

> **PHA v2** = Personal Health Assistant 第二代
> 多智能体健康助理，基于 **LangChain 1.x + LangGraph 1.x + A2A + MCP + ANP** 五协议生态
>
> **当前状态**：✅ v2.0 生产就绪，**33 阶段 / 33 tag 全部完成**

---

## 1. 快速导航

### 1.1 按角色

| 角色          | 必读                                                                                        | 时间    |
| ------------- | ------------------------------------------------------------------------------------------- | ------- |
| 🆕 第一次接触 | [V2_INDEX.md](V2_INDEX.md) (本文) → [V2_ARCHITECTURE.md](V2_ARCHITECTURE.md)                | 30 分钟 |
| 👨‍💻 开发者     | [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) → [V2_API_REFERENCE.md](V2_API_REFERENCE.md) | 1 小时  |
| 🚀 运维       | [V2_OPERATIONS.md](V2_OPERATIONS.md) → [K8S_DEPLOY.md](K8S_DEPLOY.md)                       | 1 小时  |
| 📦 接棒者     | [V2_MIGRATION_NOTES.md](V2_MIGRATION_NOTES.md) → [CHANGELOG.md](CHANGELOG.md)               | 1 小时  |
| 📊 项目经理   | [V2_FINAL_REPORT.md](V2_FINAL_REPORT.md) → [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)       | 20 分钟 |

### 1.2 按任务

| 我想…             | 看这个                                                                         |
| ----------------- | ------------------------------------------------------------------------------ |
| 了解 v2 是什么    | [V2_ARCHITECTURE.md](V2_ARCHITECTURE.md) § 1                                   |
| 5 分钟跑起来      | [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 2                             |
| 看 33 阶段干了啥  | [CHANGELOG.md](CHANGELOG.md)                                                   |
| 部署到生产        | [V2_OPERATIONS.md](V2_OPERATIONS.md) § 3                                       |
| 部署到 K8s        | [K8S_DEPLOY.md](K8S_DEPLOY.md)                                                 |
| 学 K8s            | [K8S_DEPLOY.md](K8S_DEPLOY.md) § 2                                             |
| 加新工具/Agent    | [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 5（**AgentRegistry 装饰器**） |
| 调优性能          | [V2_OPERATIONS.md](V2_OPERATIONS.md) § 4                                       |
| 排查故障          | [V2_OPERATIONS.md](V2_OPERATIONS.md) § 5                                       |
| 看 API 文档       | [V2_API_REFERENCE.md](V2_API_REFERENCE.md)                                     |
| 用 ANP 跨组织互联 | [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 6（ANP）                      |
| 看历史进度        | [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)                                     |

---

## 2. v2 是什么

**PHA v2** 是个人健康助手的**第二次重构**。相比 v1：

| 维度          | v1                  | v2                               |
| ------------- | ------------------- | -------------------------------- |
| 智能体框架    | ADK + LangGraph 0.x | LangChain 1.x + LangGraph 1.x    |
| 协议          | PHA 私有            | **A2A + MCP + ANP + PHA** 四协议 |
| 工具          | 4 个（hardcoded）   | 36 个（自动发现）                |
| 性能          | 重复请求 109s       | 重复请求 2.8s（**-97%**）        |
| 部署          | docker-compose      | compose + K8s 双部署             |
| Agent 注册    | 硬编码 5+ 处        | **装饰器 1 处**（阶段31）        |
| 多 agent 编排 | 串行                | **并行**（阶段30）               |
| 状态持久化    | 进程内              | **PostgresSaver**（阶段30）      |
| 跨组织互联    | ❌                  | **ANP + DID:WBA**（阶段33）      |

---

## 3. 阶段 30-33 关键能力

### 阶段 30：多 agent 编排

- 4 个 sub-agent 并行执行
- `/v2/agents/status` 实时查询 worker 状态
- PostgresSaver 持久化 + 崩溃恢复

### 阶段 31：AgentRegistry 自动注册

- `@register_agent(...)` 装饰器
- 加新 agent = 1 个 class，其他全自动
- 详见 [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 5

### 阶段 33：ANP 协议集成

- `anp[api]>=0.8.8` SDK
- `/anp/agent/ad.json` Agent Description
- `/anp/agent/rpc` JSON-RPC 2.0
- 4 个 agent 自动获得 `did:wba:pha.local:*`
- 详见 [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 6

---

## 4. 三协议对比

| 协议    | 端点               | 适用场景                                           | 阶段       |
| ------- | ------------------ | -------------------------------------------------- | ---------- |
| **A2A** | `/a2a/*` (v1)      | 企业内 task 协作                                   | 旧版       |
| **MCP** | 各 MCP agent       | LLM 调工具                                         | 旧版       |
| **ANP** | `/anp/*` (hostapi) | 跨组织/跨云 agent 互联网                           | **阶段33** |
| **PHA** | `/smart_chat` (v2) | LangGraph StateGraph 编排                          | 阶段28+    |
| 监控    | log only           | Prometheus + 6 端点                                |
| 限流    | 无                 | 3 层（全局 + user + agent）                        |
| 文档    | 6 份               | 9 份（+K8S_DEPLOY + CHANGELOG + PROJECT_PROGRESS） |

### 2.1 核心组件

```
┌────────────────────────────────────────────────────────┐
│                  PHA v2 架构                           │
├────────────────────────────────────────────────────────┤
│                                                        │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│   │  用户     │───▶│ hostapi  │───▶│ V2Agent  │       │
│   │ (wechat/ │    │  路由    │    │  4 个    │       │
│   │  admin)  │    │          │    │  sub     │       │
│   └──────────┘    └──────────┘    └────┬─────┘        │
│                                          │              │
│                                          ▼              │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│   │ Postgres │◀──▶│  Redis   │    │ 36 MCP   │        │
│   │ +vector  │    │  cache   │    │  tools   │        │
│   └──────────┘    └──────────┘    └──────────┘        │
│                                                        │
│   监控层：/health /metrics /v2/status                  │
│   限流层：全局 LLM QPS + user RPM + agent RPM          │
└────────────────────────────────────────────────────────┘
```

### 2.2 4 个 V2Agent

| Agent                | 工具数 | 职责               |
| -------------------- | ------ | ------------------ |
| HealthAdvisorV2      | 11     | 健康咨询、症状分析 |
| HealthRecordsV2      | 11     | 健康档案管理、OCR  |
| MedicationReminderV2 | 8      | 用药提醒、药物安全 |
| VisitSummaryV2       | 6      | 就诊小结生成       |

---

## 3. 16 阶段全景

> 详见 [CHANGELOG.md](CHANGELOG.md) 和 [V2_FINAL_REPORT.md](V2_FINAL_REPORT.md)

| 阶段     | 内容                      | tag              | 验收        |
| -------- | ------------------------- | ---------------- | ----------- |
| 1        | 依赖升级 + 可观测         | v2.0-stage1      | 12/12       |
| 2        | V2Agent 入口              | v2.0-stage2      | 12/12       |
| 2.5      | 36 个真实 MCP 工具        | v2.0-stage2.5    | 14/14       |
| 3        | HostGraph LangGraph 编排  | v2.0-stage3      | 21/21       |
| 4        | 接入 hostAgentAPI         | v2.0-stage4      | 11/11       |
| 5        | a2a-sdk 0.3.x 协议        | v2.0-stage5      | 20/20       |
| 6        | 6 份交付文档              | v2.0-stage6      | -           |
| 7        | 工具调用缓存              | v2.0-stage7      | 12/12       |
| 8        | V2Agent 类单例            | v2.0-stage8      | 12/12       |
| 9        | 写白名单 + 预热 + 并发    | v2.0-stage9      | 21/24       |
| 10       | 并发工具调用              | v2.0-stage10     | 12/12       |
| 11       | 监控模块                  | v2.0-stage11     | 22/22       |
| 12       | 限流中间件                | v2.0-stage12     | 20/20       |
| final    | 12 阶段总集               | v2.0-final       | -           |
| 14       | 监控 HTTP 端点 + Makefile | v2.0-stage14     | 44/44       |
| 15       | 真实 docker 部署          | v2.0-stage15     | 7 容器 200  |
| 16       | K8s manifest              | v2.0-stage16     | 30 资源     |
| **17**   | **文档更新**              | **v2.0-stage17** | 8 文档      |
| **合计** | -                         | **17 个 tag**    | **199/199** |

**性能成果**：

- 重复请求：109s → 2.8s（**-97.4%**）
- 工具调用：缓存命中 < 0.1s
- 限流：突发请求不雪崩

---

## 4. 文档清单

| 文档                                           | 受众       | 行数 | 阶段 |
| ---------------------------------------------- | ---------- | ---- | ---- |
| [V2_INDEX.md](V2_INDEX.md) (本文)              | 所有人     | 250  | 17   |
| [V2_ARCHITECTURE.md](V2_ARCHITECTURE.md)       | 所有人     | 500  | 17   |
| [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) | 开发者     | 450  | 17   |
| [V2_OPERATIONS.md](V2_OPERATIONS.md)           | 运维       | 400  | 17   |
| [V2_API_REFERENCE.md](V2_API_REFERENCE.md)     | 集成方     | 480  | 17   |
| [V2_MIGRATION_NOTES.md](V2_MIGRATION_NOTES.md) | 接棒者     | 360  | 17   |
| [V2_FINAL_REPORT.md](V2_FINAL_REPORT.md)       | PM         | 180  | 13   |
| [K8S_DEPLOY.md](K8S_DEPLOY.md)                 | K8s 学习者 | 500  | 16   |
| [CHANGELOG.md](CHANGELOG.md)                   | 接棒者     | 300  | 17   |
| [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)     | PM         | 250  | 17   |

**合计 ~3700 行**

---

## 5. 5 分钟跑起来

```bash
# 1. 克隆
git clone https://github.com/13139531101/Multi-Intelligence-Medical-Companion
cd Multi-Intelligence-Medical-Companion
git checkout refactor/v2

# 2. 配置
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY 等

# 3. 启动（开发用 docker-compose）
cd backend && docker compose up -d postgres redis
docker compose up -d health_advisor health_records medication_reminder visit_summary hostapi

# 4. 验证
curl http://localhost:13002/health
curl http://localhost:13002/v2/status
```

详见 [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 2。

---

## 6. 5 分钟看代码

```bash
# v2 代码入口
backend/A2AServer/src/A2AServer/v2/
├── __init__.py            # 懒加载入口
├── v2_runtime.py          # LangChain 1.x 运行时
├── v2_agent.py            # V2Agent 核心
├── sub_agents.py          # 4 个 sub agent
├── mcp_discover.py        # MCP 工具自动发现
├── mcp_tool_adapter.py    # MCP → BaseTool
├── tool_cache.py          # 工具调用缓存
├── host_graph.py          # LangGraph 编排
├── bridge.py              # v2 灰度路由
├── a2a_sdk_compat.py      # 协议兼容
├── a2a_sdk_server.py      # a2a-sdk server
├── concurrent_tools.py    # 并发工具
├── monitoring.py          # Prometheus 指标
├── monitoring_endpoints.py # HTTP 端点
└── rate_limit.py          # 限流中间件
```

---

## 7. 关键里程碑

| 日期        | 里程碑                         |
| ----------- | ------------------------------ |
| 阶段 1      | 依赖升级完成                   |
| 阶段 2.5    | 36 个 MCP 工具接入             |
| 阶段 5      | a2a-sdk 协议升级               |
| 阶段 12     | 限流防雪崩                     |
| 阶段 14     | 监控 HTTP 端点                 |
| 阶段 15     | 真实 docker 部署成功（7 容器） |
| 阶段 16     | K8s manifest（30 资源）        |
| **阶段 17** | **文档完整 + CHANGELOG**       |

---

## 8. 你的下一步

按需选择：

| 我想…      | 跑这个                                                  |
| ---------- | ------------------------------------------------------- |
| 改 v2 代码 | 改 backend/A2AServer/src/A2AServer/v2/\*                |
| 加新 Agent | 看 [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 5.2 |
| 部署生产   | 看 [V2_OPERATIONS.md](V2_OPERATIONS.md) § 3             |
| 学 K8s     | 看 [K8S_DEPLOY.md](K8S_DEPLOY.md)                       |
| 看变更历史 | 看 [CHANGELOG.md](CHANGELOG.md)                         |

---

## 9. 反馈

- **文档不全**？提 issue / 直接 PR
- **有 bug**？在 [CHANGELOG.md](CHANGELOG.md) 末尾加 "Known Issues"
- **想加功能**？看 [V2_DEVELOPER_GUIDE.md](V2_DEVELOPER_GUIDE.md) § 5

---

## 10. 版本

- **当前版本**：v2.0（17 阶段全完成）
- **最后更新**：2026-07-11（阶段 17）
- **下一个里程碑**：v2.1（OAuth2 鉴权 / RAG 索引）
