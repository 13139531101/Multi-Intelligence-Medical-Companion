# PHA 系统架构（当前实现）

> 本文档描述**截至 2026-10 阶段 48-30 的真实实现**，替代已过时的 `V2_ARCHITECTURE.md`（那份停在阶段 5，仍写着端口 10010 / 36 个 MCP 工具）。
>
> 写法约定：凡本文写下的行为，都在代码里能指到具体文件行；凡已知的坑与债，单列在最后一节，不粉饰。

---

## 1. 一句话定位

一个**多智能体个人健康助手**：用户用自然语言提问，系统路由到领域智能体，智能体调用 MCP 工具查库/调模型，答案以 SSE 流式返回，并能在前端**驱动页面动作**（导航、筛选、填表、刷新）。

技术上的卖点不是"接了个大模型"，而是**四套协议各司其职、边界清晰**，以及在此之上把 RAG 做成了可度量的多跳检索管线。

---

## 2. 服务拓扑

13 个容器，一条 `docker compose up -d` 拉起：

| 服务 | 角色 | 对外端口 |
|---|---|---|
| `multiagent_front` | React 前端（nginx 托管） | **5174 → 80** |
| `hostapi` | 主后端：A2A Host、v2 编排、AG-UI 转译、REST API | **13002** |
| `health_advisor` | 领域智能体（A2A 服务端） | 内部 |
| `health_records` | 领域智能体 | 内部 |
| `medication_reminder` | 领域智能体 | 内部 |
| `visit_summary` | 领域智能体 | 内部 |
| `postgres` | pgvector/pg16，业务数据 + 向量 + 知识图谱 | 5432 |
| `redis` | 缓存 / 语义缓存 / 限流 | 6379 |
| `loki` + `promtail` + `grafana` | 日志聚合与看板 | 3101 / — / **3030** |
| `admin_backend` / `admin_frontend` | 管理后台 | 内部 |

**注意 `hostapi` 是个"胖后端"**：它同时是 A2A Host、v2 编排器、AG-UI 转译层和 REST API 服务。其中 `frontend/hostAgentAPI/api.py` 单文件 **5581 行** —— 这是本项目最大的一处结构性技术债，见 §11。

> **`api.py` 只有一份了**：此前仓库根目录还躺着一份 **`./api.py`（5323 行）** 的重构前快照，已在本轮删除（§11 已修第 5 条）。**生效的始终是 `frontend/hostAgentAPI/api.py`** —— 按 `Dockerfile` 的 `COPY frontend/hostAgentAPI ./` 落到容器里的 `/app/api.py`。
>
> 这条留作提醒：**判断"哪份文件是活的"，别读代码，读构建配置**（Dockerfile 的 COPY、compose 的 volumes）。运行时事实永远优先于源码事实。

---

## 3. 四协议分层

四套协议**不是四个功能，而是四条正交的边界**。搞混它们会让架构说不清，所以先立边界：

| 协议 | 连接的是 | 在本项目的落点 | 形态 |
|---|---|---|---|
| **MCP** | 智能体 ↔ 工具 | `mcp/mcp_discover.py` + 各 agent 的 `mcpserver/*_tool.py` + PhaCore 共享工具 | 工具发现与调用 |
| **A2A** | 智能体 ↔ 智能体 | `A2Atypes.py`、`bridge.py`、四个领域智能体服务 | 消息传递、任务委托 |
| **AG-UI** | 智能体 ↔ 用户界面 | `frontend/hostAgentAPI/copilotkit_runtime.py` | 类型化 SSE 事件流 |
| **ANP** | 组织 ↔ 组织 | DID:WBA 身份层、Registry | 跨域发现与信任 |

**MCP 与 A2A 的分工**：MCP 解决"这个智能体能做什么"，A2A 解决"这个智能体能把活派给谁"。两者都涉及"调用"，但一个是能力边界，一个是组织边界 —— 这是面试里最容易被问混的一点。

### A2A 是双轨的（v1 协议 + v2 a2a-sdk）

这点容易被"我们用了 A2A"一句话盖过去，实际是两条并存：

| 轨 | 形态 | 位置 |
|---|---|---|
| **v1（自研）** | `JSONRPCRequest/Response`、`SendTaskRequest`、`TaskSendParams`、`Message` | `common/A2Atypes.py:147-173` |
| **v2（标准）** | a2a-sdk 0.3.x 的 `SendMessageRequest(id, jsonrpc, method, params=MessageSendParams)` | `v2/a2a_sdk_compat.py` |

`a2a_sdk_compat.py` 是**适配层**：把 PHA 既有的 `TaskSendParams/Message` 与 a2a-sdk 标准协议互相翻译。**关键设计是"a2a-sdk 不可用时退回本地纯 dict 模拟协议"** —— 于是 v1 链路永远不会因为装不上 sdk 而挂掉。这是"新标准渐进接入、老协议不许断"的典型做法。

### ANP：跨组织的身份与信任（DID:WBA + Ed25519）

ANP 是唯一**跨出单机**的一层：让不同组织的智能体互相发现、互相验证身份。落点：

- `v2/did_wba.py` —— DID:WBA 身份（`did:wba:...`）
- `v2/anp_bridge.py` / `v2/anp_crawler.py` —— 跨域消息桥接与对端发现
- 每个领域智能体目录下都有自己的 `anp_bridge.py`（HealthAdvisor / HealthRecordsManager / MedicationReminder / VisitSummaryGenerator）
- 签名用 **Ed25519**，`domain_manifest.py` 描述本域能力供对端爬取

与 A2A 的区别：A2A 管"同系统内谁把活派给谁"，ANP 管"**别的组织**凭什么信你"。

### MCP 的传输链（含运行时生成的 starter）

工具不是静态注册的，链路是**运行时装配**的：

```
mcp_tool_adapter._ensure_http_starter()   按当前 agent 的工具清单
      ↓  生成/覆写  <agent>/mcpserver/_http_starter.py
子进程 python -m <agent>.mcpserver._http_starter   （mcp.run('streamable-http')）
      ↓
hostapi 以 HTTP 连上该子进程，取回工具清单
```

`_http_starter.py` / `_stdio_starter.py` 是**运行时生成物**：既**不被 git 跟踪**（`git ls-files` 查不到），也被 `.dockerignore` 排除（注释原话："别让这个雷埋着"）。原因是它按 agent 的**实际工具清单**重写 —— 若把它打进镜像，改一次工具就要重建镜像，且镜像里的旧清单会盖掉运行时的新清单。

