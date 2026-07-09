# PHA v2 开发者指南

> 面向：新增 Agent / 工具 / 路由的开发人员
> 阅读时间：~20 分钟

---

## 1. 快速上手

### 1.1 5 分钟跑通 v2

```bash
# 1. 克隆并进入
cd i:\A2A\3\A2AServer

# 2. 安装依赖（关键 pin）
pip install "langchain==1.2.10" "langgraph==1.0.10" "langgraph-prebuilt==1.0.5" \
            "langgraph-checkpoint==3.0.1" "langchain-openai==1.3.3" "a2a-sdk==0.3.25"

# 3. 配置 .env（必备）
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx  # 可同 DEEPSEEK

# 4. 跑验收
python scripts/verify_stage2.py    # 框架
python scripts/verify_stage2_5.py  # MCP 工具
python scripts/verify_stage3.py    # HostGraph
python scripts/verify_stage4.py    # 桥接
python scripts/verify_stage5.py    # a2a-sdk

# 5. 启动 hostAgentAPI
cd frontend/hostAgentAPI
python server.py

# 6. 测试 v2（带 header）
curl -X POST http://localhost:10010/message/send \
  -H "X-Use-V2: true" \
  -H "Content-Type: application/json" \
  -d '{"params": {"message": {"role": "user", "parts": [{"text": "我头疼"}], "metadata": {}}}}'
```

### 1.2 IDE 配置

VSCode / Trae 推荐的 `launch.json`（断点调试 v2）：

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Verify Stage 2.5",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/scripts/verify_stage2_5.py",
      "console": "integratedTerminal",
    },
    {
      "name": "Run HostAgentAPI",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/frontend/hostAgentAPI/server.py",
      "console": "integratedTerminal",
    }
  ]
}
```

---

## 2. 新增一个子 Agent

### 2.1 场景

假设要加一个 `NutritionAdvisorV2`（营养顾问）。

### 2.2 步骤

**Step 1: 创建 backend 目录**

```bash
mkdir -p backend/NutritionAdvisor/mcpserver
cd backend/NutritionAdvisor
touch __init__.py
touch mcpserver/__init__.py
touch mcpserver/diet_tool.py
```

**Step 2: 实现 MCP 工具**

```python
# backend/NutritionAdvisor/mcpserver/diet_tool.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DietTool")

@mcp.tool()
def recommend_meal(disease: str = "糖尿病", user_id: str = "") -> dict:
    """根据疾病推荐健康饮食"""
    return {
        "disease": disease,
        "meals": [
            {"breakfast": "燕麦粥", "lunch": "蒸鱼+蔬菜", "dinner": "豆腐汤"},
        ],
        "tips": "低糖、低盐、规律饮食",
    }
```

**Step 3: 在 `v2/sub_agents.py` 添加 Agent**

```python
# backend/A2AServer/src/A2AServer/v2/sub_agents.py
from .v2_agent import V2Agent
from .mcp_tool_adapter import load_mcp_tools

class NutritionAdvisorV2(V2Agent):
    name = "nutrition_advisor"
    system_prompt = """你是 PHA 的营养顾问 Agent。

    你的职责：
    - 根据用户的疾病情况推荐健康饮食
    - 提供营养知识和饮食建议
    - 提醒用户饮食禁忌

    注意：
    - 你是营养顾问，不是医生，不能给出医疗诊断
    - 建议仅供参考，需配合专业医师意见
    """

    def get_tools(self):
        return load_mcp_tools(self.name)
```

**Step 4: 在 `v2/host_graph.py` 加 invoke 节点**

```python
# 在 v2/host_graph.py 中
# 1. AGENT_ALIAS 添加映射
AGENT_ALIAS = {
    ...
    "营养顾问": "nutrition_advisor",
    "nutrition_advisor": "nutrition_advisor",
}

# 2. HEURISTIC_KEYWORDS 添加关键词
HEURISTIC_KEYWORDS = {
    ...
    "nutrition_advisor": ["饮食", "营养", "食谱", "diet", "meal"],
}

# 3. build_host_graph() 加节点
g.add_node("invoke_nutrition", invoke_agent_node("nutrition_advisor"))

# 4. _route_decision 加分支
def _route_decision(state: HostState) -> str:
    target = state.get("target_agent", "health_advisor")
    return {
        ...
        "nutrition_advisor": "invoke_nutrition",
    }.get(target, "invoke_health")

# 5. add_conditional_edges 加映射
g.add_conditional_edges(
    "classify",
    _route_decision,
    {
        ...
        "invoke_nutrition": "invoke_nutrition",
    },
)

