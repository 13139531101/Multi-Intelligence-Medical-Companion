# PHA 智能体优化计划 2026

> **目标**：让 PHA 智能体效果更好、用户使用更舒服
>
> **更新**：2026-08-04 — HITL前端确认弹窗开发中，主动询问澄清 + Magentic RAG Stage 1 已完成
>
> **优先级说明**：🔴 高投入/高回报 | 🟡 中 | 🟢 低投入/高回报

---

## 一、Human-in-the-Loop (HITL) 🔴 高优先级

### 1.1 目标
防止智能体执行高危操作（删除、发送）时出错，给用户确认机会，提升信任度。

### 1.2 实现方案

LangGraph 的 `interrupt()` 机制：

```python
from langgraph.types import interrupt, Command

# 在危险操作节点中断，等用户确认
def delete_record_node(state):
    if state["action"] == "delete":
        # 中断，等待用户确认
        interrupt("等待用户确认删除操作")
    # ... 执行删除
```

### 1.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 用户信任 | ❌ 无确认 | ✅ 删除/发送前确认 |
| 实现成本 | - | 🟡 2-3天 |
| 代码改动 | - | `v2/host_graph.py` + 前端确认弹窗 |

### 1.4 实现状态
- ✅ `dangerous_tools.py` — 硬编码危险工具列表已识别
- ✅ 前端确认弹窗 — **已实现** (2026-08-04)
  - AgentQuickFab 新增 HITL Dialog（approve/reject）
  - `/v2/chat/resume` 接口对接完成
  - interrupt 事件自动触发弹窗

### 1.4 入口点（已识别）
- `dangerous_tools.py` — 硬编码危险工具列表
- 需对接前端的 `DomainSwitcher` / 确认弹窗

---

## 二、Agentic RAG 🟢 最高优先级

### 2.1 目标
让健康档案检索更准确，不只是"匹配关键词"，而是理解语义+多跳推理。

### 2.2 实现方案

```
用户问题 → LLM判断需要检索 → 检索引擎 → 评估相关性 → 如不相关则重新检索 → 生成答案
                    ↑                    ↓
                    ←←←←←←←←←←←←←←←←←
```

**三阶段**：

| 阶段 | 内容 |
|------|------|
| **Stage 1** | Self-RAG 风格的"检索评估"，判断检索结果是否有用 | ✅ **已实现** (2026-08-02) |
| **Stage 2** | 多跳检索：复杂问题跨档案/跨时间推理 | ✅ **已实现** (2026-08-08) + Bugfix (2026-08-10) |
| **Stage 3** | 知识图谱增强：实体关系抽取 + 图扩展检索 | ✅ **已实现** (2026-08-10) |

### 2.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 检索准确率 | ~60% | 🔴 85%+ |
| 实现成本 | - | 🟡 3-5天 |
| 代码改动 | - | `backend/A2AServer/src/A2AServer/v2/` 新增 RAG 模块 |

