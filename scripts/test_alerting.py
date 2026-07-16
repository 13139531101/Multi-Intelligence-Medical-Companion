"""阶段38-3: 性能监控 + 报警 单元测试"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

from A2AServer.v2.alerting import (
    AlertRule, Alert, AlertManager, Severity, get_alert_manager,
)


# ============================================================
# Test 1: AlertRule evaluate
# ============================================================
print("=" * 60)
print("Test 1: AlertRule evaluate (6 个比较符)")
print("=" * 60)
tests = [
    # (op, threshold, value, expected)
    (">",  5,   10, True),   # 10 > 5
    (">",  10,  5,  False),  # 5 > 10
    ("<",  10,  5,  True),   # 5 < 10
    (">=", 10,  10, True),   # 10 >= 10
    ("<=", 10,  5,  True),   # 5 <= 10
    ("==", 10,  10, True),   # 10 == 10
    ("!=", 10,  5,  True),   # 5 != 10
]
for op, threshold, value, expected in tests:
    rule = AlertRule("test", "x", op, threshold, severity=Severity.WARNING)
    got = rule.evaluate(value)
    status = "OK" if got == expected else "FAIL"
    print(f"  {status}: {value} {op} {threshold} → {got} (expected {expected})")
    assert got == expected

print("[PASS] Test 1")


# ============================================================
# Test 2: AlertManager 默认规则
# ============================================================
print()
print("=" * 60)
print("Test 2: AlertManager 默认规则（5 个内置）")
print("=" * 60)
mgr = AlertManager()
rules = mgr.list_rules()
assert len(rules) == 5, f"expected 5 default rules, got {len(rules)}"
for r in rules:
    print(f"  - {r['name']:30s} {r['metric_path']:25s} {r['comparator']} {r['threshold']} ({r['severity']})")
print("[PASS] Test 2")


# ============================================================
# Test 3: AlertManager evaluate（错误率超阈值）
# ============================================================
print()
print("=" * 60)
print("Test 3: AlertManager evaluate（错误率 0.5 → 触发）")
print("=" * 60)

async def test_trigger():
    mgr = AlertManager()
    # 默认空 metrics：error_rate=0, llm.error_rate=0, cache.hit_rate=0 (触发)
    metrics = {
        "request": {"error_rate": 0.5, "p95": 0.5},  # 0.5 > 0.1 → 触发
        "llm": {"error_rate": 0.5},  # 0.5 > 0.2 → 触发
        "cache": {"hit_rate": 10.0},  # 10 < 30 → 触发
    }
    await mgr.evaluate(metrics)
    active = mgr.get_active_alerts()
    print(f"  active alerts: {len(active)}")
    for a in active:
        print(f"    - {a['rule_name']:30s} [{a['severity']:8s}] {a['metric_path']}={a['value']:.4f}")
    # 验证: error_rate_high + error_rate_critical + llm_error_rate_high + cache_hit_rate_low = 4
    assert len(active) == 4, f"expected 4 alerts, got {len(active)}"
    stats = mgr.get_stats()
    assert stats["total_triggered"] == 4
    print(f"  stats: {stats}")

asyncio.run(test_trigger())
print("[PASS] Test 3")


# ============================================================
# Test 4: AlertManager resolve（指标恢复后解除）
# ============================================================
print()
print("=" * 60)
print("Test 4: AlertManager resolve（指标恢复 → 解除）")
print("=" * 60)

async def test_resolve():
    mgr = AlertManager()
    # 1. 触发
    bad_metrics = {
        "request": {"error_rate": 0.5, "p95": 0.5},
        "llm": {"error_rate": 0.5},
        "cache": {"hit_rate": 10.0},
    }
    await mgr.evaluate(bad_metrics)
    assert len(mgr.get_active_alerts()) == 4

    # 2. 恢复
    good_metrics = {
        "request": {"error_rate": 0.01, "p95": 0.5},
        "llm": {"error_rate": 0.01},
        "cache": {"hit_rate": 80.0},
    }
    await mgr.evaluate(good_metrics)
    assert len(mgr.get_active_alerts()) == 0, f"expected 0, got {len(mgr.get_active_alerts())}"
    stats = mgr.get_stats()
    print(f"  stats after resolve: {stats}")
    assert stats["total_resolved"] == 4

asyncio.run(test_resolve())
print("[PASS] Test 4")


# ============================================================
# Test 5: Alert history
# ============================================================
print()
print("=" * 60)
print("Test 5: Alert history (max 100)")
print("=" * 60)
mgr = AlertManager()
for i in range(5):
    asyncio.run(mgr.evaluate({
        "request": {"error_rate": 0.5},
        "llm": {"error_rate": 0.0},
        "cache": {"hit_rate": 80.0},
    }))
history = mgr.get_history(limit=10)
print(f"  history size: {len(history)}")
print(f"  first 2 alerts:")
for a in history[:2]:
    print(f"    - {a['rule_name']} triggered_at={a['triggered_at']:.1f}")
print("[PASS] Test 5")


# ============================================================
# Test 6: Custom rule add/remove
# ============================================================
print()
print("=" * 60)
print("Test 6: Custom rule add/remove")
print("=" * 60)
mgr = AlertManager()
mgr.add_rule(AlertRule(
    name="custom_test",
    metric_path="custom.value",
    comparator=">",
    threshold=100.0,
    severity=Severity.CRITICAL,
    description="Custom alert for testing",
))
assert any(r["name"] == "custom_test" for r in mgr.list_rules())
print(f"  added 'custom_test' rule")

mgr.remove_rule("custom_test")
assert not any(r["name"] == "custom_test" for r in mgr.list_rules())
print(f"  removed 'custom_test' rule")
print("[PASS] Test 6")


# ============================================================
# Test 7: Custom handler (webhook 模拟)
# ============================================================
print()
print("=" * 60)
print("Test 7: Custom handler (webhook 模拟)")
print("=" * 60)

async def test_handler():
    mgr = AlertManager()
    captured = []
    def my_handler(alert):
        captured.append(alert.to_dict())
    mgr.add_handler(my_handler)
    await mgr.evaluate({
        "request": {"error_rate": 0.5},
        "llm": {"error_rate": 0.0},
        "cache": {"hit_rate": 80.0},
    })
    print(f"  captured {len(captured)} alerts via handler")
    # 错误率 0.5 同时触发 high(>0.1) + critical(>0.3)
    assert len(captured) == 2
    rule_names = {a["rule_name"] for a in captured}
    assert "request_error_rate_high" in rule_names
    assert "request_error_rate_critical" in rule_names

asyncio.run(test_handler())
print("[PASS] Test 7")


print()
print("=" * 60)
print("[ALL PASS] 7/7 tests")
print("=" * 60)