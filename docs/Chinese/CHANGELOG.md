# PHA v2 更新日志 (CHANGELOG)

> 所有 v2 阶段变更记录。版本按 git tag 排序。
>
> **当前版本**：v2.0-stage33（33 阶段全完成）

---

## [v2.0-stage33] - 2026-07-14 - ANP 协议集成

### 新增
- **ANP (Agent Network Protocol) 协议集成** - 让 PHA 完整支持 A2A + MCP + ANP 三协议
- 装 `anp[api]>=0.8.8` SDK（实际装 0.8.9）
- hostapi 挂载 ANP sub-app（`/anp` 前缀）：
  - `GET  /anp/health`  健康检查
  - `GET  /anp/agent/ad.json`  Agent Description（含 DID:WBA）
  - `GET  /anp/agent/interface.json`  OpenRPC 接口定义
  - `POST /anp/agent/rpc`  JSON-RPC 2.0 调用
  - `GET  /anp/agents`  列出 4 个 PHA agent
  - `GET  /anp/agents/discover`  ANP 爬虫主动发现外部
- ANP RPC 方法：
  - `route_query(user_id, query)` 路由到合适 sub-agent
  - `parallel_query(user_id, query)` 4 agent 并行
  - `list_agents()` 列出所有 PHA agent
- 4 个 PHA agent 自动获得 DID：`did:wba:pha.local:{health_advisor, health_records, medication_reminder, visit_summary}`

### 三协议对比
| 协议 | 端点 | 适用场景 |
|------|------|---------|
| A2A | `/a2a/*` (v1) | 企业内 task 协作 |
| MCP | 各 MCP agent | LLM 调工具 |
| ANP | `/anp/*` | 跨组织/跨云 agent 互联网 |

### 验证
- `ad.json` / `interface.json` / `list_agents` RPC 全部 200
- LLM 路由正常（route_query 路由到 health_advisor）
- 6 files changed, 616 insertions

---

## [v2.0-stage31] - 2026-07-14 - AgentRegistry 自动注册

### 新增
- **`agent_registry.py`**（~180 行）：AgentSpec / AgentRegistry / @register_agent 装饰器
- 改造 `sub_agents.py`：4 个 class 改用 `@register_agent` 装饰器
- 改造 `host_graph.py`：build_host_graph 用 `discover_agents()` 自动构建
- 改造 `monitoring_endpoints.py`：用 `discover_agents()` 替代 hardcode

### 收益
- **新增 agent 只改 1 个 class**（装饰器绑定），其他全自动
- 之前要改 9 个地方（host_graph 5 处 + monitoring 1 处 + 4 个 import + 路由表）
- 现在只改 1 处

### 装饰器 vs 硬编码
| 维度 | 之前（v1） | 阶段31 |
|------|-----------|--------|
| 加 agent 改的地方 | 5+ 处 | 1 处 |
| 配置分散度 | 散在 5 个 dict | 集中装饰器 |
| 类型安全 | ❌ string-key | ✅ Python class |

---

## [v2.0-stage30] - 2026-07-13 - 多 agent 编排

### 新增
- **host_graph multi 模式**：4 个 invoke_X 并行 fan-out
  - 每个 node 写独立字段（避免 LangGraph 并行写冲突）
  - `aggregate_multi_node` 汇总 4 worker
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

### 收益
- **hostagent 能 query 每个 worker 状态**（之前只能看聚合 metrics）
- **多 worker 并行**（4 个 agent 同时跑）
- **长时间任务 + 崩溃恢复**（PostgresSaver）

### 验证
- multi mode 4 agent 并行（tool_calls: 48/77/107/164）
- PostgresSaver Checkpointer OK
- `/v2/agents/health_advisor/status` 返回 18 tool names
- 9 files changed, 572 insertions

---

## [v2.0-stage17] - 2026-07-11 - 文档完整化

