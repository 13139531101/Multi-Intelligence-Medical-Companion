# 面试材料逐条核查（2026-10-05）

> **这份文件是工作稿，不是作品集内容。** 它拿代码逐行核对了那份外部准备材料
> （连接池 / A2A / MCP / RAG / 部署 / 安全 六大块），标注每条是
> **✅ 可以照说 / ⚠️ 要改口径 / ❌ 代码里没有**。
>
> 判定依据全部是 `文件:行号`。**核查方式**：五路并行搜索，覆盖 `backend/`、
> `frontend/`、`database/`、`docker*/`、`k8s/`、`.github/`、`tests/`，含多种命名习惯。

## 一句话结论

材料**骨架是真的**（多 Agent 拆分、A2A 能力发现、MCP 工具化、rerank、Compose+Nginx 都对），
但有三类问题：

1. **「安全合规」和「可观测性」两节水分最大** —— 写的是"应该怎么做"的教科书答案，代码里多半没有。
2. **「幂等」「熔断」「病毒扫描」「Prompt Injection 防护」是脑补的** —— 全仓零命中。
3. **反过来，材料把自己写小了** —— 仓库里有 WriteGuard、OAuth2 双 token、DID 身份、
   HITL 中断恢复、AG-UI 适配层等一堆硬货，材料一个字没提（见文末第 5 节）。

---

## 1. ❌ 代码里不存在 —— 说了会被当场问穿

| # | 材料说法 | 实际 |
|---|---|---|
| 1 | 轮询接口 `/task/status?task_id=...` | **该端点不存在**（全仓零命中）。轮询本身是真的，但轮的是 `/message/pending` + `/events/query` + `/message/list`（`src/components/Conversation.jsx:69-240`，`setInterval` 500ms） |
| 2 | 工具调用幂等键 `conversation_id + tool_name + params_hash`；"外部付费调用前先查幂等记录" | **全仓零命中**（`params_hash\|idempotency_key\|幂等键` 无匹配）。最接近的是 `v2/tool_cache.py:99-103` —— 那是 **60 秒 TTL 的只读工具结果缓存**，不是幂等台账 |
| 3 | 熔断 circuit breaker | **零命中**（`circuit\|熔断\|breaker`） |
| 4 | Prompt Injection 防护（系统提示角色隔离 / 注入检测 / 拒绝泄露） | **不存在**。无任何"文档内容不得覆盖系统规则"类提示，无注入检测。`write_audit.py:52` 的"白名单"是**写操作白名单**，与注入无关 |
| 5 | 病毒扫描（ClamAV / 云扫描） | **零命中** |
| 6 | MIME / 文件头（magic number）校验 | **不存在**。类型白名单只依据**客户端可伪造的** Content-Type 和文件名后缀（`services/health_records_service.py:1080-1123`） |
| 7 | 解析沙箱（限制 CPU/内存/超时） | **不存在**。OCR 直接 `subprocess.run(["tesseract", ...])`（`PhaCore/mcpserver/shared_ocr.py:81-89`） |
| 8 | 证据块带 `citation_id` | **零命中**。items[] 实际字段是 `source/id/type/title/excerpt/created_at/score/vector_score/scope`（`knowledge_tool.py:689-704`）—— 字段叫 **`excerpt` 不是 `text`**，**没有 `citation_id`** |
| 9 | 文档清洗：去页眉页脚 / 水印 / 重复行 / 合并断行 | **零命中**。入库前只有**乱码比例检测**（`services/medical_kb_service.py:131-174`）和空行剔除 |
| 10 | `message_id` / `file_hash` / `(user_id, file_hash)` 的 UNIQUE 约束 | **不存在**。`chat_messages` 主键是 `id TEXT`，**没有 message_id 列**；`health_records.file_hash` 只是普通 `VARCHAR(64)`，去重靠应用层 SELECT 查重（`services/health_records_service.py:1606-1613`） |
| 11 | 复合索引 `(conversation_id, created_at)`、`(user_id, source_id)` | **这两个具体形式不存在**。实际是 `(consultation_id, created_at ASC)`（`hostAgentAPI/api.py:4000`）和 `(user_id, source_type)` + `(source_type, source_id)`（`database/postgres/init/02_reminders_and_records.sql:138-139`） |
| 12 | Agent 卡里声明健康检查 | AgentCard 结构里**没有 health 字段**（`common/A2Atypes.py:331`）。`/health` 在 **Host** 上（`v2/monitoring_endpoints.py:60`），不在各 Agent |
| 13 | Host 定期探测 Agent 健康 | **不存在**。只有注册时重试 12 次（`hostAgentAPI/server.py:155-174`）+ docker/k8s 探针 |
| 14 | 写库用自增序号（seq）保证同会话顺序 | **无自增序列**，靠 `created_at` + `(consultation_id, created_at)` 索引 |
| 15 | conversation_id + last_message_id 断线增量重拉 | **不存在**。`/v2/chat/resume` 是 **HITL 中断恢复**（thread_id + decisions），不是重连 |
| 16 | OCR / embedding 走"队列 + worker"架构 | **不存在**。OCR 异步是真的，但是 **FastAPI BackgroundTasks 进程内后台任务**（`v2/upload_pipeline.py:558-561`），无 celery/redis/RQ；**embedding 压根没有异步管线** |
| 17 | DB migration 用 Alembic | **不是 Alembic**。是自研的 `scripts/migrate.py`（`schema_migrations` 表 + checksum + rollback_sql，CI 里真跑）+ 大量启动时 `CREATE TABLE IF NOT EXISTS` 双轨并存 |
| 18 | pgvector 用 HNSW / 调 `ef_search` | **是 IVFFlat，不是 HNSW**，且**只设了 `lists = 100`，从不调 `probe`**（全仓 5 处建索引全同）。HNSW 只出现在路线图愿景里 |
| 19 | 前端有测试 | **不存在**。`package.json` 无 test script，`src/` 下无任何 `*.test.*` |
| 20 | Recoil 已清理 | **没清理**。`recoil ^0.7.7` 仍在 dependencies，**12 个文件**在 import |
| 21 | query 长度裁剪 | **不存在**（只有输出侧 `_excerpt` 截断） |
| 22 | 表格抽取"指标-结果-**参考范围**-单位"四元组 | **参考范围不在输出里**，反而在指标名**黑名单**里被主动排除（`health_records_api.py:1416-1417`）；实际只有三元组 |

