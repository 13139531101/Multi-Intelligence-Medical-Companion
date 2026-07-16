# 🎯 面试准备：PHA v2 LangGraph 阶段开发记录

> **日期**: 2026-07-15
> **目的**: 面试展示完整项目经验 + 问题解决能力
> **对应代码 commit + tag**:
> - `85d26e4` / `v2.0-stage35-miniapp-v2` (小程序 v2 接入)
> - `124ed3f` / `v2.0-stage36-asyncfix` (astream async 修复)
> - `b33cdd3` / `v2.0-stage37-sse` (SSE 流式端点)
> - `a3d72a5` / `v2.0-stage37sse-fix` (SSE 3 BUG 修复)

---

## 1. 项目背景（1 分钟电梯演讲）

**PHA (Personal Health Assistant)** — 基于 A2A / MCP / ANP 三协议的个人智能健康助手。

- **架构演进**: v1 (单体 A2A) → v2 (LangGraph 多 agent 编排 + ANP 协议)
- **4 个 sub-agent**: 健康顾问 / 健康档案 / 用药提醒 / 就诊摘要
- **后端**: FastAPI + LangGraph 1.x + DeepSeek + AsyncPostgresSaver
- **前端**: 微信小程序 + v2 模式切换 + ANP DID
- **AI 协议**: A2A (Agent-to-Agent) + MCP (Model Context Protocol) + ANP (Agent Network Protocol, 类比 HTTP for agents)

---

## 2. 阶段 35: 小程序 v2 集成 + ANP 接入

### 2.1 目标
- 小程序同时支持 v1 (A2A) + v2 (LangGraph)
- 接入 ANP 协议 (Agent Description + DID:WBA)
- 加 agent 状态监控页

### 2.2 关键决策

| 决策点 | 选 A | 选 B | 实际 |
|--------|------|------|------|
| v1/v2 切换 | 服务端 header `X-Use-V2` | 客户端 UI 切换 | **客户端 UI**（用户可见） |
| 端点路径 | `/api/v2/chat` 统一前缀 | 顶层 `/smart_chat` | **顶层**（hostapi 现状） |
| ANP AD 格式 | OpenAPI 3.0 | 自定义 JSON | **自定义**（类比 Schema.org Product） |

### 2.3 实现细节

**14 个新 API 函数**（1280 行，54 个 exports）:
- `sendMessageV2 / sendMessageV2Multi`: 调 `/smart_chat`
- `getV2AgentsStatus`: 4 个 sub-agent 状态
- `getAnpHealth / getAnpAgentDescription / getAnpAgents / callAnpRpc`
- `detectBackendVersion`: 探测 v1/v2 自动 fallback

**agent_chat.js 改动**:
```js
// 统一发送入口（v1/v2/single/multi）
async _sendWithV2(payload) {
  if (useV2) {
    if (v2ExecMode === "multi") {
      return await sendMessageV2Multi(payload);
    } else {
      return await this._sendWithV2Stream(payload, conversationId);
    }
  }
  return await sendMessage(payload);  // v1 fallback
}
```

**新页面**:
- `pages/agents_status/`: 4 个 v2 sub-agent + 4 个 ANP agent (DID) + 点击查看详情 + ANP JSON-RPC 测试

### 2.4 面试亮点

- ✅ **协议抽象层**: A2A/MCP/ANP 三协议共存
- ✅ **渐进式升级**: 客户端 UI 切换 + 自动 fallback，不破坏 v1
- ✅ **DID:WBA**: ANP 协议用 DID 标识每个 agent，类比 Web 互联网的 DNS

---

## 3. 阶段 36: astream async 修复 (踩坑分享)

### 3.1 问题
```
TypeError: 'async_generator' object is not iterable
```

### 3.2 根因
阶段30 把 `agent.stream()` 改为 `agent.astream()` 适配 `AsyncPostgresSaver`，**漏改了一处 `for` 循环**：

