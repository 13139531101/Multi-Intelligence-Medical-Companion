"""查看 v2 状态 + metrics"""
import httpx
import json
import sys

r = httpx.get("http://localhost:13002/v2/status", timeout=5)
data = r.json()
# 写到 stdout 但用 utf-8
sys.stdout.reconfigure(encoding='utf-8')
print("=== /v2/status 全部字段 ===")
print(json.dumps(data, ensure_ascii=False, indent=2))