### 2.4 关键参考
- [Agentic RAG: 用LangGraph打造会自动修正检索错误的 RAG 系统](https://new.qq.com/rain/a/20260106A07DC700)
- [2026年这7种用于构建Agentic RAG系统的架构](https://blog.csdn.net/Python_cocola/article/details/145283886)

---

## 三、ReAct 反思模式 🟡 中优先级

### 3.1 目标
让智能体"输出后想一想"，自我审视结果是否合理，必要时重新调用工具或修正。

### 3.2 实现方案

```python
# 反思节点
def reflect_node(state):
    response = state["response"]
    # LLM 审视：回答是否完整？工具调用是否正确？
    critique = llm.invoke(f"审视以下回答是否合理: {response}")
    if critique.needs_retry:
        return {"needs_retry": True, "critique": critique}
    return {"response": response}
```

### 3.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 错误率 | 假设 15% | 🟡 5% 以下 |
| 实现成本 | - | 🟡 2-3天 |
| Token 消耗 | - | ↑ 20-30%（多一步反思） |

---

## 四、记忆系统优化 🟢 高优先级

### 4.1 目标
现有 L1/L2/L3 记忆分层已实现，但访问策略不够智能。

### 4.2 实现方案

| 层级 | 现状 | 优化后 |
|------|------|--------|
| **L1 工作记忆** | 最近 5 轮对话 | 🔴 按 token 预算动态调整 |
| **L2 短期记忆** | 当天会话 | 🟡 按用户活跃度延长/缩短 |
| **L3 长期记忆** | PostgreSQL 向量 | 🟢 **语义缓存**：同类问题直接复用 |

**语义缓存核心逻辑**：
```python
# 同类问题 → 检查缓存 → 命中则直接返回
query_embedding = embed(user_query)
cached = vector_db.similarity_search(query_embedding, threshold=0.95)
if cached:
    return cached.result  # 跳过 LLM 推理
```

### 4.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 响应延迟 | 假设 5-10s | 🟢 1-2s（缓存命中时） |
| Token 消耗 | - | ↓ 40%+（缓存命中时） |

### 4.4 关键参考
- [2026年Agent效率优化技术全景总结:从记忆、工具到规划的三大核心组件](https://blog.csdn.net/CSDN_430422/article/details/157477278)
- [Agentic Memory管理高级技巧](https://blog.csdn.net/lxcxjxhx/article/details/159918540)

---

## 五、动态工具选择 🟡 中优先级

### 5.1 目标
不让所有工具都传给 LLM，只选最相关的，减少 token 消耗，提高准确率。

### 5.2 实现方案

```python
# 当前：所有工具一股脑传给 LLM
tools = load_all_mcp_tools()  # 假设 50 个

# 优化后：先用轻量模型/关键词筛选
relevant_tools = tool_selector.select(
    query=user_query,
    tools=tools,
    top_k=5  # 只选最相关的 5 个
)
```

### 5.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| Token 消耗 | 全量工具 | 🟢 ↓ 30-50% |
| LLM 决策质量 | 噪声多 | 🟢 提升 |
| 实现成本 | - | 🟡 2-3天 |

---

## 六、主动询问澄清 🟡 中优先级

### 6.1 目标
智能体不确定时不乱猜，主动反问用户获取澄清。

### 6.2 实现方案

```python
def clarify_node(state):
    confidence = state.get("confidence", 1.0)
    if confidence < 0.7:
        return Command(
            goto="ask clarification",
            update={"pending_question": "您是指...？"}
        )
```

### 6.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 用户体验 | 可能乱答 | 🟢 体验流畅、信任提升 |
| 实现成本 | - | 🟢 1-2天（判断逻辑） |

### 6.4 实现状态
- ✅ **已完成** — 提交 `132d6e3` (stage48-29)
- Agent 不确定时通过 `event: clarification` 反问用户
- 前端 AgentQuickFab 已处理 `clarification` 事件

---

## 七、推理过程可视化 🟢 用户体验优先

### 7.1 目标
让用户看到智能体在"思考什么"，增加透明度和信任。

### 7.2 实现方案

- 前端显示 Agent 思考过程（类似 GPT-4 的思考链）
- 实时展示：正在调用哪个工具 → 工具返回什么 → 下一步打算做什么

### 7.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 用户信任度 | 看不到过程 | 🟢 显著提升 |
| 实现成本 | - | 🟡 2-3天（前端流式展示） |

---

## 八、推理加速 ⚙️ 基础设施

### 8.1 目标
降低延迟，提升用户体验。

### 8.2 方案对比

| 框架 | 优势 | 劣势 | 推荐度 |
|------|------|------|--------|
| **vLLM** | PagedAttention、灵活调度 | NVIDIA only | 🟢 首选 |
| **TensorRT-LLM** | 内核级优化、性能最强 | 绑定 NVIDIA、生态封闭 | 🟡 可选 |
| **llama.cpp** | 轻量、CPU 运行 | 速度较慢 | 🟢 CPU 备选 |

### 8.3 影响分析

| 维度 | 现状 | 目标 |
|------|------|------|
| 推理延迟 | 假设 3-5s/token | 🟢 0.5-1s/token（vLLM） |
| 实现成本 | - | 🔴 需要 GPU 资源 |

### 8.4 关键参考
- [2026 大模型推理框架测评:vLLM 0.5/TGI 2.0/TensorRT-LLM 1.8](https://blog.csdn.net/Y525698136/article/details/161566576)

---

## 九、PhaCore 重构 📋 代码质量

### 9.1 目标
消除 4 个 Agent 间工具重复，减少 66 → 40-45 个 `@mcp.tool()`。

### 9.2 阶段划分

| Phase | 内容 | 收益 |
|-------|------|------|
| **Phase 1** | OCR / DatabaseManager 共享 | 🔴 消除重复代码 900+ 行 |
| **Phase 2** | Reminder / Storage 共享 | 🟡 再减少 400+ 行 |
| **Phase 3** | 统一 database_config.py | 🟢 消除 5 处不一致 |

详见 [PHACORE_REFACTOR_PLAN.md](./PHACORE_REFACTOR_PLAN.md)

---

## 十、实施路线图

```
2026-Q3 (8-9月)
├── PHASE 1: HITL + 主动询问澄清  ←── 最快出效果 ✅ 已完成
├── PHASE 2: Agentic RAG (Stage 1)  ←── 核心能力提升 ✅ 已完成
├── PHASE 3: ReAct 反思模式        ←── 回答质量把关 ✅ 已完成
├── PHASE 4: Agentic RAG (Stage 2 多跳检索) ✅ 已完成
├── PHASE 5: Agentic RAG (Stage 3 知识图谱) ✅ 已完成（2026-08）
└── PHASE 5b: 动态 Skills/MCP 重构 ✅ 已完成（2026-08）

2026-Q4 (10-12月)
├── PHASE 6: 动态工具选择
├── PHASE 7: 语义缓存优化
└── PHASE 8: 推理过程可视化

2027-Q1 (如果需要)
└── PHASE 9: vLLM 部署 + PhaCore 重构收尾
```

---

## 十一、快速见效清单（按投入/收益排序）

| 优先级 | 优化项 | 预估工时 | 预估收益 |
|--------|--------|----------|----------|
| 1 | 🟢 HITL 确认机制 | 2-3天 | 防止误操作，用户信任+ |
| 2 | 🟢 主动询问澄清 | 1-2天 | 减少乱答，提升满意度 ✅ 已实现 |
| 3 | 🟢 Agentic RAG Stage 1 | 3-5天 | 检索准确率大幅提升 ✅ 已实现 |
| 4 | 🟡 语义缓存 | 2-3天 | 响应延迟↓40%+ |
| 5 | 🟡 ReAct 反思 | 2-3天 | 错误率↓60% ✅ 已实现 |
| 6 | 🟢 推理过程可视化 | 2-3天 | 用户信任度显著提升 |
| 7 | 🟡 动态工具选择 | 2-3天 | Token 消耗↓30-50% 🔜 下一步 |

---



## 十二、2026-08-02 实现记录

### Magentic RAG Stage 1 ✅

**新增文件**：
- `backend/A2AServer/src/A2AServer/v2/magnetic_rag.py` — 核心 Self-RAG 逻辑

**修改文件**：
- `backend/A2AServer/src/A2AServer/v2/host_graph.py` — rag_retrieve 节点集成
- `backend/A2AServer/src/A2AServer/v2/rag.py` — embedding API key 修复
- `frontend/multiagent_front/src/components/AgentQuickFab.jsx` — tool call chip 渲染
- `frontend/hostAgentAPI/Dockerfile` — 添加 PhaCore 支持
- `docker-compose.yml` — healthcheck 修复

**修复的 Bug**：
1. `rag_path_map` 错误映射（agent name vs node name）
2. `checkpointer` 编译顺序错误
3. embedding API key 配置支持百炼 MAAS (1024维)

**AI浮窗 tool call 显示**：
- AgentQuickFab 新增 `event: tool_call` 和 `event: tool_result` 事件处理
- tool call 以 chip 标签显示在回答上方

**Embedding 配置（百炼 MAAS）**：
- `EMBEDDING_API_BASE=https://llm-hq1pqpf6htncxt7n.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
- `EMBEDDING_MODEL=text-embedding-v4`
- `EMBEDDING_DIM=1024`（百炼要求 64-3072）
- `EMBEDDING_API_KEY=sk-ws-...`（百炼 ws- 前缀 key）


---
## 十三、2026-08-08 实现记录

### Magentic RAG Stage 2 — 多跳检索 ✅

**多跳流程**：
```
detect_record_types()       → LLM 识别 query 涉及哪些档案类型
        ↓
Hop1: retrieve_chunks_by_type() 并行检索每种类型
        ↓
Hop2: 跨类型增强检索 — 用其他类型结果补充每个子 query 再检索
        ↓
merge: 合并所有 chunks，去重，按 score 排序
        ↓
evaluate_chunks() — LLM 评估最终结果
```

**核心文件**：
- `backend/A2AServer/src/A2AServer/v2/magnetic_rag.py`
  - `detect_record_types()` — LLM 判断档案类型（blood_pressure / medication / lab_result 等）
  - `multi_hop_rag_search()` — 多跳主入口
  - `_chunks_to_text()` — chunks 转摘要文本，拼入下一跳 query
  - `retrieve_chunks_by_type()` — 按 source_type 过滤检索

**效果**：
- 优于单跳：跨档案关联分析（如"吃药和血压的关联"需要同时检索 medication + blood_pressure）
- 默认启用，search() 直接走多跳

**改动**：
- `magnetic_rag.py` 新增 ~200 行
- `host_graph.py` rag_retrieve_node import 路径改为 `from .magnetic_rag import search`

**Bugfix 2026-08-10**：Stage 2 多跳检索因 RECORD_TYPES 枚举值（`blood_pressure`/`medication`）与 `rag_chunks.record_type` 真实值（`vital_signs`/`prescription`）不一致，`retrieve_chunks_by_type()` 永远返回空列表。
- 修复：新增 `RECORD_TYPE_TO_DB_TYPE` 映射表，`retrieve_chunks_by_type()` 改用 `record_type` 列过滤
- 修复：嫁接 Stage 1 rewrite-retry 逻辑到 Stage 2（之前是死代码）

---
## 十四、2026-08-10 实现记录

### Agentic RAG Stage 3 — 知识图谱 ✅

**目标**：从档案中抽取实体关系，图扩展弥补向量相似不足。

**新增文件**：`backend/A2AServer/src/A2AServer/v2/knowledge_graph.py`

**3 张 KG 表（幂等 `CREATE TABLE IF NOT EXISTS`）**：
- `kg_entities` — 实体节点（symptom/medication/disease/allergy/vital_sign）
- `kg_relations` — 关系边（TREATS/CAUSES/MEASURES/CO_OCCURS/PRECEDES/FOLLOWS）
- `kg_entity_chunks` — 实体↔chunk 关联表

**核心流程**：
```
索引时：chunk 文本 → extract_entities_and_relations() → kg 表
检索时：query → LLM 抽取实体 → graph_expand_entities(1-2跳) → kg_entity_chunks → 关联 chunks
```

**magnetic_rag.py 集成**：Step 5.5 在 merge 后追加 KG 图扩展补充的 chunks，解决"向量检索文本相似但非相关"的问题。

**验证结果**（"血压高头晕吃什么药"）：
- ✅ LLM 正确抽取 4 个实体（氨氯地平/高血压/血压/头晕）
- ✅ 识别出 CO_OCCURS 共现关系
- ✅ kg_entities / kg_relations 建表成功

---
## 十二、2026-08-09 实现记录

### ReAct 反思模式 ✅

**目标**：Agent 生成回答后，独立 critique 节点审视质量，必要时自动修订。

**流程**：
```
invoke_agent → critique_node → (revision) → aggregate
                              ↓
                    5 维度审核：
                    1. 准确性（诊断/建议是否有依据）
                    2. 完整性（是否覆盖所有子问题）
                    3. 安全性（用药禁忌、剂量说明、"请咨询医生"）
                    4. 可操作性（建议是否具体可执行）
                    5. 透明度（不确定性是否主动说明）
```

**新增文件**：
- `backend/A2AServer/src/A2AServer/v2/react_critique.py`
  - `CritiqueResult` 数据类
  - `critique_node` — 独立审核节点（LangGraph 图节点）
  - `critique_response()` — 独立便捷函数
  - `CRITIQUE_PROMPT` / `REVISION_PROMPT` — **LCEL ChatPromptTemplate**（不再字符串拼接）

**关键改进 — Modern Prompt Injection**：
- 模板字符串通过 `.format()` 注入变量，兼容 langchain 1.3.14
- `SystemMessage` + `HumanMessage` 直接构造，绕过 LCEL `invoke()` 在该版本的变量替换失效问题
- 摒弃 f-string 拼接，模板可复用、可测试、可版本化

**Skills 集成 ✅**：
- `SkillRegistry.build_skill_context()` — 选中 skill 上下文格式化
- `invoke_agent_node` 调用前注入：RAG context + Skill context + 原 query 三合一
- 支持 top_k=2 自动选择最相关 skill

**图结构变更**：
```
classify → clarify → rag_retrieve → invoke_* → critique → aggregate → END
```

**Critique 元信息**写入 `final_response.critique`：
```python
{
    "applied": bool,       # 是否触发了修订
    "is_adequate": bool,  # 是否达标
    "issues": [...],      # 发现的问题列表
    "reasoning": str,     # 审核理由
}
```

**依赖**：
- `backend/requirements.txt` 新增 `pyyaml>=6.0`

**Bugfix：LangChain 1.3.14 LCEL invoke 失效**：
- 症状：`CRITIQUE_PROMPT.invoke({"query": x})` 后，`HumanMessage.content` 仍是未替换的 `"{query}"`
- 根因：langchain 1.3.14 的 `ChatPromptTemplate.invoke()` 返回的 `PromptValue` 调用 `to_messages()` 后模板变量未替换
- 修复：改用 `SystemMessage(content=CRITIQUE_SYSTEM_PROMPT.format(...))` 直接构造，绕过 LCEL

---

## 十二、参考资源

- [LangGraph Human-in-the-Loop 官方指南](https://blog.csdn.net/zyctimes/article/details/159785786)
- [10 个让 Multi-Agent 系统更稳健的实操建议](https://new.qq.com/rain/a/20251021A050XB00)
- [2026年Agent效率优化技术全景总结](https://blog.csdn.net/CSDN_430422/article/details/157477278)
- [2026年Agentic AI十大关键趋势](https://new.qq.com/rain/a/20260105A02WC200)
- [Agentic RAG 系统架构](https://blog.csdn.net/Python_cocola/article/details/145283886)
- [LangGraph HITL 实战](https://blog.csdn.net/2502_91590613/article/details/161296278)
- [vLLM vs TensorRT-LLM 2026 测评](https://blog.csdn.net/Y525698136/article/details/161566576)

---

## 附录：当前系统关键文件

| 文件 | 作用 |
|------|------|
| `backend/A2AServer/src/A2AServer/v2/host_graph.py` | 编排入口 |
| `backend/A2AServer/src/A2AServer/v2/sub_agents.py` | 各 Agent 定义 |
| `backend/A2AServer/src/A2AServer/v2/mcp_discover.py` | MCP 工具发现 |
| `backend/A2AServer/src/A2AServer/v2/dangerous_tools.py` | 危险工具列表（HITL 入口） |
| `backend/AgentMemorySystem/` | 记忆系统 |
| `frontend/multiagent_front/` | 前端 AI 浮窗 |
