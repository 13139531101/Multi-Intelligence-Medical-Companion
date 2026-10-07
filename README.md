# 个人智能健康助手（PHA）

> 一个**多智能体个人健康助手**：用户用自然语言提问，系统路由到领域智能体，智能体调用 MCP 工具查库/调模型，答案以 SSE 流式返回，并能在前端**驱动页面动作**（导航、筛选、填表、刷新）。
>
> 技术主张不是「接了个大模型」，而是**四套协议各司其职**，以及在此之上把 RAG 做成了**可度量的多跳检索管线**。

---

## ⚡ 30 秒速览

| 项 | 数值 |
|---|---|
| 开发周期 | 2025-09 → 2026-10（约 12.5 个月，**独立开发**） |
| 提交 / Tag / 阶段 | **317** 次提交 · **52** 个 tag · **48** 个阶段 |
| 服务 | **13** 个容器（Docker Compose 一键拉起） |
| 智能体 | **4** 个领域智能体（+1 个注释掉的扩展位） |
| MCP 工具 | **70** 个（61 个领域工具 + 9 个跨 agent 共享工具） |
| 四协议 | MCP（agent↔工具）· A2A（agent↔agent）· AG-UI（agent↔界面）· ANP（跨组织） |
| 核心栈 | LangChain 1.x + LangGraph 1.x · FastAPI · PostgreSQL 16 + pgvector · Redis 7 · React 18 |
| 模型 | DeepSeek · Qwen-VL · DashScope Embedding/Rerank —— **全部走云端 HTTP API，不在本地部署任何模型** |

**四条最值得看的技术线**：

