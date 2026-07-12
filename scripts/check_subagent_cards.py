"""阶段29: 验证 4 sub-agent card 可访问"""
import httpx

urls = [
    ('health_records', 'http://localhost:10010/.well-known/agent.json'),
    ('health_advisor', 'http://localhost:10011/.well-known/agent.json'),
    ('medication_reminder', 'http://localhost:10012/.well-known/agent.json'),
    ('visit_summary', 'http://localhost:10013/.well-known/agent.json'),
]

for name, url in urls:
    try:
        r = httpx.get(url, timeout=3)
        data = r.json()
        print(f"{name}: HTTP {r.status_code} | name={data.get('name','?')} | description={data.get('description','?')[:50]}")
    except Exception as e:
        print(f"{name}: FAIL - {str(e)[:80]}")