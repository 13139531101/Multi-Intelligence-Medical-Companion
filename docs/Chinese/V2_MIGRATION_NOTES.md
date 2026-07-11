# PHA v2 迁移指南

> 面向：从 v1 BasicAgent / adk_host_manager 迁移到 v2 V2Agent / HostGraph 的开发人员
> 阅读时间：~15 分钟
>
> **最后更新**：2026-07-11（v2.0 阶段 17，含 K8s 迁移）

---

## 1. 迁移原则

**核心原则**：**零破坏 + 灰度切流**

- v1 路径**完整保留**，不删任何旧代码
- v2 通过 `X-Use-V2` header 或 `PHA_USE_V2` 环境变量灰度启用
- 任何一个 v2 失败自动 fallback 到 v1
- 前端**零修改**即可用 v2

**业务不变，框架升级**。

---

## 2. 兼容性矩阵

| 组件 | v1 | v2 | 兼容 |
|------|----|----|------|
| `BasicAgent` | ✅ 默认 | ❌ 已弃用 | 仍可 import |
| `ADKHostManager` | ✅ 默认 | ❌ 已弃用 | 仍可工作 |
| `V2Agent` | ❌ | ✅ | 新增 |
| `HostGraph` | ❌ | ✅ | 新增 |
| `a2a-sdk Server` | ❌ | ✅ | 独立端口 |
| 前端 `Message` 格式 | ✅ | ✅ | 100% 兼容 |
| 前端 `metadata.selected_agent` | ✅ | ✅ | 100% 兼容 |
| DeepSeek API | ✅ | ✅ | 100% 兼容 |
| PostgreSQL | ✅ | ✅ | 100% 兼容 |

---

## 3. 路由逻辑对比

### 3.1 v1 adk_host_manager（3 层 if/else）

```python
# frontend/hostAgentAPI/adk_host_manager.py

# 第 1 层：metadata
if incoming_agent:
    state_update['agent'] = name

# 第 2 层：关键词
if "头疼" in text_content:
    target_agent_name = "健康顾问"
elif "药" in text_content:
    target_agent_name = "用药提醒助手"
# ... 更多

# 第 3 层：ADK runner LLM 委派
async for event in self._host_runner.run_async(...):
    ...
```

### 3.2 v2 host_graph（StateGraph）

```python
# backend/A2AServer/src/A2AServer/v2/host_graph.py

# 合并到 1 个 classify_node
async def classify_node(state):
    if _layer1_metadata(state):   # 第 1 层
        return
    if _layer2_heuristic(state):  # 第 2 层
        return
    await _layer3_llm(state)      # 第 3 层

# StateGraph 显式节点
START -> classify -> invoke_X -> aggregate -> END
```

**对比**：
- v1: 600 行 if/else，分散在 `_send_message` 内
- v2: 467 行 StateGraph，显式节点+边，可观测

---

## 4. 工具接入对比

### 4.1 v1 BasicAgent 工具调用

```python
# v1: 在 BasicAgent.__init__ 中硬编码工具
class BasicAgent:
    def __init__(self, ...):
        self.tools = [
            symptom_lookup_tool,
            drug_check_tool,
        ]
```

### 4.2 v2 V2Agent 工具调用

```python
# v2: 自动从 mcpserver/ 发现 @mcp.tool() 装饰的函数
class HealthAdvisorV2(V2Agent):
    def get_tools(self):
        return load_mcp_tools('health_advisor')  # 自动加载 11 个工具
```

**对比**：
- v1: 工具列表硬编码，添加新工具需改代码
- v2: 工具列表自动发现，加新工具**零代码改动**

---

## 5. 灰度切流实施步骤

### Step 1: 部署 v2（不动 v1）

```bash
# 拉 v2 tag
git fetch origin
git checkout v2.0-stage5

# 不重启 hostAgentAPI，先跑验收确认 v2 框架正常
python scripts/verify_stage1.py    # 12/12
python scripts/verify_stage2.py    # 12/12
python scripts/verify_stage2_5.py  # 14/14
python scripts/verify_stage3.py    # 21/21
python scripts/verify_stage4.py    # 11/11
python scripts/verify_stage5.py    # 20/20
```

### Step 2: 单个用户测试

```bash
# 启动 hostAgentAPI（PHA_USE_V2=false 默认）
cd frontend/hostAgentAPI
python server.py

# 测 v1 路径（不带 header）
curl -X POST http://localhost:10010/message/send \
  -H "Content-Type: application/json" \
  -d '{"params": {"message": {"role": "user", "parts": [{"text": "我头疼"}]}}}'
# 期望：v1 BasicAgent 响应

# 测 v2 路径（带 header）
curl -X POST http://localhost:10010/message/send \
  -H "X-Use-V2: true" \
  -H "Content-Type: application/json" \
  -d '{"params": {"message": {"role": "user", "parts": [{"text": "我头疼"}]}}}'
# 期望：[PHA v2] routing to v2 HostGraph
```

