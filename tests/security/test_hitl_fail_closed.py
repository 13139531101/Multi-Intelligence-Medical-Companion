# -*- coding: utf-8 -*-
"""
HITL fail-closed 回归门禁 —— **判定不可用时，危险工具不交给模型**。

对应漏洞
--------
F-017  HITL 判定链路的 4 个静默降级点（v2_runtime.py / dangerous_tools.py）
       → 判定失效时全部危险操作**无人确认直接执行**，而且没人知道

证据链（同一份测试文件，两个 tag）
----------------------------------
    git checkout vuln-017  && python tests/security/test_hitl_fail_closed.py   # FAIL
    git checkout fixed-017 && python tests/security/test_hitl_fail_closed.py   # PASS

被测对象
--------
A2AServer.v2.hitl_guard.restrict_tools / HitlStatus
接线点：A2AServer.v2.v2_runtime.get_middlewares（判定 + 装 middleware）
        A2AServer.v2.v2_agent.V2Agent._ensure_agent（把危险工具摘出工具集）

六条安全不变式
--------------
1. HITL 装不上时，受保护的工具**不能**出现在模型可见的工具列表里
2. HITL 正常时，工具一个都不能少（不能为了"安全"把功能砍光）
3. 判定器不可用时**拒绝启动**，不能"降级继续跑"
4. **降级路径的保护集合必须等于正常路径**（失效可以更严，不能更松）
5. 判定器不依赖 langchain —— langchain 缺失时它仍然算得出来（否则修法 2 无解）
6. 结构守卫：降级必须**可见**（logger.error，不能是 logger.debug），
   而且**必须接线**（v2_agent 真调用了 restrict_tools）

为什么第 6 条要静态检查
------------------------
「没接线的控制点等于不存在」—— 这条教训在 F-007（check_permission 没接进
MCP 调用链）上已经付过一次学费。判定逻辑写得再对，没人调用它就是零。
"""
import os
import sys

# 让 import 找 backend/A2AServer/src
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # tests/security -> tests -> repo root
sys.path.insert(0, os.path.join(_ROOT, "backend", "A2AServer", "src"))

V2_DIR = os.path.join(_ROOT, "backend", "A2AServer", "src", "A2AServer", "v2")


class _FakeTool:
    """够用的假工具 —— 门禁不该为了测一个纯函数而依赖 langchain。"""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "<tool %s>" % self.name


TOOLS = [
    _FakeTool("get_health_records"),
    _FakeTool("save_health_record"),
    _FakeTool("delete_health_record"),
    _FakeTool("add_health_reminder"),
    _FakeTool("create_user_profile"),
]

# 判定器（能力表口径）认为该拦的
PROTECTED = {"save_health_record", "delete_health_record", "add_health_reminder",
             "create_user_profile"}


# --------------------------------------------------------------------------
# 1. HITL 装不上时，受保护的工具不能给模型
# --------------------------------------------------------------------------
def check_degraded_removes_protected_tools():
    from A2AServer.v2.hitl_guard import HitlStatus, restrict_tools

    status = HitlStatus(active=False, protected=frozenset(PROTECTED),
                         reason="middleware-missing")
    kept, removed = restrict_tools(TOOLS, status)
    kept_names = {t.name for t in kept}
    leaked = sorted(PROTECTED & kept_names)
    ok = not leaked
    detail = ("未摘掉的危险工具 = %s" % leaked) if leaked else (
        "已摘掉 %d 个危险工具，模型可见 %d 个" % (len(removed), len(kept)))
    return ok, detail


# --------------------------------------------------------------------------
# 2. HITL 正常时，工具一个都不能少
# --------------------------------------------------------------------------
def check_active_keeps_all_tools():
    from A2AServer.v2.hitl_guard import HitlStatus, restrict_tools

    status = HitlStatus(active=True, protected=frozenset(PROTECTED))
    kept, removed = restrict_tools(TOOLS, status)
    ok = len(kept) == len(TOOLS) and not removed
    detail = "保留 %d/%d，摘掉 %d 个（正常路径不该摘任何工具）" % (
        len(kept), len(TOOLS), len(removed))
    return ok, detail


# --------------------------------------------------------------------------
# 3. 判定器不可用 → 拒绝启动
# --------------------------------------------------------------------------
def check_fatal_refuses_to_start():
    from A2AServer.v2.hitl_guard import HitlStatus, HitlUnavailable, restrict_tools

    status = HitlStatus(active=False, reason="判定器不可用", fatal=True)
    try:
        restrict_tools(TOOLS, status)
    except HitlUnavailable:
        return True, "已拒绝启动（HitlUnavailable）"
    except Exception as e:  # noqa: BLE001
        return False, "抛了非预期异常 %s，接口契约应当是 HitlUnavailable" % type(e).__name__
    return False, "未拒绝，工具集照常交给模型了"


# --------------------------------------------------------------------------
# 4. 降级路径的保护集合 == 正常路径
# --------------------------------------------------------------------------
def check_degraded_path_protects_at_least_as_much():
    """失效可以更严，不能更松 —— 这是 fail-closed 的定义。"""
    from A2AServer.v2.hitl_guard import HitlStatus, restrict_tools

    normal = HitlStatus(active=True, protected=frozenset(PROTECTED))
    degraded = HitlStatus(active=False, protected=frozenset(PROTECTED),
                          reason="degraded")
    _, removed_normal = restrict_tools(TOOLS, normal)
    _, removed_degraded = restrict_tools(TOOLS, degraded)
    normal_names = {t.name for t in removed_normal}
    degraded_names = {t.name for t in removed_degraded}
    lost = sorted(normal_names - degraded_names)
    ok = not lost
    detail = ("降级路径比正常路径少拦了 %s" % lost) if lost else (
        "降级路径拦 %d 个 ⊇ 正常路径拦 %d 个" % (
            len(degraded_names), len(normal_names)))
    return ok, detail