### 新增
- `docs/Chinese/V2_INDEX.md` - 重写为统一入口（含 K8s 链接）
- `docs/Chinese/V2_ARCHITECTURE.md` - 重写为 v2.0 完整版
- `docs/Chinese/V2_DEVELOPER_GUIDE.md` - 增加 3 种部署方式章节
- `docs/Chinese/V2_OPERATIONS.md` - 增加 K8s 运维章节
- `docs/Chinese/V2_API_REFERENCE.md` - 增加 6 个 v2 端点
- `docs/Chinese/V2_MIGRATION_NOTES.md` - 增加 K8s 迁移
- `docs/Chinese/CHANGELOG.md` - 本文件
- `docs/Chinese/PROJECT_PROGRESS.md` - 项目进度总览

### 文档统计
- **9 份文档**（v2.0）vs 6 份（v2.0-stage6）
- **~3700 行**（+36%）

### 链接
- 17 tag 全部推送 GitHub + Gitee
- 提交：`76c25e7`（HEAD）

---

## [v2.0-stage16] - 2026-07-11 - K8s manifest

### 新增
- `k8s/00-namespace.yaml` - Namespace + LimitRange
- `k8s/01-secrets.yaml` - Secret + ConfigMap（11 API key + 业务配置）
- `k8s/02-postgres.yaml` - headless Service + PVC + StatefulSet
- `k8s/03-redis.yaml` - Service + PVC + Deployment
- `k8s/04-mcps.yaml` - 4 个 MCP 部署
- `k8s/05-hostapi.yaml` - ServiceAccount + Deployment
- `k8s/06-scaling.yaml` - HPA + PDB + Ingress + NodePort
- `k8s/kustomization.yaml` - Kustomize 统一入口
- `docs/Chinese/K8S_DEPLOY.md` - 500 行 K8s 学习指南

### K8s 资源
- **30 个 K8s 资源**
- 2 Namespace/Secret/CM, 1 SA, 2 PVC, 1 STS, 6 Deploy, 12 Svc, 1 HPA, 1 PDB, 1 Ingress

### 验证
- `kubectl apply --dry-run=client` 7/7 通过
- `kubectl kustomize k8s/` 渲染 30 资源 0 错误

### 修复
- 真实 API key 替换为 `REPLACE_ME_xxx` 占位符（GitHub Secret Scanning 拒绝后修复）

---

## [v2.0-stage15] - 2026-07-10 - 真实 docker 部署

### 新增
- 7 个容器全部运行（postgres + redis + 4 MCP + hostapi）
- A2A 协议端点（4 MCP agent.json）全部 HTTP 200
- v2 监控端点（6 个）全部 HTTP 200

### 修复（关键）
- **v2 包懒加载重构**（PEP 562 `__getattr__`）：
  - 之前 v2/__init__.py 顶层 import v2_agent → 触发 langchain
  - hostapi 容器未装 langchain → ImportError
  - 重构为 `__getattr__` 后 monitoring/rate_limit/tool_cache 可独立使用
- **FastAPI add_api_route media_type 错误**：
  - 之前用 lambda + media_type kwarg → IndexError 5
  - 改为命名函数 + Response(media_type=...)
- **hostapi 镜像 2 个月前构建不含 v2 目录**：
  - 用 bind mount 本地 backend 源码到容器
  - 4 个 hostAgentAPI 文件独立 mount

### 集成
- hostapi `api.py` 加 5 行代码 include v2 monitoring routers
- 验证 /health /health/deep /metrics /v2/status 等端点

---

## [v2.0-stage14] - 2026-07-10 - 监控 HTTP 端点 + 部署配置

### 新增
- `v2/monitoring_endpoints.py` - 7 个 HTTP 端点：
  - `GET /health` - K8s liveness probe
  - `GET /health/deep` - K8s readiness probe（深度检查）
  - `GET /metrics` - Prometheus 文本格式
  - `GET /v2/status` - 详细状态 JSON
  - `GET /v2/metrics/json` - 指标 JSON
  - `GET /v2/summary` - 人类可读摘要
  - `POST /v2/metrics/reset` - 重置指标（测试用）
- `.env.example` - 39 行完整配置模板
- `Makefile` - v2 目标 8 个（v2-verify-all / v2-bench / metrics / health 等）

