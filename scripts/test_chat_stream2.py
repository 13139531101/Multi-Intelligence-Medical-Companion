"""Test /v2/chat/stream with a different question"""
import httpx, json, time
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']

# Try the explicit way: force agent
for msg, agent in [
    ('查健康档案', 'health_records'),
    ('查吃药提醒', 'medication_reminder'),
    ('我最近血压高怎么办?', 'health_advisor'),
    ('看下我的健康档案', 'health_records'),
]:
    print(f'\n=== msg="{msg}" agent={agent} ===')
    with httpx.stream('POST', 'http://localhost:13002/v2/chat/stream',
                      json={'message': msg, 'metadata': {'selected_agent': agent}},
                      headers={'Authorization': 'Bearer '+tok},
                      timeout=60) as r:
        for line in r.iter_lines():
            if not line.strip(): continue
            print(line[:250])