# --------------------------------------------------------------------------
# 5. 判定器不依赖 langchain（否则 fail-closed 的前提不成立）
# --------------------------------------------------------------------------
def check_judgement_works_without_langchain():
    """get_interrupt_config 是纯函数 —— langchain 缺失时它仍然算得出来。

    这是「修法 2（危险工具不交给模型）」能成立的前提：
    判定器算不出危险工具集的时候，就只剩 fail-fast 了。
    """
    from A2AServer.v2.dangerous_tools import get_interrupt_config

    src_path = os.path.join(V2_DIR, "dangerous_tools.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    if "langchain" in src.lower():
        return False, "dangerous_tools.py 依赖 langchain —— 判定器不能独立于拦截器存在"

    cfg = get_interrupt_config("health_records",
                               available_tools=["save_health_record",
                                                "get_health_records"])
    ok = "save_health_record" in cfg
    detail = "判定器在无 langchain 环境下算出 %s" % (sorted(cfg) or "空集")
    return ok, detail


# --------------------------------------------------------------------------
# 6. 结构守卫：降级必须可见，而且必须接线
# --------------------------------------------------------------------------
def _hitl_block(src):
    """截出 v2_runtime.py 里的 HITL 段。"""
    start = src.find("# 3. HumanInTheLoopMiddleware")
    end = src.find("# 4. ToolCallLimitMiddleware")
    if start < 0 or end < 0:
        return ""
    return src[start:end]


def _code_only(block):
    """去掉注释行 —— 注释里提到 logger.debug 不算降级静默。"""
    return "\n".join(
        line for line in block.splitlines()
        if not line.strip().startswith("#")
    )


def check_degradation_is_visible():
    """降级不能是 logger.debug —— 默认级别看不见 = 静默失守。"""
    path = os.path.join(V2_DIR, "v2_runtime.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    block = _hitl_block(src)
    if not block:
        return False, "在 v2_runtime.py 里找不到 HITL 段 —— 判定逻辑被挪走了？"

    problems = []
    code = _code_only(block)
    if "logger.debug" in code:
        problems.append("HITL 段仍有 logger.debug —— 静默降级 = 静默失守")
    if "logger.error" not in code:
        problems.append("HITL 段没有 logger.error —— 降级不可见")
    return (not problems), "; ".join(problems) if problems else "降级用 logger.error，可见"


def check_guard_is_wired():
    """控制点必须**接到执行路径上** —— F-007 的教训。"""
    path = os.path.join(V2_DIR, "v2_agent.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    problems = []
    if "restrict_tools" not in src:
        problems.append("v2_agent.py 没有调用 restrict_tools —— 守卫写了但没接线")
    if "hitl_guard" not in src:
        problems.append("v2_agent.py 没有引用 hitl_guard")
    rt_path = os.path.join(V2_DIR, "v2_runtime.py")
    with open(rt_path, encoding="utf-8") as f:
        rt_src = f.read()
    if "hitl_statuses" not in rt_src:
        problems.append("v2_runtime.py 没有记录 HITL 状态 —— v2_agent 无从判断")
    return (not problems), "; ".join(problems) if problems else "守卫已接进 v2_agent"


CHECKS = [
    ("降级时摘掉危险工具", check_degraded_removes_protected_tools),
    ("正常路径不摘工具", check_active_keeps_all_tools),
    ("判定不可用即拒绝启动", check_fatal_refuses_to_start),
    ("降级不多丢保护", check_degraded_path_protects_at_least_as_much),
    ("判定器不依赖 langchain", check_judgement_works_without_langchain),
    ("降级必须可见", check_degradation_is_visible),
    ("守卫必须接线", check_guard_is_wired),
]


# --------------------------------------------------------------------------
# pytest 入口
# --------------------------------------------------------------------------
def test_hitl_fails_closed():
    """pytest 入口：七条不变式全过才算绿。"""
    failures = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, "检查本身抛异常 %s: %s" % (type(e).__name__, e)
        if not ok:
            failures.append("[%s] %s" % (name, detail))
    assert not failures, "HITL fail-closed 不变式被破坏:\n" + "\n".join("  - " + f for f in failures)


# --------------------------------------------------------------------------
# 独立运行入口（CI 门禁用这个）
# --------------------------------------------------------------------------
def main() -> int:
    print("== PHA HITL fail-closed 回归门禁 — 判定不可用时，危险工具不交给模型 ==\n")
    print("  被测: A2AServer.v2.hitl_guard.restrict_tools")
    print("  接线: v2_runtime.get_middlewares → v2_agent._ensure_agent\n")

    failed = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, "检查本身抛异常 %s: %s" % (type(e).__name__, e)
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{mark}] {name:<26} {detail}")

    print()
    if failed:
        print(f"[FAIL] {failed}/{len(CHECKS)} 条不变式被破坏 —— 判定失效时危险操作无人确认执行")
        return 1
    print(f"[OK] {len(CHECKS)}/{len(CHECKS)} 条不变式成立 —— HITL 失效时 fail-closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
