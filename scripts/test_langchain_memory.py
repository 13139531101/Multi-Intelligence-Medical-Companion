"""阶段40-1: PHA LangChain 风格记忆测试
- PHAHealthMemory: 医疗 buffer + 重要性 + tag
- PHAEntityMemory: 医疗实体提取
- PHALayeredMemory: 三级缓存（L1内存 / L2 Redis / L3 PG）
"""
import sys
import os
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))


# ============================================================
# Test 1: PHAHealthMemory 基本 CRUD
# ============================================================
print("=" * 60)
print("Test 1: PHAHealthMemory 基本 CRUD")
print("=" * 60)

from A2AServer.v2.langchain_memory import PHAHealthMemory
mem = PHAHealthMemory(agent_id="health_advisor", user_id="u1", max_messages=10)
mem.save_context({"input": "你好"}, {"output": "您好！"})
mem.save_context({"input": "我头疼发烧"}, {"output": "建议多喝水"})
mem.save_context({"input": "今天天气不错"}, {"output": "是的"})

vars = mem.load_memory_variables({})
print(f"  history lines: {len(vars['history'].split(chr(10)))}")
print(f"  first line: {vars['history'].split(chr(10))[0][:50]}")
assert "头疼发烧" in vars["history"] or "建议多喝水" in vars["history"]
print(f"  stats: {mem.get_stats()}")
print("[PASS] Test 1")


# ============================================================
# Test 2: 重要性评分 + tag 提取
# ============================================================
print()
print("=" * 60)
print("Test 2: 重要性评分 + 医疗 tag 提取")
print("=" * 60)

mem.clear()
# 医疗对话（高 importance）
mem.save_context(
    {"input": "我有糖尿病，吃二甲双胍，最近血压 140/90"},
    {"output": "建议控制饮食，按时服药"}
)
# 普通对话（低 importance）
mem.save_context(
    {"input": "今天天气怎么样"},
    {"output": "晴天"}
)

items = list(mem._items)
print(f"  items count: {len(items)}")
for it in items:
    print(f"    [{it.importance:.2f}] {it.tags} {it.content[:30]}")

# 验证：医疗对话 importance 应该 > 0.5
medical_items = [it for it in items if "糖尿病" in it.content or "二甲双胍" in it.content]
assert len(medical_items) > 0
assert medical_items[0].importance > 0.5
# 验证 tags
assert "chronic_disease" in medical_items[0].tags
assert "medication" in medical_items[0].tags or "vital_sign" in medical_items[0].tags
print(f"  ✓ medical importance: {medical_items[0].importance}")
print(f"  ✓ medical tags: {medical_items[0].tags}")
print("[PASS] Test 2")


# ============================================================
# Test 3: 淘汰机制（超 max_messages）
# ============================================================
print()
print("=" * 60)
print("Test 3: 淘汰机制（保留 importance 高的）")
print("=" * 60)

mem = PHAHealthMemory(max_messages=3, importance_threshold=0.3)
# 加 10 条
for i in range(10):
    is_medical = (i % 2 == 0)
    text = f"我有糖尿病，血糖{i}" if is_medical else f"普通对话{i}"
    mem.save_context({"input": text}, {"output": f"回复{i}"})

vars = mem.load_memory_variables({})
lines = vars["history"].split("\n")
print(f"  returned lines: {len(lines)}")
print(f"  first 3:")
for line in lines[:3]:
    print(f"    {line[:60]}")
assert len(lines) <= 3  # max_messages=3
# 验证：剩下的都是 medical
for line in lines:
    if line.startswith("user:"):
        # 普通对话应该被淘汰
        assert "糖尿病" in line or "血糖" in line, f"普通对话没被淘汰: {line}"
print("[PASS] Test 3")


# ============================================================
# Test 4: PHAEntityMemory 实体提取
# ============================================================
print()
print("=" * 60)
print("Test 4: PHAEntityMemory 实体提取")
print("=" * 60)

from A2AServer.v2.langchain_memory import PHAEntityMemory
emem = PHAEntityMemory(agent_id="health_advisor", user_id="u1")
emem.save_context(
    {"input": "我有糖尿病，吃二甲双胍，最近血压 140/90"},
    {"output": "建议低糖饮食"}
)
emem.save_context(
    {"input": "我对青霉素过敏"},
    {"output": "记录在案"}
)

entities = emem.get_entities()
print(f"  entities found: {len(entities)}")
for e in entities:
    print(f"    {e.entity_type:15s} {e.name:10s} value={e.value!r} mentions={e.mention_count}")