# 6. 加边
g.add_edge("invoke_nutrition", "aggregate")
```

**Step 5: 跑测试**

```python
# scripts/verify_new_nutrition.py
import asyncio
import sys
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2 import route_and_invoke

async def test():
    result = await route_and_invoke(
        query="糖尿病患者应该怎么吃？",
        conversation_id="test-nutrition-001",
        user_id="u_nutrition",
    )
    print(f"agent: {result.get('agent')}")
    print(f"content: {result.get('content')[:200]}")

asyncio.run(test())
```

---

## 3. 新增一个 MCP 工具

### 3.1 场景

给 `HealthAdvisor` 加一个 `drug_interaction_check` 工具（药物互作检查）。

### 3.2 步骤

**Step 1: 在 `backend/HealthAdvisor/mcpserver/` 加文件**

```python
# backend/HealthAdvisor/mcpserver/drug_interaction_tool.py
from mcp.server.fastmcp import FastMCP
from typing import List

mcp = FastMCP("DrugInteractionTool")

@mcp.tool()
def check_drug_interaction(drugs: List[str], user_id: str = "") -> dict:
    """
    检查多种药物的相互作用

    Args:
        drugs: 药物名称列表 (如 ["阿司匹林", "布洛芬"])
        user_id: 用户ID

    Returns:
        含互作结果、安全等级、建议的 dict
    """
    # 你的业务逻辑...
    if "阿司匹林" in drugs and "布洛芬" in drugs:
        return {
            "safe": False,
            "risk_level": "high",
            "interactions": ["阿司匹林 + 布洛芬 增加出血风险"],
            "advice": "避免同时使用"
        }
    return {"safe": True, "risk_level": "low", "interactions": [], "advice": "可同时使用"}
```

**Step 2: 测试自动发现**

```bash
python -c "
import sys
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2.mcp_tool_adapter import load_mcp_tools
tools = load_mcp_tools('health_advisor')
print([t.name for t in tools])
"
# 输出: ['analyze_symptoms', ..., 'check_drug_interaction']
```

**Step 3: 在系统 prompt 提示工具**

```python
# v2/sub_agents.py
class HealthAdvisorV2(V2Agent):
    system_prompt = """你是 PHA 的健康顾问。

    你有以下工具可用：
    - analyze_symptoms: 症状分析
    - search_symptom_info: 症状知识搜索
    - check_drug_interaction: **药物相互作用检查（新工具）**
    - ...
    """
```

**无需改其他代码！** MCP 工具自动发现机制会加载你的新工具。

---

## 4. 调试技巧

### 4.1 路由决策不生效

**症状**：请求总是路由到错误的 Agent

**排查**：
```python
# 加 debug 日志
import logging
logging.getLogger('A2AServer.v2.host_graph').setLevel(logging.DEBUG)

# 看哪一层路由命中
python -c "
import sys
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2.host_graph import _layer1_metadata, _layer2_heuristic
state = {'metadata': {'selected_agent': '健康顾问'}, 'query': '我头疼', 'events': []}
print('layer1:', _layer1_metadata(state))
print('layer2:', _layer2_heuristic(state))
"
```

### 4.2 工具调用失败

**症状**：Agent 返回"Error: ..."

**排查**：
```python
# 直接调用工具函数
from A2AServer.v2.mcp_discover import load_mcp_tool_function
func = load_mcp_tool_function('health_advisor', 'diagnosis_tool', 'analyze_symptoms')
print(func(symptoms=['头痛', '发烧']))
```

**常见原因**：
- 缺依赖（`pip install` 装）
- DB 连不上（本地 docker-compose 启动 postgres）
- 函数签名不匹配（**必须用 `**kwargs`** 兼容 LangChain 1.0）

### 4.3 流式输出无响应

**症状**：`agent.stream()` 不返回

**排查**：
```python
# 检查 LangGraph 1.0 是否真在工作
from A2AServer.v2 import get_runtime
print('runtime available:', get_runtime().available)
print('checkpointer:', get_runtime().get_checkpointer())
```

**降级**：
- 如果 LangGraph 1.0 不可用，V2Agent 会**自动降级**到基础 LLM 调用
- 想要完整功能，**必须**安装 `langchain==1.2.10` + `langgraph==1.0.10` + `langgraph-prebuilt==1.0.5`

### 4.4 a2a-sdk 协议字段不识别

**症状**：`ValidationError: 4 validation errors for Message`

**常见原因**：
- `MessageSendParams.contextId` 在 0.3.25 已移除，改用 `Message.contextId`
- `Role.user` 是枚举类，比较用 `== Role.user`
- `parts=[]` 不允许，至少要一个空 TextPart

---

## 5. 测试规范

### 5.1 验收脚本约定

每个阶段必须有一个 `scripts/verify_stageN.py`：

```python
# 模板
import os, sys, asyncio
from pathlib import Path
from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v
sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('PHA v2 阶段N 验收')
print('=' * 70)

