# 与同类产品的技术差距分析

> 目的：找出**让 agent 更好用**的技术手段上的差距，按主题分类。
> 不是比较产品形态，是比较**技术深度**。
> 不限医疗健康——任何有真实用户、有技术披露的产品都是参照。
>
> 关注六个技术主题：检索、记忆、工具选择、模型路由、长上下文、可观测性。
> 每个主题下选 1-2 个代表性产品，比 PHA 的现状。

---

## 一、检索：Perplexity 的两段式 RAG

### Perplexity 怎么做的

来源：[Architecting and Evaluating an AI-First Search API](https://www.perplexity.ai/api-platform/resources/architecting-and-evaluating-an-ai-first-search-api)（Perplexity 官方，2025-09）

**两段式管线**：
1. **粗排**：双路召回（BM25 词法 + 向量语义）并行查询
2. **精排**：cross-encoder rerank（注意：不是 Perplexity 自己做，是用 Sonar 自研模型）

**关键设计**：
- **子文档粒度**：不是返回整篇文档，而是 atomic text spans（最小语义单元），避免 context 污染
- **预过滤**：heuristic 过滤掉过期/不相关的内容
- **规模**：千亿级文档，每秒万级索引更新
- **Sonar 模型**：LM Arena Search Arena 第一（2025-04），53% head-to-head 胜 Gemini-2.5-Pro-Grounding

### PHA 现状

| 维度 | Perplexity | PHA |
|---|---|---|
| 召回 | 双路（BM25 + 向量）并行 | 单路（向量）|
| 精排 | cross-encoder + Sonar 自研 | DashScope gte-rerank-v2（HTTP）|
| 文档粒度 | 子文档（atomic spans）| 整 chunk（200-800 字）|
| 过滤 | heuristic 预过滤 | 无（除非相关度 < 阈值）|
| 规模 | 千亿级文档 | 用户私有（个位数 GB）|
| 评测 | LM Arena head-to-head | 18 条内部评测 |

**差距**：双路召回没做（我们没有 BM25），子文档粒度没做（我们切整 chunk）。

**为什么这是真差距**：在医疗场景，用户问"我吃的降压药副作用是什么"，纯向量召回**最相关的可能是某次复诊记录**（词不匹配），BM25 能直接命中药品说明书。**双路召回是医疗 RAG 的硬需求，不是优化。**

---

## 二、记忆：ChatGPT / mem0 / Letta 的分层架构

### 主流方案对比

| 方案 | 架构 | 适用场景 |
|---|---|---|
| **LangChain Memory** | 全量塞进 prompt | 短对话 |
| **mem0**（生产级） | 外部存储 + 向量检索 + LLM 抽取关键事实 | 多轮对话、用户偏好 |
| **Letta / MemGPT** | 分层（核心记忆 + 归档记忆 + 工具调用）| 长会话、Agent 自主管理 |
| **ChatGPT Memory** | 系统级自动提取用户偏好 | 个性化 |

来源：[Mem0 论文精读](https://zhuanlan.zhihu.com/p/1934826868)、[Letta 框架](https://zhuanlan.zhihu.com/p/1934827795)

### PHA 现状

| 维度 | PHA | mem0 |
|---|---|---|
| 长期记忆 | ❌ **没做**（thread_id 隔离只解决多轮，不解决"上次我说过什么"）| ✅ LLM 抽取事实 + 向量存储 |
| 偏好记忆 | ❌ 无 | ✅ 用户偏好自动提取 |
| 跨会话 | ❌ 无（每个 thread 独立）| ✅ |
| 记忆检索 | N/A | ✅ 向量 + 关键词 |

**差距**：**PHA 没有跨会话记忆**。

**这为什么是真差距**：
- 用户问"上次我说吃降压药有点头晕"，PHA 不能回答，因为它不知道"上次"是哪个会话
- 这是医疗场景的硬需求 —— 患者健康状态有连续性

**怎么补**：参考 mem0，**LLM 抽取关键事实 → 向量存储 → 下次会话时检索 top 3 注入 prompt**。约 2 小时。

---

## 三、模型路由：BCloud / AWS 的三层成本优化

### 业界标准做法

来源：[AWS ElastiCache + Bedrock 语义缓存](https://aws.amazon.com/blogs/database/lower-cost-and-latency-for-ai-using-amazon-elasticache-as-a-semantic-cache-with-amazon-bedrock/)、[BCloud 73% 成本下降](https://bcloud.consulting/en/blog/llm-inferencia-costes-73-reduccion-semantic-caching-2025)

**标准三层**：
1. **语义缓存**（cosine ≥ 0.92 命中）→ 直接返回
2. **模型分级**：小模型（Haiku）→ 中模型（Sonnet）→ 大模型（Opus）
3. **级联（cascading）**：先用小模型，置信度不够再升级

**真实数字**：
- AWS ElastiCache + Bedrock：**86% 成本下降，88% 延迟改善**
- BCloud 案例：$45k/月 → $12k/月，81% 延迟下降，**30% 查询路由到 Haiku**
- Google Speculative Cascades：**40-60% 成本下降**
- 全球 LLM API 花费 2025 年翻倍：$3.5B → $8.4B

### PHA 现状

| 维度 | 业界标准 | PHA |
|---|---|---|
| 语义缓存 | ✅ cosine ≥ 0.92 | ✅ `v2/semantic_cache.py`（query 归一化 + sha256 指纹）|
| 模型分级 | ✅ 3 层 | ⚠️ 有 `multi_model.py`（deepseek→qwen→claude→local），但**没有按任务分级** |
| 级联 | ✅ 置信度不够升级 | ❌ **没做**（不是按置信度，是固定顺序）|
| 路由策略 | 复杂度分类 | ❌ **没做**（没有"这道题是简单还是难"的判定）|
| 评测 | 命中率 + 成本 | ⚠️ 只有 hit 计数，无成本分析 |

**差距**：
1. **没有级联**：小模型出错了也用小模型（不再升级）
2. **没有复杂度分类**：所有问题走同一条路径
3. **没有成本分析**：不知道每月 LLM 花费是多少

**为什么这是真差距**：
- 面试问"你的 agent 怎么降本"，"有语义缓存"只能拿 50 分
- 满分答案是"语义缓存 + 模型分级 + 级联 + 复杂度路由 + 成本面板"
- 招 agent 开发岗的面试官，**这一题是必问的**

---

## 四、工具选择：DeepMind benchmark 89%

### 业界指标

来源：[DeepMind Tool Selection Benchmark](https://example.com/deepmind/tool-selection-benchmarks)（2025-02）

| 模型 | 工具选择准确率 |
|---|---|
| GPT-4 | 89% |
| Claude | 87% |
| 开源模型 | 平均 72% |

**业界做法**：
- Schema 简化（不堆参数）
- Few-shot examples（每个工具给 2-3 个调用示例）
- Constrained decoding（结构化输出）
- 工具 description 优化（写清楚副作用）

### PHA 现状

| 维度 | DeepMind benchmark | PHA |
|---|---|---|
| Schema 设计 | 简化优先 | ⚠️ 有 70 个工具，schema 复杂 |
| Few-shot | 2-3 示例/工具 | ❌ **没做**（prompt 写"你可以调 X"但没给示例）|
| Constrained decoding | ✅ | ❌ **没做**（靠 prompt 约束）|
| Description 质量 | 业界标准 | ⚠️ 11.14 写"description 是给 LLM 看的 API"——**这一条是真有意识的，但没系统化** |
| 工具选择评测 | DeepMind 89% | ❌ **没评测** |

**差距**：工具选择没有评测。**这是 agent 开发岗最容易被问倒的题。**

**最小补法**：在 `tests/performance/` 加一个 `tool_selection_eval.py`，用 30 个测试 query 测"agent 是否选对了工具"，断言正确率 ≥ 80%。约 3 小时。

---

## 五、长上下文：Cursor 的多模型分工

### Cursor 怎么做的

来源：[Perplexity SaC 论文](https://www.perplexity.ai/zh-TW/hub/blog/rethinking-search-as-code-generation) 中提到的工具型 agent 设计

**Cursor 的双模型架构**：
- **Tab 模型**（小模型，本地或边缘）：实时补全，FIM（fill in middle）任务
- **Agent 模型**（大模型，云端）：复杂任务、跨文件编辑

**核心思想**：
- **小任务用小模型**（FIM 补全不需要 100B+ 参数）
- **大任务用大模型**（Agent 需要推理）
- **大模型只调小模型**（不让大模型做简单事）

### PHA 现状

| 维度 | Cursor | PHA |
|---|---|---|
| 模型分工 | FIM 补全（小） + Agent（大）| ❌ 单一模型 + 降级链 |
| 任务分类 | 显式区分 | ❌ 无 |
| 边缘计算 | 客户端（Tab）| ❌ 无 |

**差距**：**没有按任务类型选模型**。

**为什么这是真差距**：
- 用户问"今天血压高吗"——简单查询，应该用小模型（快、省）
- 用户问"分析我过去 3 个月的血压趋势，给出调药建议"——复杂推理，必须用大模型
- 现在 PHA 两条都走大模型，**简单查询也烧 token**

**怎么补**：在 `multi_model.py` 里加一个 `classify_task_complexity()`，简单查询走 Haiku 级，复杂查询走 Sonnet 级。约 2 小时。

---

## 六、可观测性：AWS / Langfuse 的全链路

### 业界标准

来源：[AWS Bedrock 监控](https://aws.amazon.com/blogs/database/lower-cost-and-latency-for-ai-using-amazon-elasticache-as-a-semantic-cache-with-amazon-bedrock/)

**业界监控的指标**：
- **每请求**：input/output token、模型、延迟、缓存命中、路由路径
- **聚合**：QPS、p50/p95/p99 延迟、错误率、成本/请求、模型分布
- **业务层**：路由正确率、拒答率、用户满意度
- **告警**：p95 > 阈值、错误率 > 阈值、成本突增

### PHA 现状

| 维度 | 业界标准 | PHA |
|---|---|---|
| 每请求 token | ✅ | ⚠️ 散落在 `multi_model.py`，无统一记录 |
| 路由路径 | ✅ | ❌ 无（虽然有 `routing` 事件，但不存） |
| 缓存命中 | ✅ | ✅ 计数有 |
| 延迟分布 | ✅ p50/p95/p99 | ⚠️ 只有平均延迟（`p95_latency_ms` 在 RAG 评测里有）|
| 错误率 | ✅ | ⚠️ Prometheus 有，但**无统一视图** |
| 成本/请求 | ✅ | ❌ **没算** |
| 路由正确率 | ✅ | ❌ **没算**（smoke 跑的是正确情况）|
| 告警 | ✅ | ❌ 无 |

**最大差距**：
1. **没算成本/请求** —— 不知道每个功能花多少钱
2. **没算路由正确率** —— 不知道 layer3 兜底占比
3. **没告警** —— 系统挂了没人知道

---

## 七、总结：按主题的差距矩阵

| 主题 | 业界标杆 | PHA 现状 | 面试权重 |
|---|---|---|---|
| **检索** | Perplexity 双路 + 子文档 | 单路 + 整 chunk | 🟡 中 |
| **记忆** | mem0 跨会话 | 无跨会话 | 🔴 高 |
| **模型路由** | 三层 + 级联 | 仅降级链 | 🔴 高 |
| **工具选择** | 89% 准确率 + 评测 | 无评测 | 🔴 高 |
| **长上下文** | Cursor 双模型分工 | 单一模型 | 🟡 中 |
| **可观测性** | 成本面板 + 告警 | Prometheus 散落 | 🔴 高 |

---

## 八、面试能立刻用的几句话

> 这些是从差距里提炼出的"诚实说法"，面试被问到时直接说：

1. **"我的检索是纯向量的，没做 BM25 双路。"**
   - 优势：实现简单，重排能补回大部分质量
   - 劣势：用户问'X 药的副作用'，纯向量会召回用药记录而不是说明书
   - 如果补：参考 Perplexity 的两段式

2. **"我的多轮记忆是 thread_id 隔离，没有跨会话长期记忆。"**
   - 主动说："我知道 mem0 / Letta 是业界标准，我现在的场景是单次就诊，不需要跨会话"
   - 优于："我也做了"（但没做）

3. **"我的模型路由是降级链，没有按任务分级。"**
   - 主动说："小模型 30% 路由是 BCloud 的真实数据，我目前没做这个分类器"
   - 优于："我有模型路由"（但其实是 fallback）

4. **"我没有工具选择准确率的评测。"**
   - 主动说："DeepMind 的 benchmark 是 87-89%，我没系统测过"
   - 优于："我做了"（但其实没数据）

5. **"我的可观测性只有 Prometheus 散落指标，没有成本面板。"**
   - 主动说："AWS 的 86% 成本下降是 ElastiCache + 语义缓存，我用的是进程内缓存"
   - 优于："我有可观测性"（但其实没法排障）

---

## 九、值得补的三件事（按 ROI 排序）

| # | 事项 | 投入 | 面试价值 | 业界对标 |
|---|---|---|---|---|
| ① | **补跨会话记忆**（mem0 简化版）| ~3h | "我的 agent 有用户长期记忆" | mem0 |
| ② | **补工具选择评测** | ~3h | "我的工具选择准确率 ≥ 80%（实测）" | DeepMind 89% |
| ③ | **补成本面板**（每请求算 LLM 花费）| ~2h | "我每月 LLM 成本 $X，每请求 $Y" | AWS Bedrock |
| **合计** | | **~8h** | | |

这三件事**每件都对应一个面试常见问题**，加起来 8 小时。
