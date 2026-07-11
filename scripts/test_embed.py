import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['EMBEDDING_MODEL'] = 'text-embedding-v3'
os.environ['DASHSCOPE_API_KEY'] = 'sk-2917df2994074695b7b741ffb6382a3b'
os.environ['EMBEDDING_API_BASE'] = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
os.environ['EMBEDDING_DIM'] = '384'

import sys
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2.rag import EmbeddingClient
import asyncio

async def main():
    c = EmbeddingClient()
    print(f'api_key set: {bool(c._api_key)}, model: {c._model}, dim: {c._dim}')
    try:
        r = await c.embed(["测试文本"])
        print(f'OK, dim={len(r[0])}')
        print(f'first 3: {r[0][:3]}')
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {e}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'response: {e.response.text[:500]}')

asyncio.run(main())
