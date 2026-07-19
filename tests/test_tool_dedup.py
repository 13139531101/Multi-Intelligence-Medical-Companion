"""dedup test: 跨 agent + PhaCore, 任何 tool_name 不能重复出现.

阶段 48-19: 写完后必跑 — 失败禁止 merge.
"""
import sys
import os
from collections import defaultdict

# 让 import 找 backend/PhaCore + backend/A2AServer/src
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "backend"))
sys.path.insert(0, os.path.join(_ROOT, "backend", "A2AServer", "src"))

from A2AServer.v2.mcp_discover import (
    discover_mcp_tools_static,
    discover_phacore_tools,
)


def main() -> int:
    print("== PHA Tool Dedup Test (Stage 48-19) ==\n")

    # 收集所有工具
    all_tools: list[dict] = []
    for agent in ("health_advisor", "health_records", "medication_reminder", "visit_summary"):
        all_tools.extend(discover_mcp_tools_static(agent))
    all_tools.extend(discover_phacore_tools())

    # Group by name
    by_name = defaultdict(list)
    for t in all_tools:
        by_name[t["name"]].append((t.get("module", "?"), t.get("agent", "?"), t.get("file", "?")))

    dupes = {n: locs for n, locs in by_name.items() if len(locs) > 1}
    unique = {n: locs for n, locs in by_name.items() if len(locs) == 1}

    print(f"Total tools (跨 4 agent + PhaCore): {len(all_tools)}")
    print(f"  Unique names: {len(unique)}")
    print(f"  Duplicated names: {len(dupes)}")
    print()

    if dupes:
        print("[FAIL] 重复的 tool names (必须 PhaCore 单 owner):")
        for name, locs in sorted(dupes.items()):
            print(f"  - {name}")
            for mod, agent, file in locs:
                print(f"      @ {file}")
        return 1
    else:
        print("[OK] 所有 tool name 跨 agent 唯一, 无重复!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