### AG-UI 的实现要点

`copilotkit_runtime.py` 把内部的 `/v2/chat/stream`（事件名 `routing` / `tool_call` / `chunk` / `done` / `page_update`）**转译**成 AG-UI 的规范事件流：

```
RUN_STARTED → TEXT_MESSAGE_START → TEXT_MESSAGE_CONTENT* → TEXT_MESSAGE_END → RUN_FINISHED
                                ↘ TOOL_CALL_START → TOOL_CALL_ARGS → TOOL_CALL_END → TOOL_CALL_RESULT
```

四个不显然的设计决定（都写在代码注释里）：

1. **事件类型放在 JSON 的 `type` 字段里，而不是 SSE 的 `event:` 行。** 有些代理会剥掉 `event:` 行，放 body 里能活下来。
2. **`asyncio.Queue` + 独立 pump 任务**做背压解耦 —— 上游读得快、下游消费慢时不会互相拖死。
3. **收到 `done` 不能 `break`。** bridge 是**先发 `done`、再发 `page_update`** 的；一 break 就把尾部的页面动作丢了。这个 bug 的表现为"AI 答对了但页面不动"。
4. **PAGE_UPDATE 不从 `tool_result` 派生。** bridge 已经会发语义化的 `page_update` 事件，若再从 tool_result 推一次，前端会收到两份、触发重复 `setData`（闪烁 + 重复弹窗）。**单一来源**是这里的硬约束。

另外，上游 HTTP 状态码必须显式检查 —— 否则 401 会退化成"一句错误都没有的空回复"，用户只看到转圈。

---

## 4. 一次提问的完整生命周期

以**产品链路**（浮窗 → `/api/copilotkit` → `/v2/chat/stream` → AG-UI）为准：

```
① 前端浮窗 useChat.sendMessage(text)
     POST /api/copilotkit  { message: text, conversation_id }

② copilotkit_runtime._extract_user_message()  取出文本与 agent 提示
     POST http://localhost:13002/v2/chat/stream
     （conversation_id 透传成 A2A metadata.conversation_id）

③ bridge.v2_process_message_stream()           ← 流式编排主函数
     ③-1 路由（三层，短路优先）
          Layer 1: metadata.selected_agent  精确锁定
          Layer 2: host_graph._layer2_heuristic  关键词启发
          Layer 3: DomainManifest.host_agent_name  兜底默认智能体
          → yield {"event":"routing", ...}
     ③-2 澄清闸门
          host_graph._should_clarify()  判断问题是否太含糊
          → 需要澄清则 yield {"event":"clarification"} 并 return
            （**不走 agent**，避免拿模糊问题硬检索）
     ③-3 检索注入
          magnetic_rag.search(query, user_id, target_agent)
            → 多跳检索 + KG 图扩展 + rerank
          host_graph.crag_correct_node(...)
            → CRAG 决策：本地够不够？要不要联网？
          merged_context 前置拼进 query
          → yield {"event":"rag_context", ...}
          （整段失败一律降级为"无检索"，绝不打断对话）
     ③-4 调用智能体
          agent.stream(enriched_query, conversation_id, user_id)
          → 逐个 yield tool_call / tool_result / interrupt / chunk
     ③-5 兜底
          若 LLM 没吐最终文本但有工具结果 → 自动再调一次 LLM 总结
          而不是把 JSON 直接甩给用户

④ copilotkit_runtime 转译成 AG-UI 事件 → SSE
⑤ useChat 消费：chunk 累积渲染 / TOOL_CALL 出芯片 / PAGE_UPDATE 调页面方法
```

**两个防死循环护栏**（`bridge.py:556-584`）：`PHA_MAX_STREAM_SEC=60` 与 `PHA_MAX_STREAM_YIELDS=300`，任一超限则强制结束并用工具结果兜底成文。

### 一条值得单独讲的架构教训

`v2_process_message_stream` **从不调用 `host_graph`** —— 它自己做路由、直接 `agent.stream()`。而 host_graph 里恰好放着 `rag_retrieve`、`crag_correct`、`critique`（ReAct 反思）。

**结果**：P3 阶段做的全部 RAG 改造，在**真正的产品链路上一次都没执行过**，只有非流式的 `v2_process_message` 才会跑到。`/metrics` 上的 rerank / crag 指标恒为空 —— 而指标为空这件事，当时被当成了"没流量"，而不是"没接上"。

修法是在流式路径里补上"检索 → CRAG 决策 → 注入 context"，并与 host_graph 的 `invoke_agent_node` 保持**同样的注入格式**，让两条路径拿到一致的上下文。

> 这类"两条并行路径，一条接了新能力、另一条没有"的债，是多智能体系统里最隐蔽的一类。发现它的方式不是读代码，而是**问"这个指标为什么是 0"**。

**同源的第二处**：**长期记忆只在 `aggregate_node` 里写**（`host_graph.py:909`，写入点 `:967`，条件是 `user_id 非空 且 final_text 长度 > 20`，且在后台线程里做）。而 `aggregate_node` 只在 host_graph 里 —— 于是**流式路径（也就是产品链路）从来没写过一条长期记忆**。前端浮窗聊得再多，"记住我喜欢晨跑"也不会进记忆库。

另一处记忆写入在 `langchain_memory.py:615`（`PHALayeredMemory` 的 L3 层，`importance > 0.7` 才写），但 `PHALayeredMemory` 全仓**只在 `scripts/test_langchain_memory.py` 里被实例化过** —— 即只有测试用，产品链路没接。

> 所以本项目当前的"记忆"实际分两层：**会话内的多轮上下文**（靠 `thread_id` + checkpointer，已修好，见 §12）是真的能用；**跨会话的长期记忆**则因为写入点全在未执行的路径上，**基本是空转的**。这两件事经常被混为一谈，面试时要分清。

---

## 5. 智能体与工具

### 领域智能体（4 个）

| 智能体 | 职责 | 别名 |
|---|---|---|
| `health_advisor` | AI 问诊、健康教育、症状分析 | 健康顾问 |
| `health_records` | 健康档案增删查改、报告解读 | 健康档案管理员 |
| `medication_reminder` | 用药计划、服药提醒、剂量 | 用药提醒助手 |
| `visit_summary` | 就诊记录摘要 | 就诊摘要生成器 |

