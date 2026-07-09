# PHA v2 API 参考

> 面向：调用 v2 HostGraph / a2a-sdk Server 的前端 / 集成方

---

## 1. 端点总览

| 端点                               | 端口  | 协议                 | 说明                 |
| ---------------------------------- | ----- | -------------------- | -------------------- |
| `POST /message/send`               | 10010 | A2A 私有             | 主入口（v1+v2 灰度） |
| `GET /.well-known/agent-card.json` | 10020 | a2a-sdk              | 服务发现             |
| `POST /`                           | 10020 | a2a-sdk JSON-RPC 2.0 | a2a-sdk 标准入口     |

---

## 2. 主入口（hostAgentAPI :10010）

### 2.1 POST /message/send

#### v1 路径（无 header）

```http
POST /message/send HTTP/1.1
Content-Type: application/json
Authorization: Bearer eyJ...

{
  "params": {
    "id": "task-123",
    "sessionId": "conv-abc",
    "message": {
      "role": "user",
      "parts": [{"text": "我最近头疼"}],
      "metadata": {
        "user_id": "u_001",
        "conversation_id": "conv-abc"
      }
    },
    "acceptedOutputModes": ["text"]
  }
}
```

**响应**：v1 BasicAgent 流式返回（`text/event-stream`）

#### v2 路径（带 X-Use-V2 header）

```http
POST /message/send HTTP/1.1
Content-Type: application/json
Authorization: Bearer eyJ...
X-Use-V2: true
X-PHA-Version: v2

{
  "params": {
    "id": "task-124",
    "sessionId": "conv-abc",
    "message": {
      "role": "user",
      "parts": [{"text": "我最近头疼"}],
      "metadata": {
        "user_id": "u_001",
        "conversation_id": "conv-abc"
      }
    },
    "acceptedOutputModes": ["text"]
  }
}
```

**响应**：v2 HostGraph 流式返回

**响应消息 metadata 包含 v2 信息**：

```json
{
  "role": "agent",
  "parts": [{"text": "建议多休息..."}],
  "metadata": {
    "v2_routing": {
      "layer": 2,
      "target": "health_advisor"
    },
    "v2_tool_calls": [
      {"name": "analyze_health_concern", "args": {...}}
    ],
    "agent": "health_advisor"
  }
}
```

### 2.2 触发 v2 的三种方式

```bash
# 方式 1：header
curl -H "X-Use-V2: true" ...

# 方式 2：header（标准）
curl -H "X-PHA-Version: v2" ...

# 方式 3：环境变量（全量切流）
echo "PHA_USE_V2=true" >> .env
```

### 2.3 完整 cURL 示例

```bash
# 测 v1（默认）
curl -X POST http://localhost:10010/message/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ..." \
  -d '{
    "params": {
      "id": "task-001",
      "sessionId": "conv-001",
      "message": {
        "role": "user",
        "parts": [{"text": "我最近头疼"}],
        "metadata": {
          "user_id": "u_001",
          "conversation_id": "conv-001"
        }
      }
    }
  }'

# 测 v2
curl -X POST http://localhost:10010/message/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ..." \
  -H "X-Use-V2: true" \
  -d '{
    "params": {
      "id": "task-002",
      "sessionId": "conv-001",
      "message": {
        "role": "user",
        "parts": [{"text": "我最近头疼"}],
        "metadata": {
          "user_id": "u_001",
          "conversation_id": "conv-001"
        }
      }
    }
  }'
```

---

## 3. a2a-sdk Server (:10020)

### 3.1 GET /.well-known/agent-card.json

**服务发现**（a2a-sdk 标准）：

```bash
curl http://localhost:10020/.well-known/agent-card.json
```

**响应**：

```json
{
  "name": "PHA HostGraph v2",
  "description": "PHA 多智能体健康助理 - 基于 LangGraph 1.0 + LangChain 1.0 + DeepSeek",
  "url": "http://localhost:10020",
  "version": "2.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": true
  },
  "defaultInputModes": ["text", "text/plain"],
  "defaultOutputModes": ["text", "text/plain"],
  "skills": []
}
```

### 3.2 POST / (JSON-RPC 2.0)

#### message/send

