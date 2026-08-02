# PHA 智能体优化计划 2026

> **目标**：让 PHA 智能体效果更好、用户使用更舒服
>
> **更新**：2026-08-02 — Agentic RAG Stage 1 完成
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
| **Stage 2** | 多跳检索：复杂问题跨档案/跨时间推理 |
| **Stage 3** | 知识图谱增强：把档案里的实体关系抽出来 |

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
├── PHASE 1: HITL + 主动询问澄清  ←── 最快出效果
├── PHASE 2: Agentic RAG (Stage 1)  ←── 核心能力提升 ✅ 已完成
└── PHASE 3: ReAct 反思模式

2026-Q4 (10-12月)
├── PHASE 4: Agentic RAG (Stage 2-3 多跳+知识图谱)
├── PHASE 5: 动态工具选择
├── PHASE 6: 语义缓存优化
└── PHASE 7: 推理过程可视化

2027-Q1 (如果需要)
└── PHASE 8: vLLM 部署 + PhaCore 重构收尾
```

---

## 十一、快速见效清单（按投入/收益排序）

| 优先级 | 优化项 | 预估工时 | 预估收益 |
|--------|--------|----------|----------|
| 1 | 🟢 HITL 确认机制 | 2-3天 | 防止误操作，用户信任+ |
| 2 | 🟢 主动询问澄清 | 1-2天 | 减少乱答，提升满意度 ✅ 已实现 |
| 3 | 🟢 Agentic RAG Stage 1 | 3-5天 | 检索准确率大幅提升 ✅ 已实现 |
| 4 | 🟡 语义缓存 | 2-3天 | 响应延迟↓40%+ |
| 5 | 🟡 ReAct 反思 | 2-3天 | 错误率↓60% |
| 6 | 🟢 推理过程可视化 | 2-3天 | 用户信任度显著提升 |
| 7 | 🟡 动态工具选择 | 2-3天 | Token 消耗↓30-50% |

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