注册方式：`@register_agent(name=..., keywords=[...], tools_module=..., aliases=[...])` 装饰器（`agent_registry.py`）。`sub_agents.py` 里还留着一个注释掉的 `nutrition_advisor`，是**可扩展性的活证据** —— 加一个领域只需加一个装饰器块。

**路由是"一个请求只进一个智能体"**（除非显式指定 `parallel_agents`）。关键词命中即锁定；都不命中则落到 DomainManifest 的默认智能体。

### v2 编排层的文件职责

`backend/A2AServer/src/A2AServer/v2/` 下这几个文件的边界要分清，否则读代码会绕不出来：

| 文件 | 职责 | 关键点 |
|---|---|---|
| `bridge.py` | **流式编排主函数** `v2_process_message_stream` | 自己做三层路由 + 澄清闸门 + 检索注入，**不经过 host_graph** |
| `host_graph.py` | **LangGraph 编排图**（`build_host_graph`） | 非流式路径用；含 `rag_retrieve` / `crag_correct` / `critique` / `aggregate` 节点 |
| `v2_agent.py` | 单个领域 agent 的封装 | `stream()` 拼 `thread_id`、装配 checkpointer |
| `sub_agents.py` | 四个领域 agent 的注册与工具挂载 | `@register_agent(...)`；含注释掉的 `nutrition_advisor` |
| `magnetic_rag.py` | 多跳检索（见 §6） | 970 行 |
| `a2a_sdk_compat.py` | A2A 协议适配（见 §3） | a2a-sdk 缺席时退回 dict 模拟 |

**host_graph 的节点/边**（`host_graph.py:1147` 起）：`route` → `rag_retrieve` → `crag_correct` → `invoke_agent` → `critique` →（不通过则回 `invoke_agent`）→ `aggregate`。`aggregate` 是收尾节点，负责汇总文本、写指标、**写长期记忆**（见 §4）。

**`use_checkpointer=False`**（`host_graph.py:1237,1240`）：模块级单例图是**不带 checkpointer 编译**的。持久化不在图上做，而在 agent 层用 `AsyncPostgresSaver` —— 这是"图负责流程、agent 负责状态"的分工。注意 `v2_agent.stream()` 里那个 `cfg = {"configurable": {"checkpointer": None}}` 键**实际是空操作**（`_ensure_agent()` 建 agent 时已经带上了 checkpointer），别被它误导。

### MCP 工具

全仓 **70 个工具**，分两类：

- **领域工具**：各 agent 自己的 `mcpserver/*_tool.py`，用 `discover_mcp_tools_static(agent_name)` **按 agent 隔离加载** —— 没有全局聚合。
- **PhaCore 共享工具**（9 个）：`backend/PhaCore/mcpserver/shared_*.py`，跨 agent 复用。
  - `shared_ocr.py`：`extract_text_from_image`、`validate_medical_document`
  - `shared_page_control.py`：7 个页面操控工具（见 §7）

工具发现走 **AST 静态扫描**（`mcp_discover._extract_mcp_tools_from_source`），不 import、不执行用户代码。代价见 §11。

---

## 6. 知识层：Magnetic RAG + CRAG

这是全项目技术含量最高的部分，也是最能展开讲的部分。

### 6.1 双栈共存与 `embedding_model` 隔离

`rag_chunks` 表被**两套 RAG 栈共用**，靠 `embedding_model` 列区分：

| 栈 | 模型 | 维度 |
|---|---|---|
| v2 主链路 | DashScope `text-embedding-v4` | 384 |
| HealthAdvisor | `all-MiniLM-L6-v2` | — |

**坑**：v2 的检索 SQL 必须按 `embedding_model` 过滤，否则两套向量空间的余弦相似度会被混着算 —— 数值上不会报错，只会**悄悄返回一堆不相关的片段**。已在 `rag.py:360-364` 修掉。

> 这类"不报错、只是结果变差"的 bug，是最难靠测试发现的一类。它的可观测表现是"检索质量下降"，而没有人会为一个"感觉有点不准"报警。

### 6.2 Magnetic RAG（`v2/magnetic_rag.py`，970 行）

名字是 **Magentic**（不是 Magnetic），两阶段：

**Stage 1 — 单跳**
`should_retrieve` → `retrieve` → `evaluate_chunks` → （可选）`rewrite`，`MAX_REWRITE_COUNT=1`。

**Stage 2 — 多跳**（`search()` 默认走这条）
```
plan_retrieval  ┐ 并发发起
KG 实体抽取     ┘
      ↓
Hop 1  按 record_type 并行检索
      ↓
Hop 2  跨类型增强检索
      ↓
合并（按 chunk_id 去重，score 降序）
      ↓
KG 图扩展
      ↓
rerank
      ↓
evaluate_chunks
      ↓
（可选）rewrite → 重跑整条多跳
```

### 6.3 rerank：唯一被允许的"外部模型"

按项目约束，**不在本地部署任何模型**。重排走 DashScope HTTP API：

- 端点 `/api/v1/services/rerank/text-rerank/text-rerank`
- 模型 `gte-rerank-v2`，超时 8s
- **任何失败都返回 `None`，调用方保留原始向量顺序** —— 只记 Prometheus 指标，绝不抛异常

**实测收益：MRR 0.6167 → 1.0**（`magnetic_rag.py:701-704`）。这是全项目唯一一处有前后对比数字的检索优化，面试时值得单独说。

### 6.4 一个被"测量"否掉的优化

曾经想让 rerank 分数**短路**掉 `evaluate_chunks`（省一次 LLM 调用）。**被测量否决了**：

- `gte-rerank-v2` 的 `relevance_score` 实际落在 **0.16–0.35**
- LLM 的相关性判断落在 **0.95** 附近

两者是**不同的量纲**，找不到任何一个阈值能同时做到"可靠触发"和"不误判"。所以这个优化不是"没想到"，而是**想到了、试了、用数据否掉了** —— 这类"负结果"在面试里比正结果更有说服力。

### 6.5 CRAG（`v2/crag/`）

Corrective RAG，复用 Magnetic RAG 的 `evaluate_chunks` 结果做决策：

| 判定 | 阈值 | 动作 |
|---|---|---|
| `CORRECT` | ≥ 0.75 | 只用本地知识 |
| `AMBIGUOUS` | 0.30 – 0.75 | 本地 + 联网混合 |
| `INCORRECT` | < 0.30 | 只用联网结果 |