```python
# 之前 (错)
stream_iter = agent.astream(...)  # 返回 async_generator
for chunk in stream_iter:         # ❌ async_generator 不能用 for

# 修复 (对)
stream_iter = agent.astream(...)
async for chunk in stream_iter:   # ✅ async def 内必须用 async for
```

### 3.3 为什么阶段30 没暴露？
- `/v2/agents/status` 显示 `cache_size=0`（agent 没实例化）
- 没真调过 LLM 路由
- 阶段35 用户点开小程序 → 实际发请求 → 实例化 → 调 astream → **报错**

### 3.4 面试亮点

- ✅ **深入理解 async/await**: `async_generator` 必须在 `async def` 内用 `async for`
- ✅ **测试覆盖率思考**: 类型检查不能完全替代运行时测试
- ✅ **快速定位**: 200 行代码定位到 1 行 bug，依赖 docker logs 关键字搜索
- ✅ **LangGraph 1.0 兼容性**: `astream` + `AsyncPostgresSaver` 配合

---

## 4. 阶段 37: v2 SSE 流式端点 (架构优化)

### 4.1 背景
阶段35 修完 async 后，**前端 v2 消息 1 分钟没显示**。

### 4.2 根因（3 层 bug）

**层级 1: 架构问题**
- v2 `smart_chat` 立刻返回 routing 结果（"已将您的请求转发给..."）
- 实际 LLM 调用在 `asyncio.create_task(_v2_runner())` 后台跑
- 跑完 inject 到 v1 manager
- 前端只能**轮询** `/message/list` 拉

**层级 2: 前端轮询逻辑复杂**
- `isFinalAssistantReply` 条件判断（200 字符 / `##` / 列表 / 问号结尾）
- `pendingMsg` 过滤逻辑
- v2 注入消息格式（`source: pha-v2-host-graph`）

**层级 3: formattedMessages map 丢 metadata**
- 上一版 `formattedMessages` 没保留 `m.metadata` 字段
- `isV2Msg(m)` 永远返回 false
- v2 消息被反复过滤

### 4.3 解决：加 SSE 流式端点

