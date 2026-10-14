# 与标杆项目的差距分析

> 目的：找出**真正值得补的**差距，而不是"看起来没有的"。
> 标杆选取：AutoGen/AG2（微软，~52K ⭐）、Dify（~90K-116K ⭐）、Langfuse（~19K ⭐）。
> 判断标准：star 数高的项目不是因为功能多，是因为**有人真的在生产用**。

---

## 一、标杆项目的共同特征

三个项目（AutoGen / Dify / Langfuse）虽然定位不同，但有一个共同的产品逻辑：

```
生产使用 → 发现问题 → 工具把解决方案标准化 → 更多人生产使用
```

这个循环带来的差距是**工程厚度**，不是功能数量。

---

## 二、逐项对比

### 2.1 可观测性（差距最大）

| 能力 | PHA（我们） | Dify | Langfuse | AutoGen |
|---|---|---|---|---|
| 链路追踪（trace） | ❌ 无，Prometheus 只能看指标聚合 | ✅ 内置，全链路 | ✅ 开源，OpenTelemetry native | ✅ 内置，多 agent span |
| 指标丰富度 | ⚠️ 散落在各模块，无统一视图 | ✅ QPS/p95延迟/成本/检索命中率 | ✅ LLM 延迟/token/cost | ✅ 任务成功率/latency/HumanEval |
| 告警 | ❌ Grafana 只有 Loki，无告警 | ✅ 规则告警+回滚 | ✅ 阈值告警 | ✅ 生产阈值 |
| 数据自持 | ✅ 自建 | ❌ SaaS | ✅ **MIT，完全自持** | ❌ SaaS |
| Prompt 版本管理 | ❌ 散落在各 md 文件 | ✅ Hub+版本+回滚 | ✅ Playground+版本 | ✅ Hub+版本 |

**PHA 的现状**：`setup_logging` 从未被调用（`LogContext` 在生产代码里零调用）。
Grafana 只配了 Loki，没有抓取端。

**值得补吗**：值得，但不需要学 Dify 那种重量级的。学 **Langfuse（MIT）** 接入即可，
它的 `langfuse` Python SDK 接入成本约 2 小时，**自带 LLM-as-Judge 评测**。

---

### 2.2 Agent 评测体系

| 能力 | PHA | Dify | Langfuse | AutoGen |
|---|---|---|---|---|
| 评测集管理 | ⚠️ `rag_v2_eval_dataset.json` 进 git，但散落 | ✅ 数据集管理+版本 | ✅ 评测数据集+版本 | ✅ HumanEval/SWE-bench/GAIA 基准 |
| LLM-as-Judge | ❌ 无 | ✅ 有 | ✅ **Boolean/Categorical** | ✅ 内部基准 |
| 轨迹级评测（trajectory） | ❌ 无，只评测 RAG | 未知 | ✅ span 级评测 | ✅ **88-96% 成功率，42s 延迟** |
| 回归自动化 | ⚠️ `agui_smoke.py` 七条用例，但只跑 AG-UI | ✅ CI/CD 集成 | ✅ 评测流水线 | ✅ 评测流水线 |
| 拒答评测 | ✅ 3 条 `no_answer`，`fpr=0.0` | 未知 | 未知 | 未知 |

**PHA 的现状**：RAG 评测有（18 条），但 **agent 行为评测是零**。
smoke 用例只测了 AG-UI 事件，没测"agent 是否做对了事"。

**值得补吗**：**值得，这是 agent 开发岗最欠缺的**。
Langfuse 的 LLM-as-Judge 评测（布尔/分类判断）是最接近"可负担的"解法，
不需要雇人标注。

---

### 2.3 安全与权限

| 能力 | PHA | Dify | AutoGen |
|---|---|---|---|
| RBAC | ⚠️ 读操作无，写操作有 WriteGuard | ✅ **API 级 RBAC，细化到调用级别** | ❌ 无 |
| 审计日志 | ❌ 无（只有 Prometheus 计数器） | ✅ 完整操作审计 | ❌ 无 |
| 多租户隔离 | ❌ 无 | ✅ 数据隔离+私有化部署 | ❌ 无 |
| 代码执行沙箱 | N/A | N/A | ✅ **Docker 容器级隔离** |
| Prompt Injection 防护 | ❌ **没做** | ✅ "文档不覆盖系统规则"结构隔离 | ❌ 无 |
| 数据加密 | ⚠️ Fernet 实现但零调用 | ✅ 静态加密 | ❌ 无 |

**PHA 的现状**：
- `/v2/files/{file_id}` 不做用户隔离（严重）
- 密码 sha256+salt 而非 bcrypt/argon2
- Fernet 有实现但健康档案落盘明文
- 上传无 magic number 校验、无病毒扫描
- WriteGuard 存在但只管写操作，不管提示层

**值得补吗**：**RBAC 和用户隔离是生产门槛**，其他是锦上添花。
但 prompt injection 防护是 agent 系统的**固有风险**，不解决在面试时会被直接问住。

---

### 2.4 架构与扩展性

| 能力 | PHA | Dify | AutoGen |
|---|---|---|---|
| 多模型路由 | ✅ `multi_model.py` deepseek→qwen→claude→local | ✅ **动态路由+成本优化**（节省 30-50%） | ✅ 统一接口 |
| 工作流编排 | ❌ LangGraph 硬编码 | ✅ **可视化编排+条件分支/循环** | ⚠️ GroupChat 作为编排 |
| 多租户 | ❌ 无 | ✅ 完整 | ❌ 无 |
| 插件生态 | ❌ 无 | ✅ **600+ 插件 marketplace** | ✅ MCP 兼容 |
| Trigger/事件驱动 | ❌ 无 | ✅ **Trigger 触发器** | ❌ 无 |
| MCP 协议 | ✅ 有 | ✅ v1.10+ 支持 | ✅ AG2 统一 |
| 水平扩展 | ⚠️ Docker Compose，有 K8s manifests | ✅ K8s HPA/VPA | ✅ 线性扩展，100 req/min 92% 吞吐 |