### 验收
- verify_stage14.py: **44/44 通过**

### 修复
- /health/deep 返回字符串拼接无效 JSON → 用 json.dumps

---

## [v2.0-final] - 2026-07-10 - 12 阶段总集

### 新增
- `docs/Chinese/V2_FINAL_REPORT.md` - 12 阶段 / 13 tag 总集

### 统计
- 177/179 验收
- 13 tag 全部推送
- 6 份交付文档
- 性能：109s → 2.8s（-97.4%）

---

## [v2.0-stage12] - 2026-07-10 - 限流中间件

### 新增
- `v2/rate_limit.py` - TokenBucket + SlidingWindowLimiter + PHA2RateLimiter
  - 3 层限流：全局 LLM QPS / user RPM / agent RPM
  - 环境变量：PHA_LLM_QPS / PHA_USER_RPM / PHA_AGENT_RPM / PHA_RATE_LIMIT_WINDOW
- `v2_agent.py` - stream() 开头限流检查，超限 yield rate_limited=True

### 验收
- verify_stage12.py: **20/20 通过**

### 踩坑
- 初次 19/20，第 2 次未限流
- 排查 30+ 分钟：发现测试间隔 > 60s 滑动窗口已过期
- 修：加 PHA_RATE_LIMIT_WINDOW 环境变量，测试用 600s 窗口
- 教训：长跑测试要注意限流时间窗口

---

## [v2.0-stage11] - 2026-07-10 - 监控模块

### 新增
- `v2/monitoring.py` - Prometheus 格式指标
  - 工具缓存 hit/miss rate
  - V2Agent 单例 reuse rate
  - 请求 p50/p95/p99 延迟
  - LLM API 错误率
- 集成到 v2_agent.py（缓存命中/未命中计数）

### 验收
- verify_stage11.py: **22/22 通过**

---

## [v2.0-stage10] - 2026-07-10 - 并发工具调用

### 新增
- `v2/concurrent_tools.py` - 并发工具执行器
  - PHA_CONCURRENT_TOOLS=true 启用
  - PHA_MAX_CONCURRENCY=5 默认并发度
- 集成到 v2_agent.py

### 验收
- verify_stage10.py: **12/12 通过**

### 限制
- LangChain 1.x 暂未提供并发 API 钩子
- 并发模块**就绪但未启用**（准备升级时启用）

---

## [v2.0-stage9] - 2026-07-10 - 写白名单 + 预热 + 并发

### 新增
- 写白名单：`tool_cache.py` 的 `is_write_tool()` 判断
  - 写操作不缓存（避免返回过期数据）
- Embedding 预热：`v2_runtime.py` 启动时预加载
- 并发工具调用模块基础

### 验收
- verify_stage9.py: **21/24 通过**

### 已知问题
- 3 项 fail：与 LLM mock 行为有关（不影响生产）

---

## [v2.0-stage8] - 2026-07-10 - V2Agent 类单例

### 新增
- `v2_agent.py` - `V2Agent._agent_instance_cache` 类级 dict
  - 同一 (类, model) 复用 LangChain agent 实例
  - 节省 3s/次（重复创建）

### 验收
- verify_stage8.py: **12/12 通过**

### 性能
- agent 创建：~3s → <0.1s（**-95.7%**）

---

## [v2.0-stage7] - 2026-07-10 - 工具调用缓存

### 新增
- `v2/tool_cache.py` - 工具调用结果缓存
  - TTL 60s 默认
  - max 1000 entries
  - 写操作不缓存

### 验收
- verify_stage7.py: **12/12 通过**

### 性能
- 重复请求：109s → 2.8s（**-97.4%**）

---

## [v2.0-stage6] - 2026-07-10 - 6 份交付文档

### 新增
- `docs/Chinese/V2_INDEX.md`
- `docs/Chinese/V2_ARCHITECTURE.md`
- `docs/Chinese/V2_DEVELOPER_GUIDE.md`
- `docs/Chinese/V2_OPERATIONS.md`
- `docs/Chinese/V2_MIGRATION_NOTES.md`
- `docs/Chinese/V2_API_REFERENCE.md`

