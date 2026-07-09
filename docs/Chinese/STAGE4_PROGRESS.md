# 阶段4 推进记录

> 启动时间：2026-03
> 目标：把 v2 桥接到 hostAgentAPI，让前端请求可走 v2 HostGraph
> 状态：✅ **bridge 端到端跑通（11/11 通过）**

## 交付物

| 文件 | 作用 |
|------|------|
| [backend/A2AServer/src/A2AServer/v2/bridge.py](../../backend/A2AServer/src/A2AServer/v2/bridge.py) | v2 桥接器（接入 A2A Message + 灰度路由 + fallback）|
| [frontend/hostAgentAPI/server.py](../../frontend/hostAgentAPI/server.py) | `_send_message` 入口增加 v2 灰度路由 |
| [scripts/verify_stage4.py](../../scripts/verify_stage4.py) | 阶段4 验收脚本（11/11 通过）|

## 灰度路由机制

### 触发条件（任一）

1. **Header `X-Use-V2: true`**
2. **Header `X-PHA-Version: v2`**
3. **环境变量 `PHA_USE_V2=true`**（全量切流）

### 失败自动 fallback

```
HTTP 请求
  ↓
is_v2_request() 判断
  ↓ (True)
v2_process_message()
  ↓
  ├─ 成功 → 注入到 manager._messages + conversation
  └─ 失败 → fallback 到 v1 self.manager.process_message()
  ↓
返回正常 A2A 响应
```

## 验收结果

```
[1] v2 开关函数
  [OK] is_v2_enabled() 默认 False
  [OK] PHA_USE_V2=true 后 is_v2_enabled()
  [OK] is_v2_request(header X-Use-V2=true)
  [OK] is_v2_request(header X-PHA-Version=v2)
  [OK] is_v2_request(无 header) 默认 False

[2] v2_process_message 端到端
  [OK] v2_process_message 返回 result
  [OK] used_v2=True
  [OK] 无 error
  [OK] message 已构造
  [OK] 消息内容非空 (len=1078)
  [OK] metadata 含 v2_routing (agent=health_advisor)

阶段4 验收：11/11 通过
[OK] 全部通过！v2 bridge 接入就绪。
```

## 端到端调用链

```
前端 /message/send (Header X-Use-V2: true)
  ↓
hostAgentAPI._send_message
  ↓
v2_bridge.v2_process_message
  ↓
route_and_invoke (HostGraph)
  ↓
classify_node (3 层路由)
  ↓ (layer 2 启发: "头疼" -> health_advisor)
invoke_health
  ↓
HealthAdvisorV2.stream() (LangChain 1.0 create_agent)
  ↓
DeepSeek API (model=deepseek-chat)
  ↓
真实 MCP 工具调用 (analyze_health_concern)
  ↓
返回 1078 字符健康建议
```

## 兼容性保证

- ✅ v1 路径完全保留（`PHA_USE_V2` 默认 False）
- ✅ v2 失败自动 fallback v1
- ✅ A2A 协议层（`Message`/`TextPart`/`metadata`）格式不变
- ✅ 现有前端请求**零修改**（不传 header 就是 v1）
- ✅ 灰度切流（前端按用户/请求级别加 header 即可）

## 下一步使用

### 1. 单个用户测试 v2
```bash
curl -X POST http://localhost:10010/message/send \
  -H "Content-Type: application/json" \
  -H "X-Use-V2: true" \
  -d '{"params": {...}}'
```

### 2. 全量切流
在 `.env` 加：
```
PHA_USE_V2=true
```

### 3. 验证 v2 走了
看 server.py 日志：
```
[PHA v2] routing to v2 HostGraph
[PHA v2] success: agent=health_advisor
```

## 风险评估

- ⚠️ v2 LangGraph 状态可恢复需要 InMemorySaver/PostgresSaver（当前默认 None，**不破坏 v1**）
- ⚠️ 真实工具调用慢（5-30s）vs v1 内存流式（1-2s）。前端可能需要加 loading 状态
- ⚠️ 错误 fallback 已实现，但**没用 rate limit**。生产建议加 限流中间件