**请求**（a2a-sdk 标准 JSON-RPC 2.0）：

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "messageId": "msg-001",
      "role": "user",
      "contextId": "ctx-001",
      "parts": [{ "kind": "text", "text": "我最近头疼" }],
      "metadata": { "user_id": "u_001" }
    }
  }
}
```

**响应**：

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "kind": "message",
    "message": {
      "kind": "message",
      "messageId": "msg-002",
      "role": "agent",
      "parts": [{ "kind": "text", "text": "建议多休息..." }],
      "metadata": {
        "pha_v2": true,
        "agent": "health_advisor",
        "v2_routing": { "layer": 2, "target": "health_advisor" }
      }
    },
    "contextId": "ctx-001"
  }
}
```

#### message/stream（流式）

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "message/stream",
  "params": {
    "message": {
      "kind": "message",
      "messageId": "msg-001",
      "role": "user",
      "parts": [{ "kind": "text", "text": "..." }]
    }
  }
}
```

**响应**：`text/event-stream`（SSE 协议）

#### agent/card

```json
{
  "jsonrpc": "2.0",
  "id": "req-003",
  "method": "agent/card"
}
```

### 3.3 a2a-sdk 客户端调用示例

```python
# Python a2a-sdk 0.3.25 客户端
import asyncio
import httpx
import uuid
from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    Message,
    TextPart,
    Part,
    Role,
)


async def main():
    async with httpx.AsyncClient() as http:
        client = A2AClient(httpx_client=http, url="http://localhost:10020")

        request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message=Message(
                    messageId=str(uuid.uuid4()),
                    role=Role.user,
                    parts=[Part(root=TextPart(text="我最近头疼"))],
                    contextId="ctx-001",
                ),
            ),
        )

        response = await client.send_message(request)
        if response.result:
            msg = response.result.message
            text = msg.parts[0].root.text
            print(f"Agent: {msg.metadata.get('agent')}")
            print(f"Response: {text}")


asyncio.run(main())
```

```javascript
// JavaScript a2a-sdk 客户端
import { A2AClient } from "@a2a-js/sdk/client";
import { v4 as uuid } from "uuid";

const client = new A2AClient("http://localhost:10020");

const response = await client.sendMessage({
  id: uuid(),
  params: {
    message: {
      kind: "message",
      messageId: uuid(),
      role: "user",
      parts: [{ kind: "text", text: "我最近头疼" }],
    },
  },
});

console.log(response.result.message.parts[0].text);
```

```bash
# cURL
curl -X POST http://localhost:10020/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "messageId": "msg-001",
        "role": "user",
        "parts": [{"kind": "text", "text": "我最近头疼"}]
      }
    }
  }'
```

---

## 4. Python SDK (A2AServer.v2)

### 4.1 路由 + 调用

```python
import asyncio
from A2AServer.v2 import route_and_invoke

async def main():
    result = await route_and_invoke(
        query="我最近头疼",
        conversation_id="conv-001",
        user_id="u_001",
        metadata={"selected_agent": "health_advisor"},  # 可选
    )
    print(result)
    # {
    #     "role": "agent",
    #     "content": "建议多休息...",
    #     "agent": "health_advisor",
    #     "routing": {"layer": 1, "target": "health_advisor"},
    #     "tool_calls": [{"name": "analyze_symptoms", "args": {...}}]
    # }

asyncio.run(main())
```

### 4.2 直接使用 V2Agent

```python
import asyncio
from A2AServer.v2 import HealthAdvisorV2

async def main():
    agent = HealthAdvisorV2()
    print(f"model: {agent.model}")
    print(f"tools: {[t.name for t in agent.get_tools()]}")

    async for event in agent.stream(
        query="我最近头疼",
        session_id="conv-001",
        user_id="u_001",
    ):
        if event.get("type") == "normal":
            print(f"text: {event.get('content')}")
        elif event.get("type") == "tool_call":
            print(f"tool: {event.get('name')}")
        elif event.get("is_task_complete"):
            print("DONE")
            break

asyncio.run(main())
```

### 4.3 加载 MCP 工具

```python
from A2AServer.v2.mcp_tool_adapter import load_mcp_tools

# 加载 health_advisor 的所有真实 MCP 工具
tools = load_mcp_tools("health_advisor")
for tool in tools:
    print(f"- {tool.name}: {tool.description[:80]}")
# - analyze_symptoms: 基于真实数据的症状关联检索与证据汇总
# - get_disease_info: 获取特定疾病的详细信息
# - generate_health_assessment: 生成综合健康评估报告
# - ai_medical_diagnosis: 使用讯飞医疗大模型进行智能诊断分析
# - search_symptom_info: 搜索症状相关信息
# ... 共 11 个
```

### 4.4 静态扫描 MCP 工具

```python
from A2AServer.v2.mcp_discover import discover_mcp_tools_static

