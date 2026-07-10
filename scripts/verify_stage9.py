"""阶段9 验收 - 写操作白名单（避免工具缓存副作用）"""
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('PHA v2 阶段9 验收 - 写操作白名单')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. is_write_tool 单元测试 ----
print('\n[1] is_write_tool 单元测试')
from A2AServer.v2.tool_cache import is_write_tool


class MockTool:
    def __init__(self, name, tags=None):
        self.name = name
        self.tags = tags or []


# 写操作（按命名）
total += 1
if check('add_ 前缀识别为写', is_write_tool(MockTool("add_medication_reminder"))):
    passed += 1
total += 1
if check('delete_ 前缀识别为写', is_write_tool(MockTool("delete_record"))):
    passed += 1
total += 1
if check('send_ 前缀识别为写', is_write_tool(MockTool("send_notification"))):
    passed += 1
total += 1
if check('update_ 前缀识别为写', is_write_tool(MockTool("update_health_data"))):
    passed += 1

# 读操作（按命名）
total += 1
if check('get_ 前缀识别为读', not is_write_tool(MockTool("get_health_records"))):
    passed += 1
total += 1
if check('search_ 前缀识别为读', not is_write_tool(MockTool("search_symptom_info"))):
    passed += 1
total += 1
if check('analyze_ 前缀识别为读', not is_write_tool(MockTool("analyze_health_trends"))):
    passed += 1

# 显式标签
total += 1
if check('tags=[write] 显式标记为写', is_write_tool(MockTool("foo", tags=["write"]))):
    passed += 1
total += 1
if check('tags=[read-only] 显式标记为读', not is_write_tool(MockTool("bar", tags=["read-only"]))):
    passed += 1
total += 1
if check('tags=[idempotent] 显式标记为读', not is_write_tool(MockTool("baz", tags=["idempotent"]))):
    passed += 1

# 保守：未知按写
total += 1
if check('未知工具名按写处理（保守）', is_write_tool(MockTool("xyz123"))):
    passed += 1

# 标签覆盖命名
total += 1
if check(
    'tags=[read-only] 覆盖 add_ 前缀',
    not is_write_tool(MockTool("add_record", tags=["read-only"])),
):
    passed += 1

# ---- 2. wrap_tool_with_cache 集成测试 ----
print('\n[2] wrap_tool_with_cache 集成测试')
from A2AServer.v2.tool_cache import (
    ToolCallCache,
    get_tool_cache,
    wrap_tool_with_cache,
)


class FakeTool:
    def __init__(self, name, tags=None):
        self.name = name
        self.tags = tags or []
        self._call_count = 0
        self._last_kwargs = None

    def _run(self, **kwargs):
        self._call_count += 1
        self._last_kwargs = kwargs
        return f"result_{self._call_count}"

    async def _arun(self, **kwargs):
        self._call_count += 1
        self._last_kwargs = kwargs
        return f"result_{self._call_count}"


# 清空缓存
get_tool_cache().clear()

# 写操作工具：应该不被缓存
write_tool = FakeTool("add_reminder", tags=["write"])
wrapped_write = wrap_tool_with_cache(write_tool, use_cache=True)
total += 1
if check('写操作工具不被 wrap（保持原方法）', wrapped_write._run is write_tool._run):
    passed += 1

# 读操作工具：应该被缓存
read_tool = FakeTool("search_info", tags=["read-only"])
wrapped_read = wrap_tool_with_cache(read_tool, use_cache=True)
total += 1
if check('读操作工具被 wrap（方法被替换）', wrapped_read._run is not read_tool._run):
    passed += 1

# 读操作调两次：第二次命中缓存，call_count=1
r1 = wrapped_read._run(query="test")
total += 1
if check('读操作第 1 次调用：call_count=1', wrapped_read._call_count == 1, f'call_count={wrapped_read._call_count}'):
    passed += 1
r2 = wrapped_read._run(query="test")
total += 1
if check('读操作第 2 次调用：call_count=1（命中缓存）', wrapped_read._call_count == 1, f'call_count={wrapped_read._call_count}'):
    passed += 1
total += 1
if check('两次返回相同（缓存命中）', r1 == r2, f'r1={r1}, r2={r2}'):
    passed += 1

# 写操作调两次：call_count=2（每次都执行）
write_tool2 = FakeTool("send_email", tags=["side-effect"])
wrapped_write2 = wrap_tool_with_cache(write_tool2, use_cache=True)
wrapped_write2._run(to="u1", body="hi")
wrapped_write2._run(to="u1", body="hi")
total += 1
if check('写操作调两次：call_count=2（不被缓存）', write_tool2._call_count == 2, f'call_count={write_tool2._call_count}'):
    passed += 1

# force_cache=True 强制缓存
write_tool3 = FakeTool("add_record", tags=["write"])
write_tool3.force_cache = True
wrapped_force = wrap_tool_with_cache(write_tool3, use_cache=True)
total += 1
if check('force_cache=True 即使写操作也缓存', wrapped_force._run is not write_tool3._run):
    passed += 1
wrapped_force._run(id=1)
wrapped_force._run(id=1)
total += 1
if check('force_cache 第二次命中：call_count=1', write_tool3._call_count == 1, f'call_count={write_tool3._call_count}'):
    passed += 1

# ---- 3. 实际工具扫描（看哪些被识别为写）----
print('\n[3] PHA 实际工具的写/读分类')
from A2AServer.v2.mcp_tool_adapter import load_mcp_tools

for agent_name in ["health_advisor", "health_records", "medication_reminder", "visit_summary"]:
    tools = load_mcp_tools(agent_name)
    write_tools = [t.name for t in tools if is_write_tool(t)]
    read_tools = [t.name for t in tools if not is_write_tool(t)]
    print(f"  [{agent_name}] 读 {len(read_tools)} / 写 {len(write_tools)}")
    if write_tools:
        print(f"    写: {write_tools[:5]}{'...' if len(write_tools)>5 else ''}")
    total += 1
    if check(f"{agent_name} 工具加载成功", len(tools) > 0):
        passed += 1

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段9 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段9 完成，写操作白名单就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