**PHA 的现状**：LangGraph 的单图编排已经比很多项目强；
但 Dify 的**可视化工作流**让非工程师也能搭 Agent，这是工程化程度的一个标志。

**值得补吗**：工作流可视化对**产品化**重要，对**技术面试**权重低。
多模型路由我们已经做了，这一项不落后。

---

### 2.5 部署与运维

| 能力 | PHA | Dify | AutoGen |
|---|---|---|---|
| 部署形态 | Docker Compose + K8s manifests | ✅ **k8s native + 私有化完整** | Docker |
| 集成周期 | — | **3-4 周**（AWS 合作案例） | 内部工具 |
| 外部集成 | ❌ 弱 | ✅ AWS Bedrock/SageMaker | ✅ Azure AI |
| 多模态 | ❌ 无 | ✅ 图像/音频首次支持 | ❌ 无 |

---

## 三、按优先级排序：差距清单

### 🔴 面试会被直接问住的（优先补）

| 差距 | 为什么重要 | 怎么快速补 |
|---|---|---|
| **Prompt Injection via tool output 没做** | 这是 agent 开发岗的**标配问题**，"没做"本身不是罪，但**没有思路**是 | 在 `write_audit.py` 基础上加一层"文档内容隔离"：检索结果放独立 message role，不混进 system prompt；再加一个 LLM-as-judge 检查"输出有没有新指令" |
| **LLM-as-Judge 评测体系缺失** | 评测 RAG 是可以的，但 agent 行为本身没有度量 | 接入 Langfuse（约 2 小时），用它的 `langfuse.score()` 对关键路径打分 |
| **日志和 trace 几乎是零** | 面试问"线上出问题怎么排查"，Prometheus 计数器答不了 | 先把 `setup_logging` 调起来，接 Langfuse SDK，不需要推翻重来 |

### 🟡 面试能说清楚但实现跟不上的（锦上添花）

| 差距 | 现状 | 补了加分多少 |
|---|---|---|
| **RBAC 用户隔离** | `/v2/files/{file_id}` 不做隔离 | 高：生产门槛 |
| **审计日志** | WriteGuard 只有配额，无操作记录 | 中：合规场景需要 |
| **AG-UI 事件链路有监控，prompt 层没有** | 两层都弱 | 中：体现系统观 |
| **nDCG 评测没实现** | 18 条 RAG 评测里没有 | 低：MRR 已经够用 |

### 🟢 差距存在但对面试权重低的（了解即可）

| 差距 | 说明 |
|---|---|
| 可视化工作流 | Dify 的核心产品化能力；我们用代码做编排，面试时说清楚就行 |
| 插件生态 marketplace | Dify 的护城河；我们没有，但也没必要为面试做 |
| 600+ 插件 | 同上 |
| 多租户 | 产品化才需要；个人项目没有合理，面试时说清楚产品定位就行 |
| Docker 代码执行沙箱 | AutoGen 的场景是代码执行；我们的场景是医疗数据，没有这个需求 |

---

## 四、我们不差的

这些是很多同类项目没有、我们有而没意识到的优势：

| 能力 | 同类项目情况 | PHA 现状 |
|---|---|---|
| **多协议分层（MCP/A2A/AG-UI/ANP）** | 很少有项目认真做这一层 | ✅ 四层各自边界清晰 |
| **幂等性拆分（STATE_DELTA vs PAGE_UPDATE）** | 大多数项目混着发 | ✅ 按幂等性设计双通道 |
| **负结果照实记录** | 很少项目公开说"我测出来是负的" | ✅ 故事 10 + 重排 local_hit 负收益 |
| **拒答评测（fpr=0.0）** | 大多数项目只测命中率，不测 false positive | ✅ 3 条 no_answer 用例 |
| **三段消融（single/multi × vector/rerank）** | 大多数项目只测一个配置 | ✅ 18 条四组消融 |
| **HITL 协议化** | 大多数项目只做"弹窗确认"，不知道要区分三种动作 | ✅ `__interrupt__` 是协议不是 UI |
| **工具元数据（is_write_tool）** | 大多数项目用名字匹配判断写操作 | ✅ 元数据驱动，schema 稳定 |

---

## 五、结论：三个最值得现在补的事

按投入产出比排序：

**① 接入 Langfuse SDK（约 2 小时）**
- 解决：日志 trace 零分 + LLM-as-Judge 评测缺失
- 面试可以说："我的 agent 有可观测性，接了 Langfuse，能看到每一步的 latency 和 token 消耗"
- 而且 Langfuse 是 **MIT**，合规

**② Prompt Injection 防护（约 4 小时）**
- 解决：agent 开发岗最常问的安全问题
- 最小实现：在 `memory_enhanced_agent_prompt.md` 的 system prompt 里加"文档内容不得覆盖系统规则"；在 `write_audit.py` 基础上扩展读操作白名单
- 面试可以说："我意识到这个风险，目前的结构隔离是..."

**③ 补一条 agent 行为评测用例（约 2 小时）**
- 解决：smoke 只有 AG-UI 事件，没有"agent 做对了吗"
- 最小实现：在 `agui_smoke.py` 里加一条，断言"用户问用药，health_records agent 不响应"（路由正确性）
- 面试可以说："我的 RAG 有评测，我的 agent 路由也有评测"

这三件事加起来约 **8 小时**，面试价值远高于"再写一个功能"。