1. **[技术优势](#-技术优势)** —— 四协议分层、AI 真的会操作界面（幂等状态走 AG-UI 原生 `STATE_DELTA`）、可度量的检索优化、完整多跳 RAG 管线
2. **[智能体工程化](#-智能体工程化)** —— 加一个领域智能体 = 写一个 class，注册、路由、工具挂载、prompt 加载全自动
3. **[工具工程化](#-工具工程化)** —— 70 个工具按 agent 隔离发现，不 import 用户代码，且有阻断式重名守卫
4. **[约束与取舍](#-约束与取舍遇见问题怎么处理)** —— 每一条限制（不本地部署模型、双 RAG 栈、能力不对等的双路径）背后的判断与代价

---

## 🏆 技术优势

### 1. 四套协议各司其职，而不是「接了个大模型」

大多数「AI 应用」只有一层：调 LLM 拿回答。本项目按**边界**切成了四层，每层解决一个正交的问题：

| 协议 | 边界 | 解决什么 |
|---|---|---|
| **MCP** | agent ↔ 工具 | 这个智能体**能做什么** |
| **A2A** | agent ↔ agent | 这个智能体**能把活派给谁** |
| **AG-UI** | agent ↔ 界面 | 这个智能体**能怎么操作界面** |
| **ANP** | 组织 ↔ 组织 | **别的组织凭什么信你**（DID:WBA + Ed25519） |

「调用」这件事被切成四种，各自解耦。**A2A 还做了双轨**：v1 自研 JSON-RPC 协议与 v2 a2a-sdk 标准并存，中间有适配层，且 **a2a-sdk 缺席时自动退回纯 dict 模拟** —— 新标准渐进接入，老协议永不断。

### 2. AI 不只是回答，它**真的会操作界面**

这是最能当场演示的能力。用户说「打开上个月的血常规报告」，AI 自己跳转到档案页并弹出那条记录的详情。

**而且它按协议标准分了两条通道**，不是一股脑塞进自定义事件：

| 通道 | 语义 | 承载 |
|---|---|---|
| AG-UI 原生 **`STATE_DELTA`**（RFC 6902 JSON Patch） | 幂等的「我在哪、我在看什么」 | `route` / `filter` / `search` / `view` |
| 自定义 **`PAGE_UPDATE`** | 瞬态副作用 | `openRecord` / `setData` / `showAlert` / `refresh` / `askAgent` … |

分栏依据只有一条 —— **幂等性**：状态重放一次无害，动作重放一次会出事（弹窗重弹、toast 卡住）。所以「跳到档案页并筛到检查」现在是一次状态 patch，页面挂载时直接读到正确值，**连待执行队列都不需要**。

```
用户提问 → MCP 工具返回 {page_state, page_update}
              ├─ page_state  → JSON Patch → STATE_DELTA → pageStateStore → 页面订阅重渲染
              └─ page_update → PAGE_UPDATE → 组件注册表 → 未挂载则入队
```

支撑它的是一份**单一真相**的页面状态：模块级 store + `useSyncExternalStore`，AI 与用户交互（点 tab、打字搜索）写的是**同一个** store，不存在「AI 改一份、用户改另一份」。动作侧则是一个**带界面的组件注册表**：12 个动作、7 个页面组件、有界待执行队列（TTL 10s / 上限 20 / 按签名去重）。

> 迁移是**没有 flag day** 的：过渡期两条通道都发、收敛到同一个值，任何一端没重建成功功能都不会坏。patch 的**幂等性**单独测过（连放三次结果一致）—— 那是状态通道能成立的前提。实测证据见 `tests/e2e/agui_smoke.py` 用例 E。

**事件合规是拿官方 schema 验的，不是靠人看**。`tests/e2e/agui_schema_check.mjs` 直接 `require` 前端 `node_modules` 里的 `@ag-ui/core`，对真实流量上的每个事件跑官方 zod schema。写它的当天就抓到一个从项目第一天就存在的 bug：`TOOL_CALL_RESULT` 缺必填的 `messageId` —— 而当时「事件名白名单」守卫是**绿的**。**名字合规 ≠ 结构合规**，这层只有真 schema 打得出来。修完后 657 个真实事件全部通过。

**一次「agent 说我没权限」挖出五处缺陷。** 用户问「我做过心电图吗」，agent 答的是「我暂时没有直接打开档案详情的权限」—— 回答不算错，但一个 yes/no 问题拿到的是一句能力声明。顺着往下挖：前端不传 `selected_agent` → 四个 agent 的关键词**全不命中** → 流式路径的 **layer3 LLM 兜底只是一行注释**（等于不存在）→ 落到兜底 `health_advisor` → 而它 18 个工具里没有 `open_health_record`，**它的 prompt 却让它去调那个工具**。每一层单看都对，合起来才是 bug。修完还顺带发现 `routing` 事件**谎报层号**（`1 if selected_agent else 2`，一个永远取不到 3 的三元表达式）—— 不影响功能，但会让排障时看到的现象指向错误方向。详见 [ARCHITECTURE.md §11](docs/Chinese/ARCHITECTURE.md)。

### 3. 检索质量是**可度量**的，不是「感觉变准了」

- **18 条用例、4 组消融**（single/multi × vector/rerank）：**重排是多跳检索的必需项，不是锦上添花** —— 多跳不加重排 MRR 只有 **0.6667**，加上才回到 **0.95**（+0.283）；单跳上只 +0.022
- **一个优化被「测量」否掉了**：想让 rerank 分数短路掉 LLM 相关性判断（省一次调用），实测发现两者量纲不同（rerank 0.16–0.35 vs LLM 0.95），找不到可靠阈值 → **主动放弃**
- **负结果照实报**：重排在**简单查询上其实是负收益**（local_hit MRR 1.0 → 0.9333），是多跳上的大幅提升把它盖过去了；且我第一次只测单跳就下了「重排锦上添花」的结论，补了多跳消融才发现方向反了

> 「想到了、试了、用数据否掉了」和「做成了」一样是工程判断的证据。

### 4. 检索管线是完整的多跳架构

**Magnetic RAG**：规划检索 + KG 实体抽取并发 → Hop1 按 `record_type` 并行 → Hop2 跨类型增强 → 按 `chunk_id` 去重合并 → KG 图扩展 → 重排 → 质量评估 → 可选改写重跑。

**CRAG 纠正式检索**：检索质量自评 → `CORRECT` 只用本地 / `AMBIGUOUS` 本地+联网 / `INCORRECT` 只用联网。内置医疗领域 `LocalMockProvider` 兜底，**离线也能演示**。

**知识图谱**：5 类实体 × 6 类关系，2 跳双向 BFS 后反查 chunk。

### 5. 工程纪律：70 个工具，边界显式且有守卫

- **按 agent 隔离加载，没有全局工具表** —— `health_advisor` 拿不到写档案的工具
- **阻断式重名守卫**进 CI（三条判据，`continue-on-error: false`）
- **工具发现不执行用户代码**（AST 静态扫描兜底），宿主启动不依赖任何 agent 进程先就绪
- **工具包装用真实 `inspect.signature` 建 pydantic schema** —— 模型看得到真实参数名

### 6. 可扩展性：加一个领域智能体 = 写一个 class

注册、路由、工具挂载、prompt 加载全部自动接管。`sub_agents.py` 里留着一个注释掉的 `nutrition_advisor` 作为活证据。

### 7. 明确的架构约束，且守住了

**不在本地部署任何模型** —— 全部走云端 HTTP API（DeepSeek + DashScope）。需要重排就走 DashScope 的 `gte-rerank-v2`，且**任何失败都降级为「保留原始向量顺序」，绝不阻塞对话**。

这是成本/复杂度的主动权衡，不是能力妥协。

### 8. 工程成熟度

13 个容器 `docker compose up -d` 一键拉起 · 52 个 tag 的阶段化演进 · CI 跑 15 个阶段验证脚本 + 阻断式门禁 · 三层限流 · 写操作审计 · JWT 双 token 轮转 · 多模型路由与自动 fallback。

---

## 🤖 智能体工程化

### 加一个领域智能体 = 写一个 class

领域智能体通过装饰器声明，注册表自动接管其余一切：

```python
@register_agent(
    name="health_advisor",
    description="AI 问诊、健康教育、症状分析",
    keywords=["头疼", "发烧", "症状", "血压", "怎么办", ...],   # 参与启发式路由
    tools_module="health_advisor",                              # 决定加载哪个目录的工具
    aliases=["健康顾问"],                                        # 兼容前端传中文名
)
class HealthAdvisorV2(V2Agent):
    system_prompt = _load_prompt("HealthAdvisor", default="...")

    def get_tools(self):
        return (load_mcp_tools("health_advisor", transport=_MCP_TRANSPORT)
                + load_phacore_tools(("ocr", "page_control")))
```

装饰器只做一件事：把 `AgentSpec` + class 交给 `AgentRegistry`。**它必须返回原 class** —— 否则 import 时拿到的是 `AgentSpec` 而不是类，这是一个写在注释里的坑。

加一个新领域（比如「营养顾问」）需要动的地方：**一个 class 块**。`sub_agents.py` 里至今留着一个注释掉的 `nutrition_advisor` 作为活证据。

### 路由是三层短路

一个请求只进一个智能体（除非显式并行）：

| 层 | 依据 | 说明 |
|---|---|---|
| Layer 1 | `metadata.selected_agent` | 前端显式指定，精确锁定 |
| Layer 2 | 关键词启发式 | `AgentSpec.keywords` 命中即锁定 |
| Layer 3 | `DomainManifest.host_agent_name` | 都不命中时的兜底默认 |

关键词表是**按阶段迭代出来的**，不是拍脑袋写的。比如 `health_advisor` 在阶段 48-7 补进了「血压 / 血糖 / 怎么办 / 为什么」等高频词 —— 原因是此前用户问「血压高怎么办」会被路由到档案 agent，答非所问。

### 每个智能体加载自己的 prompt

四份 prompt 内容完全不同（顾问 12.5K / 档案 15.5K / 用药 9.3K / 摘要 10.2K 字符），**按目录显式定位**：

```python
system_prompt = _load_prompt("HealthAdvisor", default="...")
```

> **这里曾经藏着一个 40 个阶段没人发现的 bug**：旧实现把四个目录写死成一个候选列表，「谁先存在就用谁」。而 `hostapi` 的 Dockerfile 只整体 COPY 了 `HealthRecordsManager`（另外三个只 COPY 了 `mcpserver/`）—— 于是容器里**四个智能体全部加载了 HealthRecordsManager 的 prompt**。改 HealthAdvisor 的 prompt 完全没效果，且不报任何错。
>
> 静默退化正是它藏这么久的原因。修法是把 `agent_dir` 变成**必传参数**，找不到时**告警**而非静默退回。

### 编排层：图负责流程，agent 负责状态

`host_graph` 是 LangGraph StateGraph：

```
route → rag_retrieve → crag_correct → invoke_agent → critique →（不通过则回 invoke_agent）→ aggregate
```

- **`critique` 是 ReAct 反思节点**，判断 agent 的回答是否解决了问题，不通过则重跑
- **`aggregate` 是收尾节点**：汇总文本、写指标、写长期记忆
- 模块级单例图用 **`use_checkpointer=False`** 编译 —— **持久化不在图上做**，而在 agent 层用 `AsyncPostgresSaver`。这是刻意的分工：图管流程，agent 管状态。

### 记忆分两层，别混为一谈

| 层 | 机制 | 状态 |
|---|---|---|
| **会话内多轮** | `thread_id = "{user_id}:{session_id}"` + checkpointer | ✅ 可用 |
| **跨会话长期** | `aggregate_node` 写入 `AgentMemorySystem` | ⚠️ 见[已知限制](#-现状与已知限制) |

---

## 🔧 工具工程化

### 70 个工具，按 agent 隔离，没有全局工具表

| 来源 | 数量 |
|---|---|
| `health_advisor` 私有 | 18 |
| `health_records` 私有 | 19 |
| `medication_reminder` 私有 | 12 |
| `visit_summary` 私有 | 12 |
| `PhaCore` 跨 agent 共享 | 9 |

**没有全局聚合的工具表** —— 每个 agent 只看得见自己该有的工具。这保证了能力边界是显式的：`health_advisor` 拿不到写档案的工具。

### 发现链路：MCP 子进程优先，AST 静态扫描兜底

```
mcp_discover 扫描 <agent>/mcpserver/ 目录
      ↓
优先：spawn MCP 子进程（streamable-http），取回工具清单
      ↓ 失败
兜底：AST 静态扫描源码（不 import、不执行用户代码）
```

AST 兜底的价值是**宿主启动不依赖任何 agent 进程先就绪** —— 冷启动时不会因为某个 agent 没起来就整个失败。

代价是一条**必须记住的约束**：扫描器只认 `ast.FunctionDef`，**不认 `AsyncFunctionDef`**。写成 `async def` 的工具会**静默消失**，不报任何错。所以本项目所有 MCP 工具都写成同步 `def`。

### 运行时生成 starter，不打进镜像

MCP 子进程由运行时生成并覆写的 `_http_starter.py` 拉起：

```
_ensure_http_starter() 按当前 agent 的实际工具清单生成 <agent>/mcpserver/_http_starter.py
      ↓
python -m <agent>.mcpserver._http_starter  （mcp.run('streamable-http')）
```

这个文件**既不被 git 跟踪，也被 `.dockerignore` 排除** —— 因为它按实际清单重写，打进镜像反而会让旧清单盖掉新清单。`.dockerignore` 里的注释原话是：「别让这个雷埋着」。

### 工具包装：从 Python 函数到模型可调用的 schema

这是最容易被做错的一环。包装器用 `inspect.signature` 建**真实的 pydantic `args_schema`**：

```python
# ✅ 正确：模型看得到真实参数名
filter_health_records → args_schema 字段 ['category']

# ❌ 曾经的实现：def wrapped(**kwargs)
#    LangChain 只能推出一个不透明的 kwargs 参数 —— 模型看不到任何真实参数名，等于调不动
```

> **这个 bug 的表现极具欺骗性**：工具「存在」、能列出、能被选中，但模型**永远调不对**。而且失败是静默的 —— 没有异常，只是模型答得含糊。修好之后才验证出 `filter_health_records -> ['category']` 这样的真实 schema。

配套的一条约束：包装器会注册函数签名，而 `_inject_user_id_if_needed` **只对签名里含 `user_id` 的工具注入用户 id**。所以页面操控类的工具一律**不写 `user_id` 参数**，否则会被注入一个跟页面操作无关的值。

### 阻断式重名守卫

`tests/test_tool_dedup.py` 是 CI 里的**阻断式**门禁（`continue-on-error: false`），三条判据：

1. 同一 agent 内工具名唯一
2. PhaCore 内部唯一
3. PhaCore 名不撞任何 agent 的领域工具名

跨 agent 的**私有**工具重名只作 WARN 不判失败 —— 因为它们不在同一份工具列表里，运行时无冲突。当前 70 个工具中有 3 处这样的重名，全部已确认无害。

### 为什么有些工具默认跳过

`SKIP_TOOLS` 里有 5 个模块不加载，因为它们在 **import 期**就会建数据库连接或依赖外部 worker：

| 跳过的模块 | 原因 |
|---|---|
| `storage_tool` · `database_tool` | import 时即建 DB 连接 |
| `a2a_integration_tool` | 避免 agent 间循环调用 |
| `memory_integration_tool` | 记忆系统独立部署 |
| `async_analysis_tool` | 依赖外部 worker |

> ⚠️ 这是**有副作用的取舍**：`storage_tool` 被跳过意味着档案读取一度只剩 `page_control_tool` 一条路。该工具现已同时覆盖导航类与存在性提问（见[工程细节](#-值得一看的工程细节)）。

---

## ⚖️ 约束与取舍（遇见问题怎么处理）

这一节回答「限制是怎么处理的」—— 每条都写清楚**限制是什么、怎么处理、代价是什么**。

### 1. 不在本地部署模型

**限制**：本地模型拖慢镜像、吃内存、增加部署复杂度。

**处理**：所有模型能力走云端 HTTP API。唯一需要「模型」的地方是**重排（rerank）**，走 DashScope 的 `gte-rerank-v2`。

**代价与兜底**：网络调用会失败。所以 rerank **任何失败都返回 `None`，调用方保留原始向量顺序** —— 只记 Prometheus 指标，**绝不抛异常、绝不阻塞对话**。降级是静默的、可观测的，而不是中断的。

**收益**：18 条用例四组消融，**多跳 MRR 0.6667 → 0.95**（单跳 0.9333 → 0.9556）。
重排**在多跳上是必需项**：多跳把多来源片段拼在一起，候选池被稀释，bi-encoder 的 cosine 分不再能区分，只有 cross-encoder 一起看 query+doc 才排得对。

### 2. 两套 RAG 栈共用一张表

**限制**：`rag_chunks` 表被两套 RAG 栈共用（v2 主链路用 DashScope `text-embedding-v4`，HealthAdvisor 用 `all-MiniLM-L6-v2`）。

**处理**：加 `embedding_model` 列做隔离，v2 的检索 SQL **必须按它过滤**。

**不处理的后果**：两套向量空间的余弦相似度会被混着算 —— **数值上不报错，只是悄悄返回一堆不相关片段**。这类「不报错、只是结果变差」的 bug 最难靠测试发现，因为没有人会为一个「感觉有点不准」报警。

### 3. 一个被「测量」否掉的优化

曾经想让 rerank 分数**短路**掉 `evaluate_chunks`（省一次 LLM 调用）。**被测量否决了**：

| 来源 | 分数区间 |
|---|---|
| `gte-rerank-v2` 的 `relevance_score` | **0.16 – 0.35** |
| LLM 的相关性判断 | **0.95** 附近 |

两者是**不同的量纲**，找不到任何一个阈值能同时做到「可靠触发」和「不误判」。

**所以这个优化不是「没想到」，而是「想到了、试了、用数据否掉了」。** 负结果同样是工程判断的证据。

### 4. 从「这个指标为什么恒为 0」挖出的一条架构裂缝

**现象**：`/metrics` 上 rerank / crag 的指标**一直是空的**。当时的解释是「没流量」，但流量明明有。

**根因**：系统里存在两条消息处理路径，而它们**能力不对等** —— `v2_process_message_stream`（流式/产品链路）自己做路由、直接调 `agent.stream()`，**从不经过 `host_graph`**；而 `rag_retrieve` / `crag_correct` / `critique` 恰好只长在 `host_graph` 里。

**后果**：P3 阶段做的全部 RAG 改造，在**真正的产品链路上一次都没执行过**。这不是崩溃型 bug，是**沉默型**的 —— 功能看起来正常，只是悄悄少了三层检索增强，而唯一的信号是一个没人看的指标。

**修法**：在流式路径补上「检索 → CRAG 决策 → 注入 context」，并与 `host_graph` 的 `invoke_agent_node` 保持**同样的注入格式**，让两条路径拿到一致上下文。

> 这类问题的发现方式不是读代码，而是**盯住一个「不该是 0」的数字**。指标不是给运维看的装饰，是给自己留的破案线索。

### 5. 前端页面动作的两条硬约束

**约束 A：`CurrentPage/refresh` 绝不与 `navigateTo` 同批下发。**
两个动作在同一 tick 派发时，`navigate()` 只是排了个 state 更新，此刻**旧页面还挂着** —— refresh 会打在旧页面上。所以 `refresh_current_page` 只发一个动作、不导航。这条约束写进了代码注释。

**约束 B：`CurrentPage` 是「页面无关」的刷新出口。**
四个页面都注册同一个 `CurrentPage` 名字、只暴露 `refresh`，后端无脑发 `CurrentPage/refresh` 就能命中当前页。因为总有页面挂载着，这条指令**永远立即执行、不会进队列**。

### 6. 参数归一化放在工具里，不放在模型里

`shared_page_control.py` 内置别名表，让模型直接传中文口语：`检查/化验 → exam`、`用药/药物/药品 → medication`、`本周/这周 → week` …

**认不出就返回 `{"success": false, "error": ...}` 并列出合法值，不发 `page_update`** —— 让模型改口重问，好过静默展示全部内容。

这是「**宁可失败得响亮，也不要静默地做错**」的取舍。

---

## 🔍 值得一看的工程细节

### AI 操控页面（AG-UI）

多数「AI + 前端」项目止步于把回答渲染成文字。本项目让 **AI 直接操作页面**：用户说「打开上个月的血常规报告」，AI 会自己跳转到档案页并弹出那条记录的详情。

```
用户提问
   └─ MCP 工具 open_health_record(query, month)
        └─ 命中记录 → 返回 page_update.actions[]
             ├─ {component: "PageRouter",        action: "navigateTo"}  ← 跳页
             └─ {component: "HealthRecordsPage", action: "openRecord"}  ← 开详情
                  └─ bridge 扇出 → SSE page_update → AG-UI → 前端组件注册表
```

**导航与操作分离成两条动作**：跳页时目标页还没挂载，操作必然落空。所以前端组件注册表带一个**有界待执行队列**（TTL 10s / 上限 20 / 按 JSON 签名去重）：未注册的动作先入队，等组件挂载时再排空执行一次。

**`PageRouter` 常驻挂载**：它渲染 `null` 但始终在 `<Router>` 内，因此无论用户停在哪个页面，`navigateTo` 都能立即生效 —— 解决了聊天浮窗挂在 `<Router>` 之外、拿不到 `useNavigate` 的问题。

**AG-UI 转译层的四个不显然的决定**（都写在代码注释里）：

1. **事件类型放在 JSON 的 `type` 字段里**，而不是 SSE 的 `event:` 行 —— 有些代理会剥掉 `event:` 行，放 body 里能活下来
2. **`asyncio.Queue` + 独立 pump 任务**做背压解耦
3. **收到 `done` 不能 `break`** —— bridge 是先发 `done`、再发 `state_delta` / `page_update` 的；一 break 就把尾部的页面指令丢了。表现为「AI 答对了但页面不动」
4. **PAGE_UPDATE 不从 `tool_result` 派生** —— 否则前端收到两份、触发重复 `setData`（闪烁 + 重复弹窗）

### 几个「不报错但功能全无」的坑

| 现象 | 根因 |
|---|---|
| 知识图谱三张表永远是空的 | `index_document_with_kg` **没有任何调用方** —— 代码全对，功能全无 |
| 「档案找到了，但页面不跳」 | 同一工具走 in-process 返回 `dict`，走 MCP 返回 `[{"type":"text",...}]`。此前只认前者，MCP 通路下的 `page_update` 被静默丢弃 |
| 「有没有心电图检查报告」答「未找到」 | 存在性提问不触发档案检索，退到向量库（正文加密、未入库）必然答未找到 |
| 档案页点任何分类 tab 都是空的 | 后端 `record_type`（`lab_report`/`symptom`/…）与前端 tab 词表（`diagnosis`/`exam`/…）是**两套词表**，23/26 条落到一个不存在的 tab key |
| 401 变成「一句错误都没有的空回复」 | 上游 HTTP 状态码没检查，用户只看到转圈 |

> 共同点：**它们都不抛异常**。这类 bug 的排查方式不是看日志，而是**问「这个功能真的跑过吗」**。

### 检索管线

**Magnetic RAG**（多跳，`v2/magnetic_rag.py` 970 行）：

```
plan_retrieval  ┐ 并发发起
KG 实体抽取     ┘
      ↓
Hop 1  按 record_type 并行检索
      ↓
Hop 2  跨类型增强检索
      ↓
合并（按 chunk_id 去重，score 降序） → KG 图扩展 → rerank → evaluate_chunks →（可选）rewrite
```

**CRAG**（纠正式检索）：复用 `evaluate_chunks` 的结果做决策 —— `CORRECT`(≥0.75) 只用本地 / `AMBIGUOUS`(0.30–0.75) 本地+联网 / `INCORRECT`(<0.30) 只用联网。联网默认 DuckDuckGo，并内置一个医疗领域的 `LocalMockProvider` 兜底，**保证离线也能演示**。

> 注意边界：**rewrite 不属于 CRAG**，它是 Magnetic RAG 内部的单次重试。这两者经常被混为一谈。

**知识图谱**：5 类实体（symptom / medication / disease / allergy / vital_sign）× 6 类关系（TREATS / CAUSES / MEASURES / CO_OCCURS / PRECEDES / FOLLOWS），检索做 2 跳双向 BFS 后反查 chunk。

---

## 🗺️ 后续计划

> 完整的技术债清单、优先级与复现路径在 **[ARCHITECTURE.md §11](docs/Chinese/ARCHITECTURE.md)** 与 **[INTERVIEW_PREP.md](docs/Chinese/INTERVIEW_PREP.md)** 的「边界」章节 —— 这份 README 只写**路线图**。

### 近期 · 工程收口

- **拆分 `api.py`**（5581 行）→ A2A Host / 编排器 / AG-UI 转译层 / REST API 四层分离
- **收敛 `rag_chunks` schema** → 五处 DDL 合并到一份权威 migration，维度由单一配置源驱动
- **把加密真正接上写路径** → Fernet 已完整实现，接入 `save_health_record` 即闭环
- **密码哈希升级** → `sha256+salt` → bcrypt / argon2
- **给安全机制加「调用链证据」CI 检查** → 让「实现了但没被调用」这类问题在 CI 阶段暴露
- **跨会话长期记忆接通流式路径**（会话内多轮记忆已修复）

### 中期 · 产品化

- **移动端适配** —— 目前仅桌面端布局
- **告警出口** —— Prometheus + Grafana + Loki 已部署，补告警规则与通知渠道
- **并发/延迟基线** —— 补压测与 SLO
- **多租户行级数据隔离**
- **两个聊天入口能力对齐** —— 浮窗可操控页面，全页聊天补齐同一能力

### 长期 · 方向

- **检查报告图像直接理解** —— 减少 OCR → 结构化的信息损耗
- **可穿戴设备数据流式入库**
- **就诊摘要双向流转** —— 从「患者自用工具」扩展为「医患沟通介质」
- **端到端加密与零知识存储** —— 服务器不可读的健康数据

---

## 🚀 怎么跑起来

```bash
# 1. 准备环境变量（.env 需含 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY / JWT_SECRET_KEY 等）
cp .env.example .env    # 若不存在，参考 docker-compose.yml 里的 environment 段

# 2. 拉起全部 13 个容器
docker compose up -d

# 3. 访问
#    用户端      http://localhost:5174     （默认落地 /v2/dashboard）
#    Grafana     http://localhost:3030
#    后端 API    http://localhost:13002
```

**改代码后必须重建容器才生效**（无热重载）：

```bash
docker compose build hostapi multiagent_front && docker compose up -d hostapi multiagent_front
```

**跑测试**（工具重名守卫，CI 里的阻断式门禁）：

```bash
# 脚本自带 __main__ 入口，不需要 pytest
docker compose cp tests/test_tool_dedup.py hostapi:/tmp/td.py
docker compose exec -T hostapi sh -c "cd /app && python /tmp/td.py"
```

> 容器里**没有 pytest、也没有 `/app/tests/`** —— 所以是 `cp` 进去当普通脚本跑。CI 里同样是 `python tests/test_tool_dedup.py`，不是 pytest。

> ⚠️ 工具清单、agent 实例、生成的 starter 有**四处缓存**，改工具或 agent 后必须重启 hostapi，否则改动静默不生效。

---

## 📚 文档索引

| 文档 | 内容 |
|---|---|
| **[docs/Chinese/ARCHITECTURE.md](docs/Chinese/ARCHITECTURE.md)** | 完整架构：服务拓扑、四协议分层、请求生命周期、知识层、数据模型、技术债清单、**已实测验证的行为表** |
| **[docs/Chinese/INTERVIEW_PREP.md](docs/Chinese/INTERVIEW_PREP.md)** | 19 个技术难点深挖（现象 → 根因 → 修法 → 为什么难发现）+ 演示脚本 |
| [docs/README.md](docs/README.md) | 文档索引与开发约定 |

---

## 📖 项目愿景

本项目旨在打造一个私密、智能、贴心的个人健康管理助手。通过多智能体、RAG、OCR 等技术，将用户的个人病历、检查报告、用药记录等信息安全地整合为个人健康知识库，并在此基础上提供从日常健康咨询、用药提醒到辅助就医沟通的全方位智能服务。

> **核心理念**：本项目是一个**辅助性**健康管理工具，**不提供、也绝不替代**任何形式的医疗诊断或治疗建议。所有输出仅供参考，用户在做出任何医疗决策前必须咨询专业医生。

### 核心功能

**1. 个人健康知识库构建** —— 拍照（OCR）/ 上传（PDF、Word、图片）/ 手动录入；自动提取诊断、检查指标、药物名称等结构化信息；加密存储。

**2. 智能健康咨询** —— 症状初步问询（基于用户过往病史、过敏史给出缓解建议并**强烈建议及时就医**）；健康知识问答。

**3. 辅助就医与医患沟通** —— 就诊前自动生成摘要：近期主要症状、与智能体的对话要点、完整病史/手术史/过敏史、关键检查的历史结果回顾。患者可出示给医生，提升沟通效率。

**4. 贴心的用药与复诊提醒** —— 按处方自动创建服药提醒并记录依从性；药品库存预警；复诊提醒。

---

_本项目基于 A2A-MCP Server 框架进行开发。_
