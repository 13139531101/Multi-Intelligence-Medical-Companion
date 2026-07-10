# 阶段10 报告 - 并发工具调用集成（LangChain API 限制）

> **状态**：模块实现完成，集成尝试失败，已回退
> **教训**：LangChain 1.0 `create_agent()` API 设计问题

---

## 1. 阶段10 目标

把阶段11 实现的 `concurrent_tools.py` 集成到 `v2_agent.py`，让所有 V2Agent 默认启用并发工具调用。

## 2. 实现尝试

### 2.1 设计方案

通过 LangGraph 1.0 `ToolNode.awrap_tool_call` 钩子替换默认串行执行：

```python
async def awrap_tool_call(request):
    # request.tool_calls 包含 LLM 输出的多个 tool_calls
    # 用 asyncio.gather 并发执行
    results = await asyncio.gather(*[request.execute(tc) for tc in request.tool_calls])
    return results
```

### 2.2 集成代码

在 `v2_agent.py` 的 `_concurrent_kwargs()` 返回 `{"awrap_tool_call": wrap_tool_call_with_concurrent()}`，传给 `create_agent()`。

### 2.3 ❌ 失败

```
TypeError: create_agent() got an unexpected keyword argument 'awrap_tool_call'
```

**原因**：LangChain 1.0 的 `create_agent()` **不直接接受 `awrap_tool_call` 参数**。这个参数是 `ToolNode` 构造函数的，但 `create_agent()` **没有暴露替换默认 ToolNode 的入口**。

## 3. 验收成果

虽然不能集成到 v2_agent.py，**模块本身完美工作**：

```
[2] execute_tool_calls_concurrent 单元测试
  串行 3 个: 0.30s
  并发 3 个: 0.10s
  提速: 66.6%
[OK] 12/12 验收通过
```

**实测加速 66.6%**（3 个 0.1s 工具串行 0.30s → 并发 0.10s）。

## 4. 应对策略

### 4.1 短期：保持模块独立（已实施）

- `concurrent_tools.py` 保留为**用户可调用的工具**
- `v2_agent.py` 默认不启用（避免 LangChain API 错误）
- 未来 LangChain 升级暴露 ToolNode 替换时，可一键启用

### 4.2 中期：fork LangGraph

如果业务急需，可以 fork `langgraph-prebuilt` 的 ToolNode 替换 awrap_tool_call，但**风险高**（每次升级 LangChain 要重 fork）。

### 4.3 长期：等 LangChain 升级

LangChain 1.x 主线尚未稳定。社区有 [issue](https://github.com/langchain-ai/langgraph/issues) 跟踪 `create_agent` 暴露 ToolNode 替换。

## 5. 单元测试可用

`concurrent_tools.execute_tool_calls_concurrent()` 是**纯函数**，可被用户代码直接调用：

```python
from A2AServer.v2.concurrent_tools import execute_tool_calls_concurrent

# 用户代码
results = await execute_tool_calls_concurrent(
    [{"name": "tool1", "args": {...}}, {"name": "tool2", "args": {...}}],
    my_executor,
    max_concurrency=5,
)
```

## 6. 提交记录

- **新增**：[v2/concurrent_tools.py](file:///i:/A2A/3/A2AServer/backend/A2AServer/src/A2AServer/v2/concurrent_tools.py) - 增强版（保留原 `execute_tool_calls_concurrent` + 新增 `wrap_tool_call_with_concurrent`）
- **新增**：[scripts/verify_stage10.py](file:///i:/A2A/3/A2AServer/scripts/verify_stage10.py) - 12/12 通过
- **回退**：[v2/v2_agent.py](file:///i:/A2A/3/A2AServer/backend/A2AServer/src/A2AServer/v2/v2_agent.py) - 不传 `awrap_tool_call`（LangChain API 限制）

## 7. 教训

> **遇到 API 限制时**：保留模块、记录设计思路、回退到稳定状态、**等上游升级**。**不要 hack**（fork 框架源码）—— 长期维护成本高。

---

## 8. 累计 11 阶段状态

| 阶段 | 内容 | 状态 | 节省 |
|------|------|------|------|
| 7 | 工具调用缓存 | ✅ 已部署 | -96.7% 重复 |
| 8 | V2Agent 类单例 | ✅ 已部署 | -3s 每请求 |
| 9 | 写操作白名单 | ✅ 已部署 | 安全性 |
| 10 | Embedding 预热 | ✅ 已部署 | -3s 首次 |
| 11 | 并发工具调用 | ⚠️ 模块就绪 | -66.6%（待 LangChain 升级）|
