"""工具名唯一性守卫：同一份工具列表里不允许出现两个同名工具。

阶段 48-19 建立，阶段 48-29 修正判据 + 修 import 路径。

判据为什么改
------------
原版把 4 个 agent 的工具**汇总成一个全局列表**再查重名，于是恒报 3 个"重复"。
但那 3 个是**跨 agent 的同名私有工具**：

    add_medication_reminder    health_records / medication_reminder
    get_medication_reminders   health_records / medication_reminder
    get_health_record_detail   health_records / visit_summary

路由是「一个请求只进一个 agent」（sub_agents.py 关键词注册 + host_graph 兜底），
每个 agent 只加载自己 mcpserver/ 下的 *_tool.py（mcp_discover._find_mcp_tool_files
按 agent 目录 glob），两边的同名函数**永远不会出现在同一份工具列表里**，模型也
就不可能看到两个同名工具。所以全局重名在这里不是缺陷，拿它判失败是误报。

真正会让模型"看到两个同名工具"的是下面三条，本测试守的就是这三条：

  1. **同一个 agent 的列表内**重名 —— 模型拿到两个同名工具，无法区分该调哪个。
  2. **PhaCore 内部**重名 —— PhaCore 工具被 4 个 agent 全量加载，内部重名会
     同时污染 4 个 agent。
  3. **PhaCore 名撞上某 agent 的领域工具名** —— 该 agent 的列表里立刻出现一对
     同名工具，退化成第 1 条。这正是原 docstring 里「必须 PhaCore 单 owner」
     想表达的那件事。

跨 agent 的私有工具重名只作 WARN 打印，不判失败。
"""
import os
import sys
from collections import defaultdict

# 让 import 找 backend/PhaCore + backend/A2AServer/src
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "backend"))
sys.path.insert(0, os.path.join(_ROOT, "backend", "A2AServer", "src"))

from A2AServer.mcp.mcp_discover import (  # noqa: E402
    discover_mcp_tools_static,
    discover_phacore_tools,
)

AGENTS = ("health_advisor", "health_records", "medication_reminder", "visit_summary")


def _locate(tool: dict) -> str:
    """发现结果里 agent 工具用 file_path，PhaCore 工具用 file —— 两个都认。"""
    return str(tool.get("file_path") or tool.get("file") or "?")


def collect_and_check():
    """返回 (per_agent, phacore, errors, warnings)。"""
    per_agent = {a: discover_mcp_tools_static(a) for a in AGENTS}
    phacore = discover_phacore_tools()

    errors: list[str] = []
    warnings: list[str] = []

    # 判据 1：同一 agent 内重名
    for agent, tools in per_agent.items():
        names = [t["name"] for t in tools]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            errors.append(f"[{agent}] 同一 agent 的工具列表内重名: {dupes}")

    # 判据 2：PhaCore 内部重名
    pnames = [t["name"] for t in phacore]
    pdupes = sorted({n for n in pnames if pnames.count(n) > 1})
    if pdupes:
        errors.append(f"[PhaCore] 共享工具内部重名: {pdupes}")

    # 判据 3：PhaCore 名撞某 agent 的领域工具名
    pset = set(pnames)
    for agent, tools in per_agent.items():
        hit = sorted(pset & {t["name"] for t in tools})
        if hit:
            errors.append(f"[{agent}] PhaCore 工具名与领域工具撞车: {hit}")

    # WARN：跨 agent 私有工具重名（运行时无害）
    owner: dict[str, set] = defaultdict(set)
    for agent, tools in per_agent.items():
        for t in tools:
            owner[t["name"]].add(agent)
    for name in sorted(owner):
        if len(owner[name]) > 1:
            warnings.append(f"{name} 同时定义于 {sorted(owner[name])}（各自私有，运行时无冲突）")

    return per_agent, phacore, errors, warnings


def test_no_tool_name_collisions():
    """pytest 入口。三条判据全过才算绿。"""
    per_agent, phacore, errors, warnings = collect_and_check()
    total = sum(len(t) for t in per_agent.values()) + len(phacore)
    assert total > 0, "一个工具都没发现，discover 路径多半是错的"
    assert not errors, "工具名冲突:\n" + "\n".join("  - " + e for e in errors)


def main() -> int:
    print("== PHA Tool Dedup Test (Stage 48-19, 判据修正于 48-29) ==\n")

    per_agent, phacore, errors, warnings = collect_and_check()

    for agent, tools in per_agent.items():
        print(f"  {agent:<22} {len(tools):>3} tools")
    print(f"  {'PhaCore (共享)':<22} {len(phacore):>3} tools")
    print(f"\n  合计: {sum(len(t) for t in per_agent.values()) + len(phacore)} tools\n")

    if warnings:
        print(f"[WARN] 跨 agent 私有工具重名 {len(warnings)} 处（不判失败）:")
        for w in warnings:
            print(f"  - {w}")
        print()

    if errors:
        print(f"[FAIL] 工具名冲突 {len(errors)} 处:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("[OK] 无同名工具会落进同一份工具列表：agent 内唯一 / PhaCore 内唯一 / PhaCore 不撞领域工具")
    return 0


if __name__ == "__main__":
    sys.exit(main())
