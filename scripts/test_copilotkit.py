"""Test /api/copilotkit — should return AG-UI SSE events"""
import httpx, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']

# CopilotKit RunAgentInput format
body = {
    "thread_id": "test",
    "run_id": "test123",
    "messages": [
        {"id": "m1", "role": "user", "content": "你好, 我最近血压偏高"}
    ],
    "tools": [],
    "state": {},
}

with httpx.stream('POST', 'http://localhost:13002/api/copilotkit',
                  json=body,
                  headers={'Authorization': 'Bearer '+tok},
                  timeout=120) as r:
    print('status:', r.status_code)
    print('content-type:', r.headers.get('content-type'))
    for line in r.iter_lines():
        if not line.strip(): continue
        print(line[:300])