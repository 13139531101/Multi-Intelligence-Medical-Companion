"""Test /v2/chat/stream with longer timeout"""
import httpx, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}).json()['access_token']
with httpx.stream('POST', 'http://localhost:13002/v2/chat/stream',
                  json={'message': '你好, 我最近血压高'},
                  headers={'Authorization': 'Bearer '+tok},
                  timeout=120) as r:
    print('status:', r.status_code, 'content-type:', r.headers.get('content-type'))
    lines = []
    for line in r.iter_lines():
        if not line.strip(): continue
        lines.append(line)
        print(line[:400])
    print(f'\n[total lines: {len(lines)}]')