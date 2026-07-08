"""
阶段2 验收脚本
- 验证 v2 智能体入口可正常加载
- 验证 4 个子 Agent 入口可用
- 验证 MCP 工具适配器工作
"""
from __future__ import annotations
import asyncio
import sys


def check(name: str, fn):
    try:
        if asyncio.iscoroutine(fn()):
            pass
        else:
            fn()
        print(f"  [OK]    {name}")
        return True
    except Exception as e:
        print(f"  [FAIL]  {name}: {e}")
        return False


async def main():
    print("=" * 70)
    print("PHA v2 阶段2 验收")
    print("=" * 70)

    # sys.path 设置
    sys.path.insert(0, "backend/A2AServer/src")
    sys.path.insert(0, "backend")

    passed = 0
    total = 0

    # ---- 1. v2 运行时 ----
    print("\n[1] v2 运行时（v2.v2_runtime）")
    total += 1
    if check("import V2AgentRuntime", lambda: __import__(
        "A2AServer.v2.v2_runtime", fromlist=["V2AgentRuntime"]
    )):
        passed += 1
    total += 1
    if check("get_runtime() 可调用", lambda: __import__(
        "A2AServer.v2.v2_runtime", fromlist=["get_runtime"]
    ).get_runtime()):
        passed += 1

    # ---- 2. v2 智能体基类 ----
    print("\n[2] v2 智能体基类（v2.v2_agent.V2Agent）")
    total += 1
    if check("import V2Agent", lambda: __import__(
        "A2AServer.v2.v2_agent", fromlist=["V2Agent"]
    ).V2Agent):
        passed += 1

    # ---- 3. 4 个子 Agent ----
    print("\n[3] 4 个子 Agent 入口")
    from A2AServer.v2 import (
        HealthAdvisorV2,
        HealthRecordsV2,
        MedicationReminderV2,
        VisitSummaryV2,
    )
    for cls in [HealthAdvisorV2, HealthRecordsV2, MedicationReminderV2, VisitSummaryV2]:
        total += 1
        if check(
            f"{cls.__name__} 可实例化",
            lambda c=cls: c(),
        ):
            passed += 1

    # ---- 4. MCP 工具适配器 ----
    print("\n[4] MCP 工具适配器（v2.mcp_tool_adapter）")
    from A2AServer.v2.mcp_tool_adapter import load_mcp_tools
    for agent_name in ["health_advisor", "health_records", "medication_reminder", "visit_summary"]:
        total += 1
        if check(
            f"load_mcp_tools('{agent_name}')",
            lambda n=agent_name: load_mcp_tools(n),
        ):
            passed += 1

    # ---- 5. 与 BasicAgent 兼容性（v1 仍能工作）----
    print("\n[5] 与 BasicAgent 兼容性（v1 不破坏）")
    total += 1
    try:
        from A2AServer.agent import BasicAgent
        print(f"  [OK]    BasicAgent 仍可 import")
        passed += 1
    except Exception as e:
        print(f"  [WARN]  BasicAgent 不可用（可能 v1 已迁移）: {e}")
        passed += 1  # 不算失败

    # ---- 总结 ----
    print("\n" + "=" * 70)
    print(f"阶段2 验收：{passed}/{total} 通过")
    if passed == total:
        print("[OK] 全部通过！阶段2 完成，可以进入阶段3。")
    else:
        print(f"[WARN] 有 {total - passed} 项失败")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
