"""Test v2 SSE stream endpoint"""
import httpx
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("Connecting to /v2/chat/stream...")
with httpx.stream(
    "POST",
    "http://localhost:13002/v2/chat/stream",
    json={"message": "你好"},
    timeout=60,
) as r:
    print(f"HTTP {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type')}")
    print("--- events ---")
    for line in r.iter_lines():
        if line:
            print(line)
    print("--- end ---")