联网默认 **DuckDuckGo**（`duckduckgo_search.DDGS().text(..., backend="lite")`），可选 Tavily / SerpApi，并内置一个医疗领域的 `LocalMockProvider` 兜底 —— 保证**离线也能演示**。

> 注意边界：**rewrite 不属于 CRAG**，它是 Magnetic RAG 内部的单次重试。这两者经常被混为一谈。

### 6.6 知识图谱

三张表：`kg_entities` / `kg_relations` / `kg_entity_chunks`。

- **实体**（5 类）：symptom / medication / disease / allergy / vital_sign
- **关系**（6 类）：TREATS / CAUSES / MEASURES / CO_OCCURS / PRECEDES / FOLLOWS
- 抽取用 DeepSeek LLM
- 检索做 **2 跳双向 BFS**，再反查 chunk

**曾经的致命缺陷**：`index_document_with_kg` **没有任何调用方**，导致 KG 三张表**永远是空的**，图扩展是个静默空操作 —— 代码全对，功能全无。阶段 48-p3 才接上。

### 6.7 OCR 的三条并行链路

| 链路 | 路径 | 状态 |
|---|---|---|
| v2 上传管线 | PhaCore 共享 OCR → health_records MCPServer HTTP → Qwen-VL 多模态 | 三级 fallback |
| HealthRecordsManager | PaddleOCR 本地优先 → PhaCore `extract_text_from_image` | |
| PhaCore `shared_ocr.py` | 阿里云 2021 → 2019 → 本地 tesseract `chi_sim+eng` | **前两条是占位实现**，见 §11 |

结构化抽取（`data_extraction_tool.extract_medical_info`）对患者信息/诊断/用药走**正则**，对检验结果数值走 **DeepSeek LLM**。

---

## 7. 生成式 UI：页面操控管线

这是 48-29 阶段补齐的能力 —— **AI 不只是回答，还能操作界面**。
48-31 又把它拆成了**两条并行通道**（见 7.5）：幂等状态走 AG-UI 标准通道，瞬态动作走自定义事件。

### 7.1 契约

`src/ai/pageContract.js` 定义：

- **7 个页面组件**：`PageRouter` / `AiInfoCard` / `CurrentPage` / `Dashboard` / `HealthRecordsPage` / `MedicationPage` / `TodayDashboard`
- **12 个动作**：`setData` / `navigateTo` / `showAlert` / `refresh` / `openRecord` / `setFilter` / `setSearch` / `fillForm` / `askAgent` / `highlightAgent` / `setView`
- 队列参数：`PENDING_TTL_MS=10000`、`PENDING_MAX=20`

### 7.2 端到端链路

```
后端智能体调用工具 → 返回 {"page_update": {"actions":[...]}}
      ↓
bridge 扇出 page_update 事件
      ↓
copilotkit_runtime 转成 AG-UI PAGE_UPDATE
      ↓
useChat.jsx  handleEvent("PAGE_UPDATE")
      ↓
componentRegistry.call(component, action, params)
      ├─ 已注册 → 直接调页面方法 → setState
      └─ 未挂载 → 入队（TTL 10s、按签名去重、上限 20）→ 该页 register 时排空
```

**队列的三条不变量**（`ComponentRegistry.jsx`）：

1. **TTL 防陈旧** —— 10 秒前的页面指令不该再执行
2. **单次消费** —— 排空时走 `_invoke` 而不是 `call`，否则会自我循环
3. **JSON 签名去重** —— 同时防 SSE 重投递和 React StrictMode 的双次 effect

`unregister` **故意不清空队列** —— 页面切换（旧页 unregister → 新页 register）期间到达的指令必须活下来。

### 7.3 两条踩过坑的设计约束

**`CurrentPage` 模式**：`refresh` 这类动作与"用户当前在哪一页"有关。解法是**四个页面都注册同一个 `CurrentPage` 名字、只暴露 `refresh`**，后端无脑发 `CurrentPage/refresh` 就能命中当前页。因为总有页面挂载着，这条指令**永远走 `_invoke` 立即执行、不会进队列**。

**`CurrentPage/refresh` 绝不与 `navigateTo` 同批下发。** 两个动作在同一 tick 派发时，`navigate()` 只是排了个 state 更新，此刻**旧页面还挂着** —— refresh 会打在旧页面上。所以 `refresh_current_page` 只发一个动作、不导航。这条约束写进了代码注释。

### 7.4 参数归一化在工具里，不在模型里

`shared_page_control.py` 内置别名表，让模型直接传中文口语：

- 分类：`检查/化验 → exam`、`用药/药物/药品 → medication`、`过敏 → allergy` …
- 视图：`今天/今日 → today`、`本周/这周 → week`、`历史 → history`

**认不出就返回 `{"success": false, "error": ...}` 并列出合法值，不发 `page_update`** —— 让模型改口重问，好过静默展示全部内容。这是"宁可失败得响亮，也不要静默地做错"的取舍。

### 7.5 双通道：幂等状态走 AG-UI 标准 `STATE_DELTA`（阶段48-31）

**问题**：项目对外声称用 AG-UI，但页面控制走的是**自建**的 `PAGE_UPDATE` 事件，
绕开了 AG-UI 原生的 `STATE_SNAPSHOT` / `STATE_DELTA` 状态通道。全仓库 grep 确认**零处**发送 `STATE_*`。
对一个"用了 AG-UI"的项目来说，这是个说不圆的地方。

**解法不是替换，是分栏。** 判据只有一条 —— **幂等性**：

> 状态重放一次无害（"筛到检查"说两遍还是筛到检查）；动作重放一次会出事（弹窗重弹、toast 卡住）。

| 走 `STATE_DELTA`（幂等） | 保留 `PAGE_UPDATE`（瞬态 / 有副作用） |
|---|---|
| `navigateTo` → `route` | `setData`（卡片**追加**，后端不持有全量） |
| `setFilter` → `healthRecords.filter` | `openRecord`（打开弹窗，重放会重弹） |
| `setSearch` → `healthRecords.search` | `fillForm`（HITL 草稿，动作语义更清楚） |
| `setView` → `medication.view` | `showAlert`（toast，重放会卡住） |
| | `refresh`（**无状态可收敛**，硬做要假计数器） |
| | `askAgent` / `highlightAgent`（派发动作） |