# 不执行 module，扫描所有 @mcp.tool() 装饰的函数
tools = discover_mcp_tools_static("health_advisor")
for t in tools:
    print(f"- {t['name']}: args={t['args']}")
```

### 4.5 检查 v2 runtime 状态

```python
from A2AServer.v2 import get_runtime

runtime = get_runtime()
print(f"available: {runtime.available}")
print(f"checkpointer: {runtime.get_checkpointer()}")
```

---

## 5. 协议转换 API

### 5.1 PHA → a2a-sdk

```python
from A2AServer.v2.a2a_sdk_compat import (
    pha_to_sdk_message,
    pha_to_sdk_request,
    build_pha_agent_card,
)
from A2AServer.common.A2Atypes import Message, TextPart

# PHA Message
pha_msg = Message(
    role="user",
    parts=[TextPart(text="我头疼")],
    metadata={"conversation_id": "c1"},
)

# 转 a2a-sdk
sdk_msg = pha_to_sdk_message(pha_msg)
sdk_req = pha_to_sdk_request({
    "id": "req-1",
    "sessionId": "c1",
    "message": pha_msg,
})

# 构造 AgentCard
card = build_pha_agent_card()
print(card.name, card.version)
```

### 5.2 a2a-sdk → PHA

```python
from A2AServer.v2.a2a_sdk_compat import sdk_to_pha_message

# a2a-sdk Message
from a2a.types import Message, TextPart, Part, Role
import uuid
sdk_msg = Message(
    messageId=str(uuid.uuid4()),
    role=Role.agent,
    parts=[Part(root=TextPart(text="建议多休息"))],
)

# 转 PHA
pha_msg = sdk_to_pha_message(sdk_msg)
print(pha_msg.role, pha_msg.parts[0].text)
```

---

## 6. 错误码

| 错误码                           | 含义                     | 触发条件       | 客户端处理      |
| -------------------------------- | ------------------------ | -------------- | --------------- |
| `200`                            | 成功                     | 正常响应       | 显示 content    |
| `401`                            | 未授权                   | JWT 缺失/过期  | 跳转登录        |
| `403`                            | 无权                     | 会话归属错误   | 提示用户        |
| `500`                            | 服务器错误               | v2 + v1 都失败 | 重试 + 反馈     |
| `-32603`                         | a2a-sdk Internal error   | v2 处理失败    | 检查 server log |
| `-32601`                         | a2a-sdk Method not found | method 拼错    | 检查 SDK 文档   |
| `openai.AuthenticationError 401` | LLM 鉴权失败             | API key 错误   | 检查 .env       |

---

## 7. 性能指标

| 端点                               | P50 延迟 | P99 延迟 | 备注              |
| ---------------------------------- | -------- | -------- | ----------------- |
| `POST /message/send` (v1)          | 1-2s     | 5s       | 单 LLM 调用       |
| `POST /message/send` (v2)          | 5-10s    | 30s      | 工具调用 + LLM    |
| `POST /message/send` (v2 复杂)     | 15-25s   | 60s      | 多次工具调用      |
| `POST /` (a2a-sdk)                 | 同 v2    | 同 v2    | 经 hostGraph 内部 |
| `GET /.well-known/agent-card.json` | <100ms   | <200ms   | 静态              |

---

## 8. SDK 版本要求

| 依赖                   | 最低版本 | 推荐版本 | 说明         |
| ---------------------- | -------- | -------- | ------------ |
| `langchain`            | 1.2.10   | 1.2.10   | 必 pin       |
| `langgraph`            | 1.0.5    | 1.0.10   |              |
| `langgraph-prebuilt`   | 1.0.5    | 1.0.5    | **关键 pin** |
| `langgraph-checkpoint` | 3.0.1    | 3.0.1    | **关键 pin** |
| `langchain-openai`     | 0.3.0    | 1.3.3    |              |
| `a2a-sdk`              | 0.3.0    | 0.3.25   |              |

---

## 9. 联系

- 文档问题：开 GitHub Issue
- 性能问题：参考 [V2_OPERATIONS.md](V2_OPERATIONS.md)
- 协议问题：参考 [V2_MIGRATION_NOTES.md](V2_MIGRATION_NOTES.md)
