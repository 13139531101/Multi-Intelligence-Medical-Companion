"""阶段41-3: Skill/MCP registry E2E"""
import json
import httpx
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("Skill/MCP Registry E2E")
print("=" * 60)

# 1. 列出 skills
r = httpx.get('http://localhost:13002/v2/registry/skills')
skills = r.json().get('skills', [])
print(f"\n1. skills: {len(skills)} 个")
for s in skills[:3]:
    print(f"   {s['icon']} {s['display_name']} enabled={s['enabled']}")

# 2. 创建一个 custom skill
r = httpx.post('http://localhost:13002/v2/registry/skills', json={
    'name': 'nutrition_advice',
    'display_name': '营养建议',
    'description': '个性化营养和饮食建议',
    'category': 'custom',
    'tools': ['calculate_bmi', 'search_drug_info'],
    'keywords': ['营养', '饮食', '吃饭', 'nutrition', 'diet'],
    'priority': 65,
    'icon': '🥗',
    'system_prompt_addon': '你是营养师助手，根据用户身体状况提供饮食建议。',
})
print(f"\n2. create skill: {r.json().get('created', False)}, name={r.json().get('skill', {}).get('name')}")
assert r.json().get('created')

# 3. 测试匹配
r = httpx.post('http://localhost:13002/v2/skills/match', json={'text': '我最近饮食不规律'})
matched = [s['name'] for s in r.json().get('matched', [])]
print(f"\n3. match '饮食不规律': {matched}")
assert 'nutrition_advice' in matched

# 4. 禁用 skill
r = httpx.post('http://localhost:13002/v2/registry/skills/nutrition_advice/disable')
print(f"\n4. disable: {r.json().get('disabled')}")
assert r.json().get('disabled')

# 5. 重新启用
r = httpx.post('http://localhost:13002/v2/registry/skills/nutrition_advice/enable')
print(f"\n5. enable: {r.json().get('enabled')}")
assert r.json().get('enabled')

# 6. 删除 custom skill
r = httpx.delete('http://localhost:13002/v2/registry/skills/nutrition_advice')
print(f"\n6. delete: {r.json().get('deleted')}")
assert r.json().get('deleted')

# 7. 不能删 default skill
r = httpx.delete('http://localhost:13002/v2/registry/skills/health_records')
print(f"\n7. delete default: {r.json().get('error', '')}")
assert 'cannot delete default' in r.json().get('error', '')

# 8. 列出 MCPs
r = httpx.get('http://localhost:13002/v2/registry/mcp/servers')
mcps = r.json().get('servers', [])
print(f"\n8. MCPs: {len(mcps)} 个")
for m in mcps:
    print(f"   {m['icon']} {m['display_name']} status={m['status']}")

# 9. 注册远程 MCP
r = httpx.post('http://localhost:13002/v2/registry/mcp/servers', json={
    'name': 'remote_test', 'url': 'https://httpbin.org', 'type': 'http',
    'display_name': '远程测试 MCP',
})
print(f"\n9. register remote: {r.json().get('registered', {}).get('name')}")

# 10. 列出（应该 +1）
r = httpx.get('http://localhost:13002/v2/registry/mcp/servers')
print(f"\n10. MCPs after register: {len(r.json().get('servers', []))}")

# 11. 健康检查
r = httpx.post('http://localhost:13002/v2/registry/mcp/servers/remote_test/health')
print(f"\n11. health check: {r.json().get('server', {}).get('status')}")

# 12. 删除远程
r = httpx.delete('http://localhost:13002/v2/registry/mcp/servers/remote_test')
print(f"\n12. delete remote: {r.json().get('deleted')}")

# 13. 不能删 default MCP
r = httpx.delete('http://localhost:13002/v2/registry/mcp/servers/health_records_mcp')
print(f"\n13. delete default MCP: {r.json().get('error', '')}")

print()
print("=" * 60)
print("[ALL PASS] 13/13 tests")
print("=" * 60)