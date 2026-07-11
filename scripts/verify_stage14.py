"""阶段14 验收 - 监控 HTTP 端点 + .env.example + Makefile v2 目标"""
import os
import sys
import json
from pathlib import Path

from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

sys.path.insert(0, 'backend/A2AServer/src')

print('=' * 70)
print('PHA v2 阶段14 验收 - 监控端点 + 部署配置')
print('=' * 70)


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 监控端点模块 ----
print('\n[1] 监控端点模块')
from A2AServer.v2.monitoring_endpoints import (
    router,
    health_router,
)

total += 1
if check('v2 router 可导入', router is not None):
    passed += 1
total += 1
if check('health_router 可导入', health_router is not None):
    passed += 1

# ---- 2. TestClient 测试端点 ----
print('\n[2] HTTP 端点测试')

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(router)
    client = TestClient(app)

    # 2.1: /health
    r = client.get("/health")
    total += 1
    if check('GET /health 返回 200', r.status_code == 200, f"code={r.status_code}"):
        passed += 1
    body = r.json()
    total += 1
    if check('GET /health 含 status=ok', body.get("status") == "ok", f"body={body}"):
        passed += 1

    # 2.2: /health/deep
    r = client.get("/health/deep")
    total += 1
    if check('GET /health/deep 返回 200 或 503', r.status_code in (200, 503)):
        passed += 1
    body = r.json()
    total += 1
    if check('GET /health/deep 含 checks', "checks" in body):
        passed += 1
    total += 1
    if check('checks 包含 v2_runtime', "v2_runtime" in body.get("checks", {})):
        passed += 1

    # 2.3: /metrics
    r = client.get("/metrics")
    total += 1
    if check('GET /metrics 返回 200', r.status_code == 200):
        passed += 1
    total += 1
    if check('GET /metrics text/plain', "text/plain" in r.headers.get("content-type", "")):
        passed += 1
    total += 1
    if check('GET /metrics 含 pha_request_total', "pha_request_total" in r.text):
        passed += 1

    # 2.4: /v2/status
    r = client.get("/v2/status")
    total += 1
    if check('GET /v2/status 返回 200', r.status_code == 200):
        passed += 1
    body = r.json()
    total += 1
    if check('GET /v2/status 含 metrics', "metrics" in body):
        passed += 1
    total += 1
    if check('GET /v2/status 含 tool_cache', "tool_cache" in body):
        passed += 1
    total += 1
    if check('GET /v2/status 含 rate_limiter', "rate_limiter" in body):
        passed += 1

    # 2.5: /v2/metrics/json
    r = client.get("/v2/metrics/json")
    total += 1
    if check('GET /v2/metrics/json 返回 200', r.status_code == 200):
        passed += 1

    # 2.6: /v2/summary
    r = client.get("/v2/summary")
    total += 1
    if check('GET /v2/summary 返回 200', r.status_code == 200):
        passed += 1
    body = r.json()
    total += 1
    if check('GET /v2/summary 含摘要', "summary" in body):
        passed += 1

    # 2.7: /v2/metrics/reset
    r = client.post("/v2/metrics/reset")
    total += 1
    if check('POST /v2/metrics/reset 返回 200', r.status_code == 200):
        passed += 1

except ImportError as e:
    check('TestClient 可用', False, str(e))
    for _ in range(15):
        total += 1
        # 跳过

# ---- 3. .env.example 存在且完整 ----
print('\n[3] .env.example 配置完整性')
env_example = Path('.env.example')
total += 1
if check('.env.example 存在', env_example.exists()):
    passed += 1

if env_example.exists():
    content = env_example.read_text(encoding='utf-8')
    required_vars = [
        "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL",
        "DEEPSEEK_API_KEY", "PHA_LLM_MODEL",
        "DASHSCOPE_API_KEY", "EMBEDDING_MODEL",
        "PHA_LLM_QPS", "PHA_USER_RPM", "PHA_RATE_LIMIT",
        "PHA_TOOL_CACHE_TTL",
        "PHA_CONCURRENT_TOOLS",
        "HOSTAPI_PORT",
    ]
    for var in required_vars:
        total += 1
        if check(f'.env.example 含 {var}', var in content):
            passed += 1

# ---- 4. Makefile v2 目标 ----
print('\n[4] Makefile v2 目标')
makefile = Path('Makefile')
total += 1
if check('Makefile 存在', makefile.exists()):
    passed += 1

if makefile.exists():
    content = makefile.read_text(encoding='utf-8')
    targets = [
        "v2-verify-all",
        "v2-verify-%",
        "v2-bench",
        "v2-test",
        "v2-format",
        "v2-clean",
        "metrics:",
        "health:",
    ]
    for t in targets:
        total += 1
        if check(f'Makefile 含 {t}', t in content):
            passed += 1

# ---- 5. metrics 端点 Prometheus 格式 ----
print('\n[5] Prometheus 格式')
try:
    r = client.get("/metrics")
    text = r.text
    has_pha_prefix = any(line.startswith("pha_") for line in text.split("\n") if line)
    total += 1
    if check('Prometheus 输出含 pha_ 前缀指标', has_pha_prefix):
        passed += 1
    has_help = "# HELP" in text
    total += 1
    if check('Prometheus 含 # HELP 注释', has_help):
        passed += 1
    has_type = "# TYPE" in text
    total += 1
    if check('Prometheus 含 # TYPE 注释', has_type):
        passed += 1
except Exception:
    pass

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段14 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段14 完成，监控端点 + 部署配置就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
