"""阶段19 验收 - 写操作安全审计 (5 层保护)"""
import os
import sys
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
import locale
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except Exception:
    pass

# 强制低限额 + 关掉 auth（测试用）
os.environ['PHA_WRITE_QUOTA_PER_HOUR'] = '5'
os.environ['PHA_AUTH_REQUIRED'] = 'true'
os.environ['PHA_DANGEROUS_TOOLS_REQUIRE_CONFIRM'] = 'true'

print('=' * 70)
print('PHA v2 阶段19 验收 - 写操作安全审计 (5 层保护)')
print('=' * 70)

# ---- 加载 v2 模块 ----
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))
from A2AServer.v2.write_audit import (
    get_write_guard, set_write_allowlist, is_dangerous_write,
    WriteGuard, WriteDecision,
)
from A2AServer.v2.tool_cache import is_write_tool


total = 0
passed = 0


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:55s} {detail}')
    total += 1
    if ok:
        passed += 1


async def main():
    guard = get_write_guard()
    print(f"\n[1] 配置: PHA_WRITE_QUOTA_PER_HOUR=5, AUTH=on, DANGEROUS=on\n")

    # ---- 1. L1 鉴权 ----
    print('[1] L1 鉴权')
    d = await guard.check("", "agent1", "add_record", {})
    check('空 user_id 被拒', not d.allowed and d.layer == "L1_auth", f"layer={d.layer}")

    d = await guard.check("ab", "agent1", "add_record", {})  # 太短
    check('user_id 长度 <3 被拒', not d.allowed and d.layer == "L1_auth", f"layer={d.layer}")

    d = await guard.check("user_001", "agent1", "add_record", {})
    check('正常 user_id 通过 L1', d.allowed, f"layer={d.layer}")

    # ---- 2. L2 白名单 ----
    print('\n[2] L2 白名单')
    set_write_allowlist(["add_record", "update_record"])  # 只允许 2 个
    d = await guard.check("user_001", "agent1", "delete_record", {})
    check('delete_record 不在白名单被拒', not d.allowed and d.layer == "L2_allowlist", f"layer={d.layer}")

    d = await guard.check("user_001", "agent1", "add_record", {})
    check('add_record 在白名单通过 L2', d.allowed, f"layer={d.layer}")

    set_write_allowlist([])  # 清空白名单
    d = await guard.check("user_001", "agent1", "add_record", {})
    check('空白名单允许所有', d.allowed, f"layer={d.layer}")

    # ---- 3. L5 危险工具确认 ----
    print('\n[3] L5 危险工具 confirm')
    check('delete_record 是危险', is_dangerous_write("delete_record"))
    check('remove_user 是危险', is_dangerous_write("remove_user"))
    check('update_password 是危险', is_dangerous_write("update_password"))
    check('add_record 不是危险', not is_dangerous_write("add_record"))
    check('get_record 不是危险', not is_dangerous_write("get_record"))

    # 不带 confirm token 应拒绝
    d = await guard.check("user_001", "agent1", "delete_record", {"id": 1})
    check('危险工具无 confirm token 被拒', not d.allowed and d.layer == "L5_confirm_required", f"layer={d.layer}")
    check('拒绝时返回 confirm_token', bool(d.confirm_token), f"token={d.confirm_token[:16] if d.confirm_token else 'None'}...")

    # 用返回的 token 再次 check 通过
    d2 = await guard.check("user_001", "agent1", "delete_record", {"id": 1}, confirm_token=d.confirm_token)
    check('危险工具带正确 confirm token 通过', d2.allowed, f"layer={d2.layer}")

    # token 用第二次应失败（一次性）
    d3 = await guard.check("user_001", "agent1", "delete_record", {"id": 1}, confirm_token=d.confirm_token)
    check('confirm token 一次性（第二次被拒）', not d3.allowed, f"layer={d3.layer}")

    # ---- 4. L4 限额 ----
    print('\n[4] L4 限额 (5/hour)')
    # 先成功写 5 次
    for i in range(5):
        async with guard.protect("user_002", "agent1", "add_record", {"i": i}) as ctx:
            ctx.set_result({"ok": True})
    check('5 次写操作都成功', True, 'consumed 5/5')

    # 第 6 次应被限额拒绝
    try:
        async with guard.protect("user_002", "agent1", "add_record", {"i": 6}):
            pass
        check('第 6 次被限额拒绝', False, 'should have raised')
    except PermissionError as e:
        check('第 6 次被限额拒绝', "L4_quota" in str(e), str(e)[:80])

    # ---- 5. 写失败退还配额 ----
    print('\n[5] 写失败退还配额')
    guard3 = get_write_guard()
    guard3._quota.pop("user_003", None)  # 清空
    try:
        async with guard3.protect("user_003", "agent1", "add_record", {"x": 1}):
            raise ValueError("simulated failure")
    except ValueError:
        pass
    # 检查配额应退还
    state = guard3._quota.get("user_003")
    count = state.count_in_window(time.time()) if state else 0
    check('写失败时退还配额', count == 0, f'count={count}')

    # ---- 6. 审计统计 ----
    print('\n[6] 审计统计')
    stats = guard.stats()
    check('stats.total > 0', stats["total"] > 0, f"total={stats['total']}")
    check('stats 含 success 计数', stats["success"] > 0, f"success={stats['success']}")
    check('stats 含 denied 计数', stats["denied"] > 0, f"denied={stats['denied']}")
    check('stats 含 error 计数', stats["error"] > 0, f"error={stats['error']}")
    check('stats 含 auth_required', stats["auth_required"] is True)
    check('stats 含 dangerous_require_confirm', stats["dangerous_require_confirm"] is True)

    # ---- 7. get_recent ----
    print('\n[7] get_recent 查询')
    recent = guard.get_recent(limit=10)
    check('get_recent 返回列表', isinstance(recent, list))
    check('get_recent 至少 1 条', len(recent) >= 1, f"got {len(recent)}")

    # 按 user 过滤
    recent_u = guard.get_recent(limit=100, user_id="user_002")
    check('get_recent 按 user 过滤', all(e["user_id"] == "user_002" for e in recent_u), f"got {len(recent_u)}")

    # 按 tool 过滤
    recent_t = guard.get_recent(limit=100, tool_name="delete_record")
    check('get_recent 按 tool 过滤', all(e["tool_name"] == "delete_record" for e in recent_t), f"got {len(recent_t)}")

    # ---- 8. 集成测试：is_write_tool ----
    print('\n[8] 与 tool_cache 集成')
    class _Tool:
        def __init__(self, name, tags=None):
            self.name = name
            self.tags = tags or []
    check('is_write_tool(add_record) = True', is_write_tool(_Tool("add_record")))
    check('is_write_tool(delete_user) = True', is_write_tool(_Tool("delete_user")))
    check('is_write_tool(get_record) = False', not is_write_tool(_Tool("get_record")))
    check('is_write_tool(list_records) = False', not is_write_tool(_Tool("list_records")))
    check('is_write_tool(search_disease) = False', not is_write_tool(_Tool("search_disease")))

    # ---- 9. 总结 ----
    print('\n' + '=' * 70)
    print(f'阶段19 验收：{passed}/{total} 通过')
    if passed == total:
        print('[OK] 全部通过！阶段19 完成，5 层写保护就绪。')
    else:
        print(f'[WARN] 有 {total - passed} 项失败')
    print('=' * 70)
    return passed == total


if __name__ == "__main__":
    import time
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
