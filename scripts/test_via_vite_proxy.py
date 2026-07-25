"""Test CopilotKit through vite proxy"""
import httpx, json
tok = httpx.post('http://localhost:5174/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']

body = {
    "thread_id": "t1",
    "run_id": "r1",
    "messages": [{"id": "m1", "role": "user", "content": "你好, 我最近血压高"}],
    "tools": [],
    "state": {},
}

with httpx.stream('POST', 'http://localhost:5174/api/copilotkit',
                  json=body,
                  headers={'Authorization': 'Bearer '+tok},
                  timeout=120) as r:
    print('status:', r.status_code)
    print('content-type:', r.headers.get('content-type'))
    n = 0
    for line in r.iter_lines():
        if not line.strip(): continue
        n += 1
        if n <= 6:
            print(line[:200])
    print(f'[total {n} lines]')