---

## 2. ⚠️ 部分真实 —— 改了就能用

| # | 材料说法 | 改成这样说 |
|---|---|---|
| 1 | `DB_POOL_MAX_SIZE` **默认 20** | **默认 2**（`HealthAdvisor/database_config.py:91`、`HealthRecordsManager/database_config.py:40`），compose 部署默认 `3`。唯一出现 20 的是 `auth.py:164` 解析失败的兜底分支。**`docker-compose.yml:279-283` 留着一行注释，记的正是池太小把连接打满、auth 500 的事故** —— 说成 20 等于把踩过的坑说反了 |
| 2 | 业务代码"统一" `with db_manager.get_connection()` | 机制真实（池优先 + `psycopg.connect` 直连 fallback，异常 `rollback()` 再归还），但**全仓至少 4 套连接获取方式并存**：`db_manager.get_connection()`、`health_records_api.py:1007` 的 `get_db_connection()`、记忆系统的 `getconn()/putconn()`、v2 的 `AsyncConnectionPool`。别说"统一" |
| 3 | 混合检索（向量 + 关键词兜底）是**系统整体策略** | **只在 HealthAdvisor 栈里是真的**（`knowledge_tool.py:752-767`，真 SQL `ILIKE`）。**v2 主链路是纯向量检索** —— `v2/rerank.py:5-7` 的 docstring 自己写着这句。tsvector/BM25 全仓零命中 |
| 4 | "不本地部署模型" | **rerank 这半句是真的**（DashScope HTTP，全仓无 CrossEncoder）；**embedding 是假的** —— `HealthAdvisor/mcpserver/knowledge_tool.py:28-31` 走本地 `sentence_transformers` 的 `all-MiniLM-L6-v2`，AgentMemorySystem 也是 |
| 5 | OCR 三级 fallback | 有，**但有缺陷**：占位串 `"阿里云OCR 2021 接口调用占位"` **不在** `_aliyun_error_signatures()` 里，所以配了 key 时占位串会被当成"识别结果"直接返回、**fallback 根本不触发**（`PhaCore/mcpserver/shared_ocr.py:32-42, 115-148`） |
| 6 | 监控：接口耗时 / 错误率 / 队列堆积 / 连接池 | `/metrics` 端点**真的实现了**（Prometheus 格式），**但无人抓取**：compose 里没有 Prometheus、仓里没有 `prometheus.yml`、Grafana 数据源**只配了 Loki**。而且 `observability/metrics.py` 里通用指标（`pha_requests_total`/`pha_llm_calls_total`/`pha_a2a_rpc_calls_total`/`pha_db_query_latency_seconds`）**只定义、零调用点** —— 真正接了埋点的只有 CRAG / Critique / rerank 三组 |
| 7 | 结构化日志 + trace_id/request_id 贯穿链路 | JSON 格式器真实（`observability/structured_logging.py:37-91`），promtail 也按这些字段解析；**但 `LogContext` 在生产代码里零调用**（只在测试里用过），`setup_logging` 没在任何服务入口被调。所以"request_id 贯穿"**不成立** |
| 8 | 密码哈希 bcrypt/argon2（如果打算这么说） | **是 `hashlib.sha256(password + salt)` 单轮无迭代**（`hostAgentAPI/auth.py:285-292`）。全仓无 bcrypt/argon2/scrypt/pbkdf2/passlib |
| 9 | `JWT_SECRET_KEY` 缺省策略 | **三套并存**：代码硬编码（`auth.py:32`、`v2/oauth2.py:45`、`health_records_api.py:222`）、compose dev-secret 兜底（`docker-compose.yml:206,358`）、admin_backend 缺失直接崩（`:261,263` required 语法） |
| 10 | 健康数据加密（Fernet） | **实现了但零调用**。`storage_tool.py:42-57` 定义了 `encrypt_data`/`decrypt_data`，**全仓无调用点**；`save_health_record` 直接写明文（`:116-130`）。**别说"已加密"** |
| 11 | 上传大小 Nginx + 应用双层限制 | 应用层是真的（10MB/20MB）；**Nginx 层只有 admin-dashboard 配了 `client_max_body_size 50m`，multiagent_front 的 nginx.conf 没有这条**（默认 1MB，反而会挡上传） |
| 12 | 工具级硬超时 | **v1 MCP 客户端有**（`client.py:116, 308-317`）；**v2 LangChain 主链路没有 per-tool 超时**（`v2_runtime.py` 只有 Retry/CallLimit/Fallback 中间件） |
| 13 | AST 扫描不认 `async def` | 缺陷**真实存在**（`mcp_discover.py:178-179` 只认 `ast.FunctionDef`），但**当前无实际受害者** —— 全仓没有 `async def` + `@mcp.tool` 的工具。说"潜伏缺陷"而不是"正在丢工具" |
| 14 | 工具返回体 `[:4000]` 截断 | 机制描述准确，**数字已过时** —— 现在是 `[:20000]`（`v2_agent.py:588-591`，阶段48-28 提上去的） |
| 15 | 三 ID 贯穿全部链路 | `conversation_id`/`message_id` 真实贯穿；**`task_id` 只在 v1 A2A 路径**（`adk_host_manager.py:279`），**v2 主路径走进程内 LangGraph，不产生 task_id** |
| 16 | 多 Agent 并行用 `asyncio.gather` | **并行是真的，但由 LangGraph fan-out 实现**（`host_graph.py:1210-1222`）；`asyncio.gather` 用在**工具层并发**（`v2/concurrent_tools.py:84-87`），不是"多 Agent 并发调用" |
| 17 | 幂等靠 UNIQUE + upsert | **确实大量用**，但核心是 **RAG / 知识图谱 / 咨询表的复合键**（`rag_chunks`、`rag_documents`、`kg_entities`、`rag_feedback`），**不是材料点名的 `message_id` / `file_hash`** |
| 18 | 来源聚合去重（按 source 分组、组内 topM、组内相似去重） | 栈 B 有 `row_number() OVER (PARTITION BY user_id, source_type, source_id)`（**topM=1**，`knowledge_tool.py:107-117`）；**v2 只有 chunk_id 去重**；**组内相似文本去重全仓不存在** |
| 19 | 敏感信息脱敏 | PII 中间件真实，覆盖 **email / url / ip / credit_card / 手机号**（`v2/v2_runtime.py:241-283`）；**身份证无脱敏**（反而有抽取存库逻辑）、**住址无脱敏**。另有两个反例：`/v2/files/{id}` 注释明写"不做用户隔离"（`upload_pipeline.py:936`）、embedding 查询原文**未脱敏**直送 DashScope（`rag.py:163-171`） |
| 20 | user_id 三层注入 | 三层**都有**，但 **(c) 的机制描述不准** —— `process_tool_call`（`mcp_client/client.py:560-573`）是**无条件覆盖**，**不做** `current_user`/`default_user` 占位值判断；占位值识别在**工具内部**（`memory_integration_tool.py:79-93`）和 API 层 |