**State schema**（刻意扁平、按页面命名空间化）：

```js
{
  route: "/v2/health-records",                          // string
  healthRecords: { filter: "exam", search: "血压" },     // 档案页
  medication:    { view: "week" }                        // 用药页
}
```

**链路**（与 7.2 并行，互不替代）：

```
工具返回 {"page_state": {route, healthRecords:{...}}, "page_update": {...}}
      ↓
bridge._page_state_to_json_patch 展平成 RFC 6902 ops
      ↓  yield {"event":"state_delta","delta":[...]}
copilotkit_runtime → _agui_event("STATE_DELTA", {delta, displaySummary})
      ↓
useChat.jsx  case "STATE_DELTA" → pageStateStore.applyPatch(delta)
      ↓
useSyncExternalStore 订阅 → 页面重渲染
      ↓
PageRouter 订阅 route → navigate()；档案页订阅 filter/search → 受控 Tabs/输入框
```

**三个设计细节**：

1. **`add` 而不是 `replace`** —— RFC 6902 规定 `add` 到**已存在的对象成员**即等于替换。
   所以后端**不需要知道前端当前状态**，也不用先查键在不在，无脑 `add` 就能表达"把 `/a/b` 设成 v"。
   这让"工具只声明自己改了什么"成立 —— 它不必持有全量 state。
2. **路径键做 RFC 6901 转义**（`~`→`~0`、`/`→`~1`，**顺序不能反**）。
   前端 `applyJsonPatch` 里做反转义时同理必须先解 `~1` 再解 `~0`，否则 `~01` 会被解成 `/`。
3. **`PageRouter` 的回写 effect 需要 `handledRouteRef` 守卫** —— 没有它，回写会在**同一次 commit** 里
   看到"route(B) ≠ 当前位置(A)"而把 route 改回 A，导航永远不发生。这个 bug 是写的时候发现的，不是跑出来的。

**为什么过渡期两条通道都发**：前端 `pageStateStore` 是唯一真相，页面的 `setFilter` / `setView` 动作
也写**同一个** store —— 两条路最终落到同一个值，**幂等无害**。换来的是：任何一端（后端镜像 /
前端 bundle）没重建成功，功能都不会坏。**没有 flag day。**

**顺带收益**：`filter_health_records` 原本发 `[navigateTo, setFilter]` **两个动作**，靠 `ComponentRegistry`
的待执行队列兜住"目标页还没挂载"。改成一次 state patch 后，页面挂载时直接读到 store 里的当前值 ——
**这条路径不再依赖队列**。队列仍然保留，供 `openRecord` / `highlightAgent` 这类真·动作使用。

**实测**（`tests/e2e/agui_smoke.py` 用例 E，走真实浮窗链路 `/api/copilotkit`）：

```
[E] 幂等状态   STATE_DELTA: 1  PAGE_UPDATE: 2
    STATE_DELTA: [{"op":"add","path":"/route","value":"/v2/health-records"},
                  {"op":"add","path":"/healthRecords/filter","value":"exam"}]
    路径: ["/route","/healthRecords/filter"]   判定: PASS
```

---

## 8. 数据模型（核心表）

| 表 | 用途 |
|---|---|
| `users` | 账号（`sha256(password+salt)`，见 §11） |
| `health_records` | 健康档案，`record_type` ∈ `other/lab_report/medical_report/symptom/allergy/…` |
| `medications` / `medication_plans` | 用药与计划 |
| `visit_summaries` | 就诊摘要 |
| `rag_chunks` | 向量块（`embedding_model` 区分双栈） |
| `kg_entities` / `kg_relations` / `kg_entity_chunks` | 知识图谱 |

**一个反复踩的坑：`record_type` 与前端 tab 词表是两套词表。** 库里实际是 `lab_report/medical_report/symptom/allergy/other`，而前端 `API_TO_TYPE` 只认 `diagnosis/examination/exam/report/allergy/medication` —— 结果 23/26 条档案落到 `other`，而 `other` **根本不是 tab 的 key**，点任何分类都是空的。48-29 补齐映射后 18/26 落到真实 tab（剩下 8 条 `other` 确实没有对应 tab，这是真实结果）。

### 8.1 `rag_chunks` 的 schema 漂移（同一个表，五个 DDL，三个维度）

这张表由**五处 `CREATE TABLE IF NOT EXISTS`** 各自声明 —— 谁先跑谁定表结构，后跑的因为 `IF EXISTS` 静默跳过：

| 出处 | 声明维度 |
|---|---|
| `backend/A2AServer/src/A2AServer/v2/rag.py`（文档注释） | `vector(384)` |
| `backend/HealthAdvisor/mcpserver/knowledge_tool.py:202` | `vector(384)` |
| `backend/health_records_api.py:764` 与 `:1153` | `vector(384)` |
| `database/migrations/V20250827000000__init.sql:31` | **`vector(1024)`** |
| `database/postgres/init/02_reminders_and_records.sql:142` | （随 env） |

而**运行时维度是环境变量驱动的**：`v2/rag.py:42` 默认 `384`，但 `.env:79` 写着 `EMBEDDING_DIM=1024`；更离谱的是 `monitoring_endpoints.py:398` 把默认值写成 `"1536"` —— **同一个列，三个数字**。

危险在于：表一旦按某个维度建好，另一条路径的 `%s::vector(384)` 字面量转换就会**直接报错**。所以"哪个维度生效"取决于**哪个服务先启动** —— 这是典型的"本地能跑、换台机器就炸"。

### 8.2 一次真实的多租户踩踏（已修，值得单讲）

`migrations/drop_legacy_rag_chunks_constraint.sql` 记录了完整事故：

- **现象**：用户 B 索引一个 `source_id` 已被用户 A 用过的文档时，`/v2/rag/index` 直接 500，报 `duplicate key value violates unique constraint`。
- **根因**：线上库上**同时存在两个唯一约束**。旧的 `(source_type, source_id, chunk_index, embedding_model)` **不含 `user_id`** —— 它把 `source_id` 当成全局唯一，于是跨用户互相踩踏。而 `rag.py` 的 `index_document` 是 `DELETE ... WHERE user_id=%s AND source_type=%s AND source_id=%s`（按用户删）再插 —— **删的粒度比约束的粒度细**，结果"删不掉别人的行，又插不进自己的行"。
- **修法**：新约束 `(user_id, source_type, source_id, chunk_index, embedding_model)` 是旧约束的**严格超集**，所以删掉旧约束不会放进任何"按租户语义本不该存在"的重复行，只是恢复了多租户隔离。用 `IF EXISTS` 保证幂等。
- **顺序陷阱**：必须**先删约束再删索引** —— 反过来先 `DROP INDEX` 会报 `cannot drop index ... because constraint ... requires it`。

