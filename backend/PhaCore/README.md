# PhaCore — PHA 共享工具库

> **版本**: v0.1 (起草于阶段 48-19)  
> **目的**: 消除 4 个 sub-agent 中重复实现的 MCP 工具

---

## 1. 是什么

`PhaCore` 是 PHA 的**共享 MCP 工具库**, 提供 4 个 sub-agent 都需要的能力:

| 模块 | 是什么 | 替代谁 |
|---|---|---|
| `mcpserver/shared_ocr.py` | OCR 工具集 (extract_text / validate_medical_document) | HRM `ocr_tool.py` + MedReminder `ocr_tool.py` |
| `mcpserver/shared_reminder.py` | 用药提醒增删查 + 服药打卡 | HRM `reminder_tool.py` + MedReminder `reminder_tool.py` |
| `mcpserver/shared_storage.py` | 健康档案 CRUD + 就诊摘要 CRUD | HRM `storage_tool.py` + VSG `database_tool.py` |
| `mcpserver/shared_health_analysis.py` | 健康趋势分析 + 洞察 + 异常告警 | HRM `async_analysis_tool.py` + HealthAdvisor `knowledge_tool.py` + VSG `ai_analysis_tool.py` |
| `mcpserver/shared_notification.py` | 通知发送 + 提醒设置 | MedReminder `notification_tool.py` |
| `mcpserver/shared_a2a.py` | A2A 跨 agent 调用 helper | HealthAdvisor `a2a_integration_tool.py:12-90` + MedReminder `drug_safety_tool.py:63-149` |
| `mcpserver/shared_db.py` | 统一 DSN + DatabaseManager | 4 份 `_normalize_pg_dsn` + 5 个 agent `database_config.py` |

---

## 2. 边界规则

### 2.1 PhaCore 只放"跨 agent 必需"的能力

**PhaCore 工具的判断标准**:
- 至少 2 个 agent 都需要
- 或者它是某个 tool 的单点 owner (加 alias 后, 别处不再写)
- 或者它是基础设施 (DB, A2A, OCR)

**PhaCore 不放**:
- 只一个 agent 用的工具 (放各自 `mcpserver/`)
- LLM 关联性强的"领域"工具 (e.g. `analyze_symptoms` 在 advisor 的语境更适合 advisor 拥有)
- 一个 agent 的私有 UI helper

### 2.2 PhaCore 工具 = 单 owner + 多 reader

- 每个 tool 有**单一 owner** (例如 `add_medication_reminder` 归 `medication_reminder`)
- 其他 agent 通过 sub_agents `get_tools()` 重导出 PhaCore 工具, 但 owner 是明确的
- 这避免"LLM 不知道调谁"的问题

### 2.3 PhaCore 与现有路由的关系

`host_graph.py` 的 LangGraph 路由**不变** — agent 仍然是 4 个 + host_graph. PhaCore 是**工具共享层**, 不引入新的 agent.

---

## 3. 怎么用

### 3.1 添加 PhaCore 工具

```python
# backend/PhaCore/mcpserver/shared_xxx.py
from mcp.server.fastmcp import FastMCP
from .shared_db import get_pg_conn

mcp = FastMCP("PhaCoreSharedXxx")

@mcp.tool()
def my_new_tool(user_id: str, ...) -> str:
    """文档必须说明 owner / reader / 触发场景."""
    with get_pg_conn() as conn:
        ...
```

### 3.2 让某个 agent 引用 PhaCore 工具

```python
# backend/HealthAdvisor/mcpserver/advisor_tools.py
from PhaCore.mcpserver.shared_ocr import mcp as shared_ocr_mcp

@mcp.tool()
def analyze_via_ocr(image_base64: str) -> str:
    # 重导出 PhaCore 的 OCR, 加 advisor-specific wrapper
    return _call_shared_ocr(image_base64)
```

或者更简洁 — 在 `sub_agents.py`:

```python
class HealthRecordsV2(V2Agent):
    def get_tools(self):
        # PhaCore + 本地
        return (
            load_mcp_tools("health_records", transport=_MCP_TRANSPORT) +
            load_mcp_tools("PhaCore_shared_ocr", transport=_MCP_TRANSPORT)
        )
```

### 3.3 改动 dangerous_tools (HITL)

```python
# backend/A2AServer/src/A2AServer/v2/dangerous_tools.py
# 不要 hardcode tool 名 — 改成从 mcp_discover 自动收集
from .mcp_discover import discover_all_tools

def auto_interrupt_config(agent_name: str) -> Dict[str, Any]:
    """所有 PhaCore *_reminder / *_delete 工具自动 require HITL."""
    all_tools = discover_all_tools()
    return {
        t.name: {"allowed_decisions": ["approve", "reject", "edit"]}
        for t in all_tools
        if t.agent == agent_name and (
            "delete" in t.name or "log_medication" in t.name
        )
    }
```

---

## 4. 文件清单

```
backend/PhaCore/
├── mcpserver/
│   ├── __init__.py
│   ├── shared_ocr.py           (~250 行)
│   ├── shared_reminder.py      (~450 行)
│   ├── shared_storage.py       (~400 行)
│   ├── shared_health_analysis.py (~500 行)
│   ├── shared_notification.py  (~400 行)
│   ├── shared_a2a.py           (~150 行)
│   ├── shared_db.py            (~200 行)
│   └── LEGACY_ALIAS.py         (~50 行, 1 周后删)
├── db/
│   └── 00_full_schema.sql      (完整 schema)
├── mcp_config_shared.json
└── README.md (本文件)
```

---

## 5. 验证

跑 `pytest tests/test_tool_dedup.py` 必须通过。失败的话**禁止 merge**, 因为代表又出现重复。

```python
# tests/test_tool_dedup.py
def test_no_duplicate_tool_names():
    """跨 agent + PhaCore, 任何 (tool_name) 不能在多个地方出现."""
    tools = discover_all_tools()
    by_name = defaultdict(list)
    for t in tools:
        by_name[t.name].append(t.agent)
    dupes = {n: a for n, a in by_name.items() if len(a) > 1}
    assert not dupes, f"重复 tool: {dupes}"
```

---

## 6. 状态

- 📝 文档完成 (本文)
- ⏳ 实施 phase 1 (PhaCore 框架 + OCR): 未开始
- 见 [PHACORE_REFACTOR_PLAN.md](../../docs/Chinese/PHACORE_REFACTOR_PLAN.md) 的完整路线