---

## 3. ✅ 可以照说 —— 有代码证据

### 数据库 / 连接池
- 模块级 `_db_pool` 懒加载 + `_db_pool_init_attempted` 防重试（`HealthAdvisor/database_config.py:41-42, 83-102`；`HealthRecordsManager/database_config.py:17-18, 32-47`）
- 优先 `DATABASE_URL`，否则拼 DSN（`HealthAdvisor/database_config.py:69-80, 118-127`）
- `get_connection()` 异常 `rollback()` 再归还/关闭（`HealthAdvisor/database_config.py:152-186`）
- `AgentMemorySystem/database_config.py:69, 84` 的 `getconn()/putconn()` 风格

### A2A 协议 / 会话
- `.well-known/agent.json` **由 Starlette 路由动态返回**（`common/server/server.py:62-64, 92-93`），含 **skills**（`HealthAdvisor/main.py:60-70`）、**输入输出模式**（`:56,78-79`）、**capabilities.streaming**（`:59`）
- `/message/send`、`/message/list`、`/events/query` **三个接口名全对**（`hostAgentAPI/server.py:84-99`）
- Host 会话管理（`server.py:187-214`）+ Agent 注册发现（启动读 `agents.json` → 拉 `.well-known/agent.json`，`server.py:148-180` + `adk_host_manager.py:694-704`）
- SSE 流式：后端 `EventSourceResponse`（`common/server/server.py:135-138`）；前端三套增量渲染（`fetchEventSource` / `getReader` / `wx.onChunkReceived`）
- "流式异常回退 v1 + 轮询"真实（微信小程序 `agent_chat.js:1631-1639, 2266-2270`）

