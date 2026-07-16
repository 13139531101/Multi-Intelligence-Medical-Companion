"""阶段41: 端到端 dashboard 测试"""
import sys
import json
import httpx
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("PHA v2 Dashboard 端到端测试")
print("=" * 60)

# Test skills
r = httpx.get('http://localhost:13002/v2/skills')
print(f"\n[/v2/skills] status={r.status_code}, count={len(r.json().get('skills', []))}")
for s in r.json().get('skills', [])[:3]:
    print(f"  - {s['icon']} {s['display_name']} (priority={s['priority']})")

# Test tools
r = httpx.get('http://localhost:13002/v2/tools')
print(f"\n[/v2/tools] status={r.status_code}, count={len(r.json().get('tools', []))}")
for t in r.json().get('tools', [])[:3]:
    print(f"  - {t['name']} ({t['category']})")

# Test MCP
r = httpx.get('http://localhost:13002/v2/mcp/servers')
print(f"\n[/v2/mcp/servers] status={r.status_code}, count={len(r.json().get('servers', []))}")
for s in r.json().get('servers', []):
    print(f"  - {s['icon']} {s['display_name']} [{s['status']}]")

# Test skill match
r = httpx.post('http://localhost:13002/v2/skills/match', json={'text': '我最近血压高，吃什么药'})
print(f"\n[/v2/skills/match] matched:")
for s in r.json().get('matched', []):
    print(f"  - {s['display_name']}")

# Test tool call
r = httpx.post('http://localhost:13002/v2/tools/call', json={'name': 'calculate_bmi', 'args': {'weight_kg': 70, 'height_cm': 175}})
data = r.json()
print(f"\n[/v2/tools/call BMI] success={data.get('success')}")
if data.get('success'):
    result = json.loads(data['result'])
    print(f"  BMI: {result['bmi']} ({result['category']})")

# Test MCP call
r = httpx.post('http://localhost:13002/v2/mcp/call/health_records_mcp',
               json={'method': 'search_health_records', 'args': {'user_id': 'demo'}})
data = r.json()
print(f"\n[/v2/mcp/call] success={data.get('success')}, latency={data.get('latency_ms', 0):.1f}ms")
print(f"  call_id: {data.get('call_id')}")

# Test dashboard
r = httpx.get('http://localhost:13002/test/dashboard.html')
print(f"\n[/test/dashboard.html] status={r.status_code}, size={len(r.text)}")

print()
print("=" * 60)
print("打开浏览器: http://localhost:13002/test/dashboard.html")
print("=" * 60)