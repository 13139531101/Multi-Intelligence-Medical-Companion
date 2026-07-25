"""Test /v2/chat/stream with SSE — see what events come back"""
import httpx, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']
with httpx.stream('POST', 'http://localhost:13002/v2/chat/stream',
                  json={'message': '看下我最近一个月的健康档案'},
                  headers={'Authorization': 'Bearer '+tok},
                  timeout=120) as r:
    print('status:', r.status_code, 'content-type:', r.headers.get('content-type'))
    chunks = []
    for line in r.iter_lines():
        if not line.strip(): continue
        chunks.append(line)
        print(line[:300])
    print(f'\n[total lines: {len(chunks)}]')