### RAG
- chunk size / overlap **全部 env 可配**（v2 `rag.py:59-60` 200/30；hostapi `health_records_api.py:324-369` 650/120；MCP `knowledge_tool.py:507-508` 800/120），hostapi 那条有**真标题语义切分**
- topK 可配（`rag.py:61`，默认 5）+ **召回 2 倍候选给 rerank**（`rag.py:381`）+ 最终上下文按 chunk 300 字 / 总量 1500 字截断
- **rerank（最硬的一条）**：DashScope `gte-rerank-v2` 走 **HTTP**（`v2/rerank.py:31-32, 63-65`）、**可开关**（`:48-50`）、**8 秒超时**（`:33`）、**失败回退向量序**（`:127-198` + `magnetic_rag.py:697-734`）、**全仓无本地 cross-encoder**
- **MRR 0.6167 → 1.0 有确凿出处**：`tests/performance/rag_metrics.json:13`（vector）与 `:61`（rerank）
  > ⚠️ **但这是栈 B（HealthAdvisor MCP，单跳）的 5 条小样本**。主链路（栈 A `magnetic_rag`）另有一份
  > **更好的**评测：`tests/performance/rag_v2_metrics.json`，**18 条自然语言用例、四组消融**，
  > 多跳 MRR **0.6667 → 0.95**，且含 3 条拒答用例（`false_positive_rate: 0.0`）。
  > **材料里所有拿 0.6167→1.0 当主数字的地方都该换成这份**（README / ARCHITECTURE /
  > INTERVIEW_PREP / RESUME 已于本次更新）。`thesis_outline_ch1_draft.md:780,784` 仍是旧数字，待定。