total = 0
passed = 0

def check(name, ok, detail=''):
    global total, passed
    total += 1
    if ok:
        passed += 1
        print(f'  [OK]  {name}')
    else:
        print(f'  [FAIL] {name}  {detail}')

# ... 测试项

print(f'\n阶段N 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
```

### 5.2 关键测试场景

每个新 Agent/工具必须覆盖：

1. **单元测试**：路由函数、工具函数
2. **集成测试**：Agent + 工具 + LLM
3. **端到端测试**：通过 hostAgentAPI 或 a2a-sdk server
4. **降级测试**：缺依赖时自动降级，不崩溃

---

## 6. 代码规范

### 6.1 Python 代码风格

- 遵循 PEP 8
- 类型注解必须（`def foo(x: str) -> dict:`）
- docstring 用中文（项目约定）
- 行长 < 120 字符

### 6.2 Git 提交规范

```
feat(v2-stageN): 简短描述

详细描述：
- 改动 1
- 改动 2

兼容性：
- v1 路径仍工作
- ...

Co-Authored-By: Claude <noreply@anthropic.com>
```

### 6.3 Tag 规范

```
v2.0-stageN       # 主版本 tag（推 GitHub + Gitee）
v2.0-stageN.M     # 修复 tag（可重打）
```

---

## 7. 性能优化

### 7.1 当前性能瓶颈

| 瓶颈 | 原因 | 解决方案 |
|------|------|---------|
| 工具调用慢 | 5-30s（含 LLM + 工具）| 1) 缓存热点查询 2) 预热工具 |
| 状态恢复慢 | Postgres 网络 | 本地 InMemorySaver (开发) / PostgresSaver (生产) |
| 流式延迟 | LLM 推理时间 | 用更快的 model (deepseek-v4-flash) |

### 7.2 常用优化

- **减少工具数**：只暴露必要工具
- **关键词优先**：用 layer2 启发快速路由（避免 LLM 决策）
- **缓存**：高频 query 走 Redis

---

## 8. 常见问题 FAQ

**Q1: V2Agent 和 BasicAgent 能不能同时用？**
A: 能。`PHA_USE_V2=false`（默认）走 v1 BasicAgent。`X-Use-V2=true` 走 v2。

**Q2: 升级 LangChain 后 v1 还能用吗？**
A: v1 BasicAgent 仍可 import。V2Agent 是独立模块。

**Q3: 怎么知道 v2 在跑？**
A: 看日志 `[PHA v2] routing to v2 HostGraph` 和 `[PHA v2] success: agent=...`

**Q4: a2a-sdk server 端口 10020 必须开吗？**
A: 不必须。独立服务，给需要 a2a 协议兼容的客户端用。

**Q5: 怎么切换到 OpenAI 而不是 DeepSeek？**
A: 设 `OPENAI_API_BASE=https://api.openai.com/v1` + `PHA_LLM_MODEL=openai:gpt-4o-mini`

---

## 9. 进阶：自定义中间件

PHA v2 支持 LangChain 1.0 Middleware（参考 `v2_runtime.py: get_middlewares`）：

```python
# v2_runtime.py 添加新中间件
from langchain.agents.middleware import HumanInTheLoopMiddleware

def get_middlewares(self, model):
    middlewares = []
    if HumanInTheLoopMiddleware is not None:
        middlewares.append(HumanInTheLoopMiddleware(
            interrupt_on={"send_email": True},  # send_email 工具需人工确认
        ))
    return middlewares
```

更多中间件类型：
- `PIIRedactionMiddleware`：PII 脱敏
- `SummarizationMiddleware`：长上下文压缩
- `HumanInTheLoopMiddleware`：人在回路（关键操作需确认）
- `LLMToolSelectorMiddleware`：LLM 选工具

---

## 10. 下一步推荐

1. **跑 `verify_stage5.py`** 确认一切正常
2. **读 [V2_API_REFERENCE.md](V2_API_REFERENCE.md)** 了解所有 API
3. **读 [V2_OPERATIONS.md](V2_OPERATIONS.md)** 了解部署
4. **开始你的第一个改动**：加一个 tool 或一个 Agent