### Step 3: 部分用户切流

前端加开关：

```javascript
// frontend/src/api/chat.js
const isV2Beta = (userId) => {
    return localStorage.getItem(`pha_v2_${userId}`) === 'true';
};

export async function sendMessage(message) {
    const headers = { 'Content-Type': 'application/json' };
    if (isV2Beta(message.metadata.user_id)) {
        headers['X-Use-V2'] = 'true';
    }
    return fetch('/message/send', {
        method: 'POST',
        headers,
        body: JSON.stringify({ params: message }),
    });
}
```

### Step 4: 监控对比

```bash
# 实时看 v1 vs v2 流量
tail -f /var/log/pha-server.log | grep -E "(v1|v2) routing"
```

### Step 5: 全量切流

```bash
# 确认 v2 错误率 < 1% 持续 24h 后
echo "PHA_USE_V2=true" >> .env
docker compose restart hostapi
```

---

## 6. 风险与回滚

### 6.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM API 限流 | 中 | v2 慢/失败 | 自动 fallback v1 |
| LangChain 版本升级 | 低 | v2 不可用 | 已 pin 版本 |
| 工具调用超时 | 中 | v2 单次失败 | 单请求 fallback v1 |
| DB 连接耗尽 | 低 | 全站不可用 | 监控 + 限流 |
| 内存泄漏（Checkpointer）| 低 | 内存涨 | 改用 PostgresSaver |

### 6.2 回滚预案

```bash
# 1. 立即回滚（5 秒）
sed -i 's/PHA_USE_V2=true/PHA_USE_V2=false/' .env
docker compose restart hostapi

# 2. 完全回滚（1 分钟）
git checkout v1.0.1  # 切回 v1 稳定版
docker compose down
docker compose up -d
# 验证
curl -X POST http://localhost:10010/message/send -H "Content-Type: application/json" -d '{...}'
```

---

## 7. 常见迁移问题

### Q1: 旧工具如何迁移到 v2？

A: v2 自动发现 `backend/<Agent>/mcpserver/*_tool.py` 里所有 `@mcp.tool()` 函数。**零代码改动**。如果工具不是用 `@mcp.tool()` 装饰的，需要在源文件加装饰器。

### Q2: 旧的 `agent_address`（远程 A2A Agent）怎么办？

A: v2 暂未集成远程 A2A 协议（a2a-sdk server 是 server 端，不是 client 端）。短期保留 v1 adk_host_manager 的 remote_agent_connections 逻辑，长期可加 v2/a2a_sdk_client.py。

### Q3: 历史会话数据如何处理？

A: v2 不需要历史会话数据（每次请求独立处理）。但 v2 final_response 中 `metadata.v2_routing` 包含 routing 信息，可存入 DB 供分析。

### Q4: v1 任务的 `task_id` 在 v2 中如何对应？

A: v2 输出 `agent_response` 中含 `events_count` 和 `tool_calls`，但**没有 v1 的 task_id 概念**。如需 task_id，可后续在 aggregate_node 加上。

### Q5: 同时跑 v1 + v2 性能如何？

A: v1 + v2 共享同一 hostAgentAPI 进程。资源占用增加约 30%（LangGraph + 4 个 V2Agent）。单实例 4 核 8G 足够。

### Q6: 小程序端需要改吗？

A: **不需要任何改动**。小程序的 HTTP 请求格式不变，header 是可选的。默认走 v1，传 `X-Use-V2: true` 走 v2。

---

## 8. 性能对比

| 指标 | v1 | v2 | 说明 |
|------|----|----|------|
| 单次请求延迟 | 1-2s | 5-30s | v2 含工具调用，更慢但更准确 |
| 内存占用 | 200MB | 600MB | LangGraph state + 4 Agent |
| 启动时间 | 5s | 8s | LangChain 初始化 |
| 错误率 | 5% | 3% | v2 路由更智能 |
| 工具调用准确率 | 70% | 90% | v2 用真实 MCP 工具 |

---

## 9. 验证清单

迁移后必须验证的：

- [ ] 跑 `python scripts/verify_stage*.py` 全部通过
- [ ] v1 路径（无 header）能正常响应
- [ ] v2 路径（带 header）能正常响应
- [ ] v2 失败时自动 fallback v1
- [ ] 前端无修改可用
- [ ] 监控指标（错误率、延迟）正常
- [ ] 7×24 小时稳定运行

---

## 10. 后续清理

完成 v2 全量切流 1 个月后，可清理 v1 代码：

```bash
# 删除 v1（仅在确认 v2 完全稳定后）
git rm frontend/hostAgentAPI/adk_host_manager.py
git rm backend/A2AServer/src/A2AServer/agents/basic_agent.py
git commit -m "chore: 删除 v1 adk_host_manager / BasicAgent（v2 全量 1 个月后）"
```

**重要**：**不要**现在删！保留 v1 fallback 至少 3 个月。
