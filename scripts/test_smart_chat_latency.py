"""测 v2 smart_chat 实际 LLM 回答延迟"""
import httpx
import time
import sys
import os

# 强制 UTF-8 输出
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

t = time.time()
r = httpx.post('http://localhost:13002/smart_chat', json={'message': '你好'}, timeout=120)
print(f'[0.0s] POST /smart_chat: status={r.status_code}')
conv_id = r.json().get('conversation_id')
print(f'       conversation_id: {conv_id}')

for i in range(40):
    time.sleep(1)
    try:
        r = httpx.post('http://localhost:13002/message/list',
                       json={'params': {'conversation_id': conv_id}}, timeout=10)
        msgs = r.json().get('result', [])
        if msgs and any(m.get('parts', [{}])[0].get('text', '').strip() for m in msgs):
            elapsed = time.time() - t
            first = msgs[0]
            text = first.get('parts', [{}])[0].get('text', '')
            print(f'[{elapsed:.1f}s] got msg! text_len={len(text)}')
            print(f'         preview: {text[:100]}')
            break
        else:
            print(f'[{i+1}s] msgs={len(msgs)}, waiting...')
    except Exception as e:
        print(f'[{i+1}s] error: {e}')
else:
    print('TIMEOUT: 40 秒还没拿到 LLM 回答')