- CRAG 三分支 CORRECT/AMBIGUOUS/INCORRECT（`v2/crag/action_policy.py:23-63`，阈值 0.75/0.30 可配）
- 融合方式是**"并集 + 去重 + rerank"**（`magnetic_rag.py:822-869`），不是加权融合

### MCP / 工具
- **FastMCP** + transport 默认 `streamable_http`，失败降级链 http→stdio→inprocess（`mcp_tool_adapter.py:116, 260-290`）
- **`inspect.signature` 建真实 pydantic `args_schema`**（`mcp_tool_adapter.py:863-943`）
- **工具重名守卫在 CI 里且是阻断的**（`tests/test_tool_dedup.py` + `.github/workflows/test.yml:129-130`），当前 3 处跨 agent 重名降级为 WARN
- **user_id 三层注入的骨架成立**（`server.py:103-111` JWT→env；`task_manager.py:69-85` metadata→run_inference；`client.py:560-573` 工具调用时补）
- topK 钳到 1..50（`knowledge_tool.py:626, 776, 795`）
- **有限次重试 + 退避**（`v2_runtime.py:361-366`，`max_retries=2, backoff_factor=0.5`）
- 检索失败 → 关键词兜底（`knowledge_tool.py:752-767`）
- 工具数 **health_advisor 18 / health_records 19 / medication_reminder 12 / visit_summary 12**，PhaCore 共享 9，合计 **70**（与 README 一致）
- `open_health_record` **health_advisor 没有、health_records 有**（`HealthRecordsManager/mcpserver/page_control_tool.py:215`）
- **PhaCore 工具不含 `user_id`**，且是写进文件头的硬约束（`shared_page_control.py:22-24`"绝不写 user_id 参数"）

### 部署
- **Docker Compose 12 个服务**，服务名当 DNS（`docker-compose.yml:67, 368`；`nginx.conf:25` 显式 `resolver 127.0.0.11`）
- **Nginx**：反代四组 location、静态资源 + SPA fallback、`proxy_read_timeout 300s`、**SSE 透传 `proxy_buffering off`**（`multiagent_front/nginx.conf:45-50, 63-68, 94-99`）
- 9 个服务配了 healthcheck（四个 agent 打的都是 `/.well-known/agent.json`）；hostapi 的 `depends_on` 用了 `condition: service_healthy`
- **`/metrics` 端点真实实现**（Prometheus 格式，`hostAgentAPI/api.py:319-325`，四个 agent 各自也挂了）
- **CI 真实**：5 个 workflow，`verify_stage*.py` + 工具重名守卫（阻断）

---

## 4. 材料里最危险的六条（按"被问穿的代价"排序）

1. **"默认 20"** —— 和自己仓库里的踩坑注释直接矛盾
2. **"混合检索"写成系统整体策略** —— v2 主链路纯向量，一问 `rerank.py` 的 docstring 就露
3. **"幂等键 / 熔断 / 病毒扫描"** —— 三个词全仓零命中，属于纯脑补
4. **"加密已做"** —— Fernet 是死代码，`save_health_record` 写明文
5. **"监控体系"** —— 端点孤立、通用指标零埋点，一问"看板上能看到什么"就空
6. **"不本地部署模型"** —— embedding 是本地 MiniLM，只有 rerank 符合

---

## 5. 🎁 材料漏掉的加分项 —— 这些比材料里那些更值得讲

**每一行都是核查时翻出来的、材料一个字没提的**：

