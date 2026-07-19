"""Test middleware with chat_model."""
import sys, os
sys.path.insert(0, '/app/A2AServer')
sys.stdout.reconfigure(encoding='utf-8')

from A2AServer.v2.v2_runtime import get_runtime
from langchain_openai import ChatOpenAI

chat_model = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY", "fake"),
    base_url="https://api.deepseek.com",
    temperature=0,
)
r = get_runtime()
mws = r.get_middlewares(model="deepseek-chat", chat_model=chat_model)
print(f'get_middlewares (with chat_model) returned {len(mws)} middleware instances:')
for m in mws:
    print(f'  - {type(m).__name__}: {m}')
