# 阶段2 推进记录

> 启动时间：2026-03
> 目标：替换子 Agent 入口为 LangChain 1.0 `create_agent`
> 状态：✅ **全部 12/12 验收通过**

## 交付物

| 文件 | 作用 |
|------|------|
| [v2/__init__.py](../../backend/A2AServer/src/A2AServer/v2/__init__.py) | v2 包入口 |
| [v2/v2_runtime.py](../../backend/A2AServer/src/A2AServer/v2/v2_runtime.py) | v2 运行时（单例 + Middleware + Checkpointer）|
| [v2/v2_agent.py](../../backend/A2AServer/src/A2AServer/v2/v2_agent.py) | v2 智能体基类 `V2Agent` |
| [v2/sub_agents.py](../../backend/A2AServer/src/A2AServer/v2/sub_agents.py) | 4 个子 Agent 的 v2 入口（HealthAdvisor / HealthRecords / MedicationReminder / VisitSummary）|
| [v2/mcp_tool_adapter.py](../../backend/A2AServer/src/A2AServer/v2/mcp_tool_adapter.py) | MCP 工具 → LangChain BaseTool 适配器 |
| [scripts/verify_stage2.py](../../scripts/verify_stage2.py) | 阶段2 验收脚本 |

## 关键设计

### 1. v2/v2_runtime.py：单例运行时
- `V2AgentRuntime`：统一封装 LangChain 1.0 + Checkpointer + Middleware
- **降级机制**：LangChain 1.x 不可用时不阻塞，标记 `available=False`
- **Checkpointer**：自动从 `PHA_CHECKPOINT_DB_URL` 选 Postgres，否则用 `InMemorySaver`

### 2. v2/v2_agent.py：智能体基类
- 继承 `V2Agent` 即可获得 v2 全部能力
- `stream()` 事件格式与 `BasicAgent.stream()` **完全一致**（兼容 A2A 协议）
- 失败自动降级到 error 事件，不抛异常

### 3. v2/sub_agents.py：4 个子 Agent
- 加载项目原有 prompt（`memory_enhanced_agent_prompt.md`）
- 工具列表通过 `load_mcp_tools(agent_name)` 动态加载
- **零业务代码修改**：原有 `BasicAgent` 仍可工作

### 4. v2/mcp_tool_adapter.py：工具适配器
- 阶段2-4 用占位 stub（每个 agent 1-2 个 mock 工具）
- 阶段2-5 替换为真实 MCP 工具（自动扫描 `mcpserver/*_tool.py`）
- Pydantic v2 兼容（用 `Field` 定义 `name/description`）

## 验收结果

```
[1] v2 运行时                              OK
[2] v2 智能体基类                          OK
[3] 4 个子 Agent 入口                       OK × 4
[4] MCP 工具适配器                          OK × 4
[5] 与 BasicAgent 兼容性（v1 不破坏）       OK
================================
阶段2 验收：12/12 通过
```

## 兼容性保证

- ✅ **零业务破坏**：原有 `BasicAgent.stream()` 仍可工作
- ✅ **零依赖强制升级**：LangChain 1.x 不可用时自动降级
- ✅ **A2A 协议兼容**：输出事件格式与 v1 完全一致
- ✅ **向后兼容**：stage1 的 `observability.py` 仍可被 v2 runtime 调用

## 下一步（阶段3）

- [ ] HostAgent 用 LangGraph `StateGraph` 替换 `adk_host_manager.py` 的 3 层 if/else
- [ ] 加 Checkpointer（先 InMemory，再换 PostgresSaver）
- [ ] 加 Middleware（PII 脱敏、Summary、Human-in-the-loop）
- [ ] 老的 `adk_host_manager.py` 保留为 v1 路由，新请求走 v2