| 加分项 | 位置 |
|---|---|
| **WriteGuard 写操作安全网关**：工具白名单 + `confirm_token` 二次确认 + 每用户每小时写配额 + 审计（含 request_id/duration_ms） | `v2/write_audit.py:71-87` |
| **OAuth2 双 token**：access 15min + refresh 7d + **jti 撤销列表** + 签发限流 20/min/IP + RBAC role claim | `v2/oauth2.py:45-169` |
| **DID:WBA 去中心化身份**：Ed25519 keystore + 对 HTTP body 的 sha256 签名验签 + `/anp` 子应用 | `v2/did_wba.py`、`HealthAdvisor/main.py:114-123` |
| **HITL 人机协同中断/恢复**：`interrupt` 事件 + `/v2/chat/resume`（thread_id + decisions），前端已接 | `hostAgentAPI/api.py:5292, 5365-5428`、`NewChat.jsx:764-797` |
| **CopilotKit / AG-UI 协议适配层**：`/api/copilotkit`，28 个标准事件 + 非标准自动包 CUSTOM + **幂等状态走标准 `STATE_DELTA`** | `copilotkit_runtime.py`、`src/ai/pageStateStore.js` |
| **v1/v2 双路径自动降级**：v2 失败自动回退 v1 ADK，还能用 `X-PHA-V2-Disable` 头强制 | `hostAgentAPI/server.py:300-357` |
| **语义缓存 / 限流器 / 推理链追踪 / 多模型路由**（deepseek→qwen→claude→local 自动 fallback） | `v2/semantic_cache.py`、`rate_limit.py`、`reasoning_tracer.py`、`multi_model.py` |
| **k8s 全套部署清单**（含 HPA、secrets、kustomization） | `k8s/00-namespace.yaml` ~ `06-scaling.yaml` |
| **工具并发执行**：`ToolNode.awrap_tool_call` 并发跑无依赖 tool_calls（max_concurrency=5），**写操作不并发** | `v2/concurrent_tools.py:84-87` |
| **调用次数硬上限**：单轮 tool ≤12、thread 内 LLM ≤30 轮 | `v2_runtime.py:341, 351` |
| **工具结果缓存**：60s TTL + LRU 1000 + 命中统计，自动套在 inprocess 工具上 | `v2/tool_cache.py`、`mcp_tool_adapter.py:844-849` |
| **子进程 env 白名单透传**：stdio/http 子进程只继承十余个白名单 env | `mcp_tool_adapter.py:334-343, 669-678` |
| **MCP 503 快速拒绝**：工具预加载未完成时直接 503 | `common/server/server.py:97-100` |
| **知识图谱**：`kg_entities`/`kg_relations` + 实体扩展 `graph_expand_entities`，多跳检索真的在用 | `v2/knowledge_graph.py:491-519`、`magnetic_rag.py:843-864` |
| **用户反馈闭环**：`rag_feedback` 表 + 检索加权 `score * (1 + 0.2 * fb)`，点赞/点踩影响后续排序 | `v2/rag.py:388-461` |
| **被测量否掉的优化（负结果）**：想让 rerank 分数短路 LLM 相关性判断，实测量纲不同（0.16–0.35 vs 0.95）→ 主动放弃 | `magnetic_rag.py:32-50` |
| **多跳检索的负收益数据**：`multi_hop_mrr_gain: -0.0056`（诚实报负结果） | `tests/performance/rag_v2_metrics.json:551` |
| **跨租户唯一约束的生产事故修复**：旧约束不含 user_id 导致跨用户互踩、`/v2/rag/index` 500 | `backend/A2AServer/migrations/drop_legacy_rag_chunks_constraint.sql` |

---

## 6. 建议的动作

1. **第 1 节的 22 条**：直接从材料里删掉，或改成"我们当时评估过但没做，因为……"——
   后者反而是加分项（**能说清"为什么没做"比假装做了强**）。
2. **第 2 节的 20 条**：按"改成这样说"一栏改措辞。多数只是把"统一/整体/贯穿"这类
   绝对词去掉，改成"在某条链路上"。
3. **第 3 节**：保留，照说。
4. **第 4 节六条**：单独过一遍，确认自己嘴上不会滑出去。
5. **第 5 节**：补进材料。**这是这次核查最大的收获** —— 材料把项目写小了。
6. 材料里"你们怎么处理 X"那种教科书式问答，建议整体降权：
   **面试官要的是"你的项目里怎么做的"，不是"业界通常怎么做"。**
