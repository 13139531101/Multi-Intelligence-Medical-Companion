"""检查 middleware 是否真生效."""
import sys, os
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')

from A2AServer.v2.v2_runtime import (
    get_runtime, _LANGCHAIN_V2_OK,
    SummarizationMiddleware, PIIMiddleware
)
print('_LANGCHAIN_V2_OK =', _LANGCHAIN_V2_OK)
print('SummarizationMiddleware =', SummarizationMiddleware)
print('PIIMiddleware =', PIIMiddleware)
print()

r = get_runtime()
print('runtime.available =', r.available)
mws = r.get_middlewares(model='deepseek-chat')
print(f'get_middlewares() returned {len(mws)} middleware instances:')
for m in mws:
    print(f'  - {type(m).__name__}: {m}')