> 这个事故的教训不是"少建约束"，而是**"约束的粒度必须和业务删除的粒度一致"**。两者不一致时，数据库不会报"你删错了"，只会报一个看起来无关的 duplicate key。

---

## 9. 安全与可观测

### 可观测

- **日志**：promtail 采集 → Loki → Grafana（3030）—— 这条链是通的
- **指标**：`/metrics` 端点暴露 rerank / CRAG / 限流等，**但是断的**：`docker-compose.yml` 里**没有 Prometheus 服务**，仓里也**没有 `prometheus.yml`** —— 没有任何东西去抓这个端点。所以指标只存在于"能被抓"的意义上，实际是死的。
- **审计**：指标审计开关 `USE_LLM_INDICATOR_AUDIT=true`

> **两个"看起来有、其实没有"叠在一起**：指标本身在流式路径接上 RAG 之前恒为空（§4），而就算不为空，也没有抓取端。排查时的表现都是"看板上没数据"，很容易被当成"没流量"。

### 安全

- **认证**：JWT HS256，24 小时有效期（`auth.py`）
- **限流**：`rate_limit.py`，可经 `PHA_RATE_LIMIT` 关闭
- **用户隔离**：`thread_id = "{user_id}:{session_id}"`；RAG 检索按 `user_id` 限定作用域（外加 `__global__` 公共知识）
- **依赖注入两档**：`get_current_user`（强制）与 `get_current_user_optional`（可选），后者用于公开但想识别用户的端点

**密钥的三种行为（同一个 `JWT_SECRET_KEY`）**：

| 位置 | 行为 |
|---|---|
| `auth.py:32` | 代码里硬编码兜底 `'your-secret-key-change-this-in-production'` |
| `docker-compose.yml:206,358` | `${JWT_SECRET_KEY:-dev-secret}` —— 缺省退化成字面量 **`dev-secret`** |
| `docker-compose.yml:261` | `${JWT_SECRET_KEY:?...}` —— 缺省**直接启动失败** |

`.env` 里**确实配了**一个 64 字符的强密钥（非占位值），所以当前部署是安全的。但**同一个密钥有三套缺省策略**：一套硬编码、一套退化成 `dev-secret`、一套直接崩 —— 换个环境少一个 `.env` 就会静默降级成可猜的密钥。

**健康数据的落盘状态（比"没加密"更糟的一种）**：`storage_tool.py` 里 **Fernet 加密是完整实现的** —— `encrypt_data`（`:42`）、`decrypt_data`（`:51`）、`get_or_create_encryption_key`（`:30`）都在。但全仓检索这两个方法的调用点，**除了 `page_control_tool.py:259` 的一句注释，没有任何地方调用**。`save_health_record`（`:67`）直接把明文 `content` 写进库。

> 所以这不是"我们没做加密"，而是"**加密做好了，没接上**"—— 前者是能力缺失，后者是**接线遗漏**，且因为代码看起来完备，review 时最容易滑过去。真正的 PHI 落盘是明文。

**已知问题**（详见 §11）：密码用 `sha256+salt` 而非 bcrypt/argon2；`ProtectedRoute` 在 DEV 模式**完全绕过鉴权**。

---

## 10. 部署

- `docker compose up -d` 拉起 13 个容器，前端 5174、后端 13002、Grafana 3030
- 镜像托管在阿里云 ACR（`crpi-*.personal.cr.aliyuncs.com`）
- **前端 nginx 的两个关键配置**：
  1. `resolver 127.0.0.11` + 变量形式的 `proxy_pass` —— 延迟 DNS 解析，修掉启动时 `[emerg] host not found` 的崩溃循环
  2. SSE 透传：`proxy_buffering off` + 300s 超时 —— 否则流式回复会被 nginx 缓冲成一坨
- CI：GitHub Actions 跑 15 个 `verify_stage*.py` + 一个**阻断式**工具重名守卫（`tests/test_tool_dedup.py`）

---

## 11. 技术债（诚实清单）

按"会不会在面试里被问倒"排序。**48-30 这一轮已修掉 5 条**（已修表），修法与实测证据见 §12。

### 已修（48-30）

| # | 问题 | 位置 | 修法 |
|---|---|---|---|
| 1 | 浮窗**不传 `conversation_id`** → 每轮都是新会话 | `useChat.jsx` + `copilotkit_runtime.py` | 浮窗用 `sessionStorage` 生成稳定会话 id 并透传；runtime 同时认 `conversation_id` / `thread_id` |
| 2 | 路由重复声明：`/health-records`、`/medication` 各声明两次 | `App.jsx` | React Router 6 首次声明生效 → 删掉前面的 v1 页面分支，让 `<Navigate>` 兼容重定向真正可达 |
| 3 | 死代码：`SmartChat.jsx`、`pages/Login.jsx`、`copilotkit-a2ui-stub.js`、`PageDataContext.jsx` | `src/` | 逐一确认零引用后删除；`PageDataProvider` 包裹层一并摘除 |
| 4 | 前端 `package.json` 带 `@copilotkit/react-core`、`@copilotkit/react-ui`、`playwright` 未用依赖 | `package.json` | 移除并重生成 lock（保留包 0 版本变动，删掉 375 个 @copilotkit 传递依赖） |
| 5 | **根目录陈旧 `api.py`（5323 行）** + **两个 v1 孤儿页面**（`HealthRecords.jsx` 921 行、`Medication.jsx` 719 行） | `./api.py`、`src/pages/` | 三者均为"被取代但没删"：`api.py` 是重构前快照，两个页面被阶段 44 的 `New*` 版本取代。全部 `git rm`，构建模块数不变（12066） |

> 第 5 条的甄别过程值得记一笔：`pages/Header.jsx` 一度也被我的孤儿扫描判为死文件，**复核时发现它被 `Home.jsx` / `ConversationPage.jsx` 以相对路径 `from "./Header"` 引用** —— 扫描脚本按 `pages/Header"` 匹配，漏了相对路径这种写法。**删除前必须用第二种方式复核。**