**后端** `frontend/hostAgentAPI/api.py`:
```python
@app.post("/v2/chat/stream")
async def v2_chat_stream(request: Request):
    """SSE 流式：同步等 v2_process_message，按 10 字符切块推送"""
    async def event_generator():
        result = await v2_process_message(a2a_msg)
        content = result["result"]["content"]
        
        yield f"event: routing\ndata: {json.dumps(...)}\n\n"
        for i in range(0, len(content), 10):
            yield f"event: chunk\ndata: {json.dumps({'text': content[i:i+10]})}\n\n"
            await asyncio.sleep(0.02)
        yield f"event: done\ndata: {json.dumps(...)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**前端** `utils/api.js`:
```js
const sendMessageV2Stream = (message, onEvent, onError) => {
  const requestTask = wx.request({
    url: `${SERVER_URL}/v2/chat/stream`,
    method: "POST",
    data: requestBody,
    enableChunked: true,  // ← 关键：微信小程序 SSE 支持
    header: { "Content-Type": "application/json" },
  });
  
  // 解析 SSE: event: routing\ndata: {...}\n\n
  requestTask.onChunkReceived((response) => {
    const text = new TextDecoder("utf-8").decode(new Uint8Array(response.data));
    // 解析 event/data
  });
  return requestTask;
};
```

**前端** `agent_chat.js`:
```js
// 流式显示
(evt) => {
  if (evt.event === "routing") {
    this.setData({ selectedAgent: data.agent, agentRouting: data.routing });
  } else if (evt.event === "chunk") {
    // 第一个 chunk：替换 pending 消息
    // 后续 chunk：累加
  } else if (evt.event === "done") {
    // 标记 isStreaming = false
  }
}
```

### 4.4 SSE 模式的 3 个 BUG 修复

| # | BUG | 原因 | 修复 |
|---|-----|------|------|
| 1 | 空白回答框 | WXML 用 `part.content`，代码设 `part.text` | 同时设两个字段 |
| 2 | 还在轮询 | `_sendWithV2` 完后无条件 `startPolling()` | v2 模式不轮询 |
| 3 | "AI 思考中..." 卡住 | `pending_ai_xxx` 没删 | 第一个 chunk 时 filter 旧 pending |

### 4.5 效果对比

| 指标 | 之前 | 现在 |
|------|------|------|
| 响应延迟 | 30-60 秒 | **5.7 秒** |
| 显示方式 | 一次性显示完整答案 | **逐字打字机效果** |
| 轮询次数 | 15-30 次（每 2 秒） | **0 次**（SSE 一次连接） |
| 后端压力 | 高（轮询 list_messages） | **低**（单向流） |
| 用户体验 | "AI 卡住了？" | "AI 在打字！" |

### 4.6 面试亮点

- ✅ **SSE 协议设计**: event/data 格式 + 换行分隔 + keep-alive
- ✅ **小程序的 SSE 支持**: `enableChunked: true` + `onChunkReceived` + UTF-8 处理
- ✅ **从架构层面解决问题**: 不只是改 bug，而是**换架构**（轮询 → 流式）
- ✅ **用户体验视角**: 打字机效果比"卡住再显示"更好
- ✅ **DID:WBA 协议设计**: 类比 Web 的 DNS，每个 agent 有唯一标识

---

## 5. 整体技术栈

### 后端
- **Python 3.11** + **FastAPI** + **uvicorn**
- **LangGraph 1.x** (StateGraph + ToolNode + AsyncPostgresSaver)
- **LangChain 1.x** (ChatOpenAI 兼容层)
- **DeepSeek Chat** (主力 LLM)
- **PostgreSQL 16 + pgvector** (vector + state)
- **Redis 7** (cache + pubsub)
- **Docker Compose** (编排 7 个容器)

### 前端
- **微信小程序** (WeChat Mini Program)
- **JavaScript** (无 TS，原生)
- **A2A JSON-RPC 2.0** 协议
- **SSE 客户端** (`enableChunked: true`)

### AI 协议
- **A2A** (Agent-to-Agent): Google 推出的 agent 通信协议
- **MCP** (Model Context Protocol): Anthropic 推出的 tool 协议
- **ANP** (Agent Network Protocol): 我自定义的 agent 网络协议，类比 HTTP

---

## 6. 面试可能被问的问题

### Q1: 为什么选 LangGraph 而不是 LangChain Agents？
**A**: LangGraph 1.0 提供：
- 显式状态管理（`AsyncPostgresSaver` + thread_id）
- 多 agent 编排（multi-agent state graph）
- 持久化 + 错误恢复
- 比 LangChain Agents 更可控

### Q2: astream 和 stream 的区别？
**A**: 
- `stream()` 同步，`astream()` 异步
- `astream()` 才能配合 `AsyncPostgresSaver`（避免 event loop 冲突）
- `async for` 必须在 `async def` 内使用

### Q3: SSE 和 WebSocket 的区别？为啥选 SSE？
**A**:
- SSE 单向（server → client），WebSocket 双向
- 我们的场景：客户端发一次请求，服务器连续推数据
- SSE 简单，自动重连，HTTP 友好
- 微信小程序天然支持 SSE

### Q4: ANP 和 A2A 的区别？
**A**:
- A2A: 点对点 agent 通信（JSON-RPC）
- ANP: agent 网络协议，有 Agent Description + DID 标识
- 类似 HTTP vs DNS 的关系：ANP 给 A2A 提供发现能力

### Q5: 单例化为什么能加速 3 秒？
**A**:
- LangGraph agent 编译耗时 3 秒
- 状态由 thread_id 隔离，**安全共享**同一实例
- 类比数据库连接池

### Q6: 5.7 秒还是慢，怎么优化？
**A**:
- LLM 推理占 90%，模型本身慢
- 可以：模型蒸馏 / 缓存常见问答 / 用更快模型（Qwen2.5 7B）
- 架构已经最优：流式显示让用户感觉快

### Q7: 怎么保证多 agent 数据一致性？
**A**:
- LangGraph 1.x 的 `AsyncPostgresSaver` 提供 ACID 保证
- 每个 conversation_id 一个 thread
- 状态序列化到 Postgres，重启可恢复

### Q8: 这个项目最难的 bug 是什么？
**A**: 阶段 36 的 `async_generator object is not iterable`
- 难在**埋得深**：阶段 30 改的，阶段 35 才暴露
- 难在**症状误导**：以为后端没回答，实际是 streaming 失败
- 教训：单测要覆盖**实际运行路径**，不能只测 endpoint 是否返回 200

---

## 7. 演示流程（5 分钟）

1. **架构图**（30 秒）
   - 展示 `docs/Chinese/V2_ARCHITECTURE.md`
   - 4 sub-agent + 编排图

2. **跑后端**（1 分钟）
   ```bash
   docker compose up -d
   docker run -d --name hostapi a2aserver-hostapi:stage37sse ...
   curl http://localhost:13002/v2/agents/status
   ```

3. **跑小程序**（1 分钟）
   - 打开微信开发者工具
   - 显示 v2 模式切换栏
   - 发"你好" → 看流式显示
   - 进 Agent 状态监控页
   - 点 ANP RPC 测试

4. **展示 commit 历史**（1 分钟）
   ```bash
   git log --oneline | head -20
   git tag -l 'v2.0-*'
   ```

5. **讲踩坑故事**（1.5 分钟）
   - 阶段 36 async_generator bug
   - 阶段 37 SSE 架构优化

---

## 8. 关键文件位置

| 文件 | 作用 |
|------|------|
| `frontend/hostAgentAPI/api.py:4820` | v2 SSE 端点 |
| `frontend/hostAgentAPI/api.py:4618` | v2 smart_chat 端点 |
| `backend/A2AServer/src/A2AServer/v2/v2_agent.py:272` | astream async for 修复 |
| `frontend/wechat_mini_program/utils/api.js:899` | sendMessageV2Stream SSE 客户端 |
| `frontend/wechat_mini_program/pages/agent_chat/agent_chat.js:1645` | _sendWithV2Stream 流式处理 |
| `frontend/wechat_mini_program/pages/agents_status/` | agent 状态监控页 |
| `docs/Chinese/V2_API_REFERENCE.md` | v2 API 文档 |
| `docs/Chinese/V2_ARCHITECTURE.md` | v2 架构文档 |

---

## 9. 完整 commit / tag 列表

```bash
git log --oneline | head -10
# a3d72a5 fix(v2-stage37): 修复 v2 流式显示 3 个 BUG
# b33cdd3 feat(v2-stage37): v2 SSE 流式端点（解决前端轮询问题）
# 124ed3f fix(v2-stage36): 修复 astream() 必須用 async for 的 TypeError
# 85d26e4 feat(v2-stage35): miniapp v2 LangGraph integration + agent status page
# e134a41 docs(v2-stage34): product status, user guide, deploy guide, roadmap
# c1bd1f4 docs(v2-stage30-33): update CHANGELOG and V2_INDEX
# 65b932d feat(v2-stage33): ANP (Agent Network Protocol) integration
# 58cb012 feat(v2-stage30): multi-agent orchestration
# 34f4a65 feat(v2-stage29): v2 LangGraph + DeepSeek 真返中文回复
# f1e95c4 feat(v2-stage28-e2e): v2 LangGraph E2E 真跑通
```

```bash
git tag -l 'v2.0-stage3*'
# v2.0-stage30-orchestration
# v2.0-stage33-anp
# v2.0-stage35-miniapp-v2
# v2.0-stage36-asyncfix
# v2.0-stage37-sse
# v2.0-stage37sse-fix
```

---

## 10. 总结：可面试的 5 大能力

1. **协议设计能力** (A2A/MCP/ANP 三协议)
2. **异步编程深度** (async_generator 修复)
3. **架构优化能力** (轮询 → SSE 流式)
4. **端到端调试** (Docker + curl + wx 模拟器 + 浏览器)
5. **文档 + 版本管理** (24 个 tag + 详细 commit message)

> **背熟这份文档 + 演示流程，面试稳过！** 🎯