# 验证
names = {e.name for e in entities}
assert "糖尿病" in names
assert "二甲双胍" in names
assert "血压" in names
# "青霉素过敏" or "青霉素"
assert any("青霉素" in n for n in names)
# 验证值
bp_entity = next(e for e in entities if e.name == "血压")
assert bp_entity.value == "140/90"
print(f"  ✓ BP value: {bp_entity.value}")
print("[PASS] Test 4")


# ============================================================
# Test 5: 跨消息实体累积
# ============================================================
print()
print("=" * 60)
print("Test 5: 同一实体多次提及（mention_count 累加）")
print("=" * 60)

emem.clear()
for _ in range(5):
    emem.save_context({"input": "糖尿病怎么控制"}, {"output": "..."})

diabetes = next(e for e in emem.get_entities() if e.name == "糖尿病")
print(f"  糖尿病 mention_count: {diabetes.mention_count}")
assert diabetes.mention_count == 5
print("[PASS] Test 5")


# ============================================================
# Test 6: langchain 兼容接口
# ============================================================
print()
print("=" * 60)
print("Test 6: langchain 兼容接口（BaseChatMemory）")
print("=" * 60)

mem = PHAHealthMemory(agent_id="test", user_id="test")
# 这些是 langchain 强制接口
assert hasattr(mem, "memory_variables")
assert hasattr(mem, "load_memory_variables")
assert hasattr(mem, "save_context")
assert hasattr(mem, "clear")
# 验证接口
assert "history" in mem.memory_variables
mem.save_context({"input": "test"}, {"output": "ok"})
v = mem.load_memory_variables({})
assert "history" in v
print(f"  ✓ memory_variables: {mem.memory_variables}")
print(f"  ✓ save_context / load_memory_variables 工作正常")
print(f"  ✓ langchain 兼容接口全部实现")
print("[PASS] Test 6")


# ============================================================
# Test 7: PHALayeredMemory L1 only（无 Redis/PG）
# ============================================================
print()
print("=" * 60)
print("Test 7: PHALayeredMemory L1 内存模式（无 Redis/PG）")
print("=" * 60)

from A2AServer.v2.langchain_memory import PHALayeredMemory
lm = PHALayeredMemory(agent_id="ha", user_id="u1")  # 没 redis_url/pg_url
lm.save_context({"input": "你好"}, {"output": "您好"})
lm.save_context({"input": "头疼"}, {"output": "多休息"})
v = lm.load_memory_variables({})
print(f"  history: {len(v['history'])} items")
# 2 次 save_context × 2 (user+ai) = 4
assert len(v["history"]) == 4
print(f"  stats: {lm.get_stats()}")
assert lm.get_stats()["l1_hits"] == 1
print("[PASS] Test 7")


# ============================================================
# Test 8: PHALayeredMemory L2 Redis 模式
# ============================================================
print()
print("=" * 60)
print("Test 8: PHALayeredMemory L2 Redis 模式")
print("=" * 60)

import os
# 默认检测常见 Redis 端口
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
lm = PHALayeredMemory(agent_id="ha2", user_id="u2", redis_url=redis_url)
stats = lm.get_stats()
print(f"  l2_enabled: {stats['l2_enabled']}")
if stats['l2_enabled']:
    # 写一条
    lm.save_context({"input": "redis 测试"}, {"output": "ok"})
    # 清空 L1 模拟冷启动
    lm._l1.clear()
    # 重新加载（应该从 L2 命中）
    v = lm.load_memory_variables({})
    print(f"  L2 hit: {lm.get_stats()['l2_hits']}")
    assert lm.get_stats()["l2_hits"] == 1
    print(f"  ✓ L2 Redis 命中")
    print("[PASS] Test 8")
else:
    print("  [SKIP] Redis not available")


# ============================================================
# Test 9: 工厂函数
# ============================================================
print()
print("=" * 60)
print("Test 9: 工厂函数")
print("=" * 60)

from A2AServer.v2.langchain_memory import (
    create_health_memory, create_entity_memory, create_layered_memory
)
m1 = create_health_memory()
m2 = create_entity_memory()
m3 = create_layered_memory()
print(f"  PHAHealthMemory: {type(m1).__name__}")
print(f"  PHAEntityMemory: {type(m2).__name__}")
print(f"  PHALayeredMemory: {type(m3).__name__}")
assert type(m1).__name__ == "PHAHealthMemory"
assert type(m2).__name__ == "PHAEntityMemory"
assert type(m3).__name__ == "PHALayeredMemory"
print("[PASS] Test 9")


print()
print("=" * 60)
print("[ALL PASS] 9/9 tests")
print("=" * 60)