### 已修（48-31）

| # | 问题 | 位置 | 修法 |
|---|---|---|---|
| 1 | 自称用 AG-UI，页面控制却**全程绕开原生状态通道**（全仓 grep 零处 `STATE_*`） | `bridge.py` / `api.py` / `copilotkit_runtime.py` / `useChat.jsx` | 按**幂等性**把 12 个动作拆两栏：幂等状态走标准 `STATE_DELTA`（JSON Patch），瞬态动作保留自定义 `PAGE_UPDATE`。见 §7.5 |
| 2 | 5 个自定义事件（`routing` / `rag_context` / `clarification` / `interrupt` / `PAGE_UPDATE`）**裸发**，不是 AG-UI 规定的 `CUSTOM` 包裹形状 | `copilotkit_runtime.py` | 在**唯一出口** `_agui_event()` 上加 28 条标准事件白名单，非标准自动包成 `{"type":"CUSTOM","name":...,"value":...}`；前端 `useChat.jsx` 加 `case "CUSTOM"` 解包后**按原名字重新分发** —— 下游 5 个分支一行未改 |
| 3 | `TOOL_CALL_RESULT` **缺必填字段 `messageId`** | `copilotkit_runtime.py` | 补 `messageId: f"tool_{tc_id}"` + `role: "tool"`（由 `tc_id` 派生而非 `uuid4`，重投递时 id 稳定） |

> 第 1 条修得"保守"是刻意的：**过渡期两条通道都发**，且前端的页面动作也写同一个 store，
> 所以两条路收敛到同一个值、幂等无害 —— 任何一端没重建成功功能都不会坏，**没有 flag day**。

> **第 3 条是怎么被发现的（这一段比修复本身更值得讲）。**
> 第 2 条修完后，`agui_smoke.py` 的 F 用例全绿 —— 它检查的是**事件名**在不在标准白名单里。
> 但"名字合规 ≠ 结构合规"：一个事件名字对了、字段错了，照样过不了官方客户端。
> 于是补了一个**用官方 schema 本体**校验的脚本（`tests/e2e/agui_schema_check.mjs`，
> `require` 前端 `node_modules` 里的 `@ag-ui/core`，对真实 wire 上的每个事件跑 `safeParse`）。
> 首次运行就报出 **5 个 `TOOL_CALL_RESULT` 未过 `ToolCallResultEventSchema`：`messageId` 是必填的，我们没发**。
> 这个 bug 从项目第一天就在，**只有拿真 schema 打真流量才照得出来**。

### 未修

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| 6 | `api.py` **5581 行**单文件 | `frontend/hostAgentAPI/api.py` | 可维护性；任何改动都要在大文件里定位 |
| 7 | 密码 `sha256+salt`，非 bcrypt/argon2 | `auth.py:287` | 真实安全缺陷；GPU 爆破成本低 |
| 8 | **PHI 明文落盘**：Fernet 加解密**已实现但零调用** | `storage_tool.py:42,51` | 不是"没做加密"而是"加密做好了没接上"；`save_health_record` 直接写明文 |
| 9 | `JWT_SECRET_KEY` **三套缺省策略**（硬编码 / `dev-secret` / 直接崩） | `auth.py:32`、`docker-compose.yml:206,261,358` | `.env` 配了强密钥，但换环境少一个 `.env` 会**静默降级**成可猜密钥 |
| 10 | `/metrics` **无抓取端**：compose 里没有 Prometheus，仓里没有 `prometheus.yml` | `docker-compose.yml` | 指标端点形同虚设；看板无数据易被当成"没流量" |
| 11 | **长期记忆从不在产品链路写入**：唯一写入点 `aggregate_node` 只在 host_graph 里，而流式路径不过 host_graph | `host_graph.py:967` | 跨会话记忆基本空转（会话内多轮是好的，见 §4） |
| 12 | `PHALayeredMemory` 全仓**只在测试里实例化** | `langchain_memory.py:667` | 分层记忆 L1/L2/L3 在产品链路上没接 |
| 13 | `rag_chunks` **五处 DDL、三个维度**（384 / 1024 / 1536） | `rag.py`、`knowledge_tool.py:202`、`health_records_api.py:764,1153`、两处 `.sql` | 谁先启动谁定表结构，`IF EXISTS` 静默跳过；换机器可能直接炸（见 §8.1） |
| 14 | 阿里云 OCR 两个函数是**占位实现**，直接返回中文占位串 | `shared_ocr.py:68,107` | 走阿里云路径必然拿到占位文本；靠三级 fallback 掩盖 |
| 15 | AST 扫描**不认 `AsyncFunctionDef`** | `mcp_discover.py:164-221` | 写成 `async def` 的工具**静默消失**，不报错 |
| 16 | `pageContract.js` 是**字面量契约，无编译期校验** | `src/ai/pageContract.js` | 改名要同步 5 个后端文件，漏一个就静默失效。48-31 又添了一处同类耦合：`shared_page_control.py` 里 `page_state` 的**键名**必须与 `pageStateStore.js` 的 state schema 一致（`healthRecords` / `medication` / `filter` / `search` / `view`）—— 拼错一个字母，patch 会安静地写进一个没人读的键 |
| 17 | 全页聊天 `NewChat.jsx` **不消费 PAGE_UPDATE** | `pages/NewChat.jsx` | 只有浮窗能操控页面，两个聊天入口能力不一致 |
| 18 | 工具返回体超长会被 `[:4000]` 截断，`json.loads` 失败被 `except` 吞掉 | `v2_agent.py:559` → `bridge.py` | **page_update 静默消失** |
| 19 | `ProtectedRoute` DEV 模式绕过鉴权 | `ProtectedRoute.jsx:11-13` | 仅开发环境，但容易误带上线 |
| 20 | Recoil 基本名存实亡：24 个 atom，v2 页面全用 `useState` | `store/recoilState.js` | 依赖还在，实际不用 |
| 21 | 状态通道**只用下行**：从不把 `state` 放进 `RunAgentInput` 上行 | `copilotkit_runtime.py`、`useChat.jsx` | 符合 AG-UI 的"双向状态"只做了一半。后果是**后端不知道前端当前状态**，每次只能发全量 `add` patch（好在 RFC 6902 规定 `add` 到已存在成员即替换，所以不影响正确性，只是浪费带宽）。要做上行得让前端把 `pageStateStore` 的当前快照塞进请求体 |
| 22 | 无 `STATE_SNAPSHOT` 回退，也**不做状态压缩** | 同上 | 长会话里 patch 会一直累积。参考实现（`@ag-ui/client`）的做法是把 `STATE_SNAPSHOT` + 后续 `STATE_DELTA` **压成一条最终 `STATE_SNAPSHOT`** 再交给消费者 —— 我们没做，客户端重放整条历史才能还原状态。会话短的时候无所谓，长了会疼 |

> 第 13 条（五处 DDL）是这类病的剩余样本：**同一个东西有两份以上真相，且没有任何机制保证它们一致**。这类债的共同表现是"**读代码时读到了错的那份**"，而不是运行时报错 —— 本项目的架构调研就在已删掉的根目录 `api.py` 上踩过一次（第 5 条）。

---

## 12. 附：已实测验证的行为

以下不是"代码看起来对"，而是**跑出来看到过**的：

| 验证项 | 结果 |
|---|---|
| 9 个 PhaCore 工具加载 | `args_schema` 有真实字段名（`filter_health_records → ['category']`），且**均不含** `user_id` |
| `refresh_current_page` 不变量 | 恰好 1 个动作、`CurrentPage/refresh`、无 `navigateTo` |
| 分类别名 | 检查类→exam、药物→medication、MEDICATION→medication、这周→week 全部命中 |
| 档案分类映射 | 18/26 条落到真实 tab（修前仅 3 条） |
| 工具重名守卫 | 70 个工具，3 处跨 agent 重名降级为 WARN |
| **多轮记忆（不带 conversation_id）** | A1 说"我叫张三" → A2 问"我叫什么" → **答"没有可用的信息"**；两轮 `conversation_id` 分别为 `stream_1153efdb` / `stream_9a3ee8fb`（每轮新生成） |
| **多轮记忆（带稳定 conversation_id）** | B1 说"我叫李四，41岁" → B2 问"我叫什么" → **正确答"李四，41岁"** |

### 48-30 修复后的复测（走真实浮窗链路 `/api/copilotkit`）

| 验证项 | 结果 |
|---|---|
| 多轮记忆（A 组：带同一 `conversation_id`） | "记住：我叫王五，今年52岁" → "我叫什么名字？今年多大？" → **正确答出"王五, 52岁"** |
| 多轮记忆（B 组：不带 id，回归） | 仍然失忆 —— **证明修复没有影响不传 id 的老调用方** |
| 页面操控回归：筛档案 | "帮我打开健康档案页，只看检查" → **2 条 PAGE_UPDATE**，事件序列完整（`RUN_STARTED → routing → rag_context → TEXT_MESSAGE_* → TOOL_CALL_* → PAGE_UPDATE → RUN_FINISHED`） |
| 页面操控回归：刷新 | "刷新一下页面" → **恰好 1 条 PAGE_UPDATE**（不变量保持） |
| 页面操控回归：用药页 | "去用药页看看本周的" → **2 条 PAGE_UPDATE** |
| 前端构建 | `vite build` 成功（12066 模块，21.92s） |
| 容器产物 | 含 `pha_chat_conversation_id`、不再含 `PageDataProvider`；`/app/copilotkit_runtime.py` 含转发代码 |

**这几行是 §11 已修第 1-5 条的实测证据**：多轮记忆的能力本身一直是好的，缺的只是浮窗把会话 id 传下去；页面操控在改动后无回归；删除死代码后构建模块数不变（12066），证明删掉的确实不在构建图里。

### 48-31 双通道的实测（`tests/e2e/agui_smoke.py` 用例 E，已进常驻回归）

| 验证项 | 结果 |
|---|---|
| 幂等状态走标准通道 | "帮我打开健康档案页，只看检查的" → **`STATE_DELTA: 1`**，delta = `[{add,/route,/v2/health-records}, {add,/healthRecords/filter,exam}]` |
| 双轨并存 | 同一次调用 **`PAGE_UPDATE: 2`**（`navigateTo` + `setFilter`）照旧发出 —— 两条通道收敛到同一个 store |
| 瞬态动作未受影响（回归） | "我今天要吃什么药？" → `PAGE_UPDATE: 1`（`AiInfoCard/setData`），**没有** `STATE_DELTA` |
| A/B/D 三条既有硬断言 | 全 PASS，退出码 0 |
| JSON Patch 生成器（单测） | 嵌套展平、`/`→`~1`、`~`→`~0`、空 dict 整体赋值 —— 全部正确 |
| 前端 applier（单测） | 后端真实 ops 灌入：嵌套不冲掉兄弟键、转义对称、**同一条 patch 重放三次结果一致（幂等）**、空 ops 引用稳定 |
| 前端产物 | bundle 内含 `STATE_DELTA` 分支、三条 JSON Pointer 写回路径、`useSyncExternalStore` |

> "同一条 patch 重放结果一致"这条不是形式主义 —— **它是整个 STATE_DELTA 方案能成立的前提**。
> 状态通道的语义就是"收敛到声明值"，一旦某条 patch 不幂等，网络重投递就会把页面推向错误状态。

### 48-31 的 AG-UI 合规实测（`tests/e2e/agui_schema_check.mjs`，官方 schema 本体）

用 `@ag-ui/core@0.0.57` 的 zod schema 逐个校验真实 wire 事件（3 轮真实提问，走 `/api/copilotkit`）：

| 阶段 | 结果 |
|---|---|
| 修 CUSTOM 之前 | 5 个 `PAGE_UPDATE` / `routing` / `rag_context` 等**裸发**，官方客户端解析不出 |
| 修 CUSTOM 之后 | 639 个事件，**0 个非法** —— 但 `TOOL_CALL_RESULT` 报 5 个 schema 失败（缺 `messageId`） |
| 补 `messageId` 之后 | **657 个事件全部通过官方 schema ✓**；`CUSTOM` 里包着 `routing` / `rag_context` / `PAGE_UPDATE` |
| 冒烟测试 A/B/D/E/F | 全 PASS，退出码 0，945 个事件 0 非法 |

> 这个脚本**当场就抓到一个从项目第一天就存在的 bug**，而当时白名单守卫（F 用例）是绿的 ——
> 名字层面的合规和结构层面的合规是两件事，**只有拿真 schema 打真流量才照得出后者**。