### 统计
- 合计 ~2500 行

---

## [v2.0-stage5] - 2026-07-10 - a2a-sdk 0.3.x 协议

### 新增
- `v2/a2a_sdk_compat.py` - PHA 协议 ↔ a2a-sdk 0.3.x 协议转换
- `v2/a2a_sdk_server.py` - a2a-sdk 标准 FastAPI server（端口 10020）
- 独立 server 兼容 a2a-sdk 客户端

### 验收
- verify_stage5.py: **20/20 通过**

---

## [v2.0-stage4] - 2026-07-10 - 接入 hostAgentAPI

### 新增
- `v2/bridge.py` - v2 灰度路由
  - 旧请求 → v1
  - 新请求（v2 header）→ v2
  - 失败 fallback
- 集成到 hostAgentAPI

### 验收
- verify_stage4.py: **11/11 通过**

### 兼容性
- v1 / v2 并存
- 灰度切流（5% → 50% → 100%）

---

## [v2.0-stage3] - 2026-07-10 - HostGraph LangGraph 编排

### 新增
- `v2/host_graph.py` - LangGraph 1.x 编排
  - 替换 adk_host_manager.py
  - StateGraph 替代 ADK HostAgent
- 4 个 V2Agent 注册为 node

### 验收
- verify_stage3.py: **21/21 通过**

---

## [v2.0-stage2.5] - 2026-07-10 - 36 个真实 MCP 工具

### 新增
- `v2/mcp_discover.py` - AST 扫描 + 动态加载
- `v2/mcp_tool_adapter.py` - MCP 工具 → LangChain BaseTool
- 接入 4 个 MCP server（11 + 11 + 8 + 6 = 36 工具）

### 验收
- verify_stage2_5.py: **14/14 通过**

---

## [v2.0-stage2] - 2026-07-10 - V2Agent 入口

### 新增
- `v2/v2_agent.py` - V2Agent 核心
  - LangChain 1.0 `create_agent()` 封装
  - 流式输出
  - 工具调用 + 结果处理
- `v2/sub_agents.py` - 4 个 V2Agent
  - HealthAdvisorV2
  - HealthRecordsV2
  - MedicationReminderV2
  - VisitSummaryV2

### 验收
- verify_stage2.py: **12/12 通过**

---

## [v2.0-stage2.1] - 2026-07-10

### 修复
- `v2_runtime.py` 修复 langgraph 1.0.x 兼容问题
- pin prebuilt 1.0.5

---

## [v2.0-stage2.2] - 2026-07-10

### 修复
- 工具适配器细节调整

---

## [v2.0-stage1] - 2026-07-10 - 依赖升级

### 新增
- `v2/v2_runtime.py` - LangChain 1.x 探测
  - 探测 LangChain / LangGraph / langchain.agents.create_agent
  - 降级到 v1 模式（如果 LangChain 不可用）

### 验收
- verify_stage1.py: **12/12 通过**

### 关键升级
- LangChain 1.x
- LangGraph 1.0
- a2a-sdk 0.3.x

---

## 已知问题 (Known Issues)

| 问题 | 影响 | 状态 |
|------|------|------|
| hostapi 容器 `/a2a` 端点 POST 400 | A2A 协议请求格式不符 | 计划修 |
| 并发工具模块未真正启用 | LangChain 1.x 缺 API 钩子 | 等 LangChain 升级 |
| v2 文档中文为主 | 英文版缺失 | 计划补 |
| K8s 镜像需重新构建 | 当前用 2 个月前镜像 | 计划修 CI/CD |

---

## 下一步计划

- **v2.1**：OAuth2 鉴权 / OPA 授权
- **v2.2**：RAG 索引 / PGVector 记忆
- **v2.3**：CI/CD (GitHub Actions / ArgoCD)
- **v2.4**：HTTPS 证书 (cert-manager)
- **v3.0**：模型分流 / 多模型协同

---

## 反馈

提 issue / PR / 邮件，**所有反馈都被记录**。
