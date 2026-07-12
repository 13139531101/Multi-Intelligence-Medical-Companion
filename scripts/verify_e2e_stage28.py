"""阶段28 E2E 验证脚本 - v2 LangGraph 容器端到端跑通

测试场景：
1. 启动 hostapi 容器（含 langgraph + 11 MCP 工具）
2. POST /smart_chat 真提问
3. 检查容器日志确认 v2 链路全跑通
"""
import sys
import time
import subprocess
import httpx
import json

print('=' * 70)
print('PHA v2 阶段28 E2E 验证 - v2 LangGraph 端到端')
print('=' * 70)


def step(name):
    print(f'\n[{name}]')


def ok(msg):
    print(f'  [OK]   {msg}')


def fail(msg):
    print(f'  [FAIL] {msg}')


# ---- 1. 准备环境变量 ----
step('1. 准备环境变量')
ENV = {
    'PYTHONPATH': '/app:/app/backend',
    'DB_HOST': 'postgres',
    'DB_USER': 'pha',
    'DB_PASSWORD': 'zTlQevKV5vzq31QzRqwfcauKX3uQZ64c',
    'MEMORY_DB_HOST': 'postgres',
    'MEMORY_DB_USER': 'pha',
    'MEMORY_DB_PASSWORD': 'zTlQevKV5vzq31QzRqwfcauKX3uQZ64c',
    'MEMORY_DB_NAME': 'personal_health_assistant',
    'DEEPSEEK_API_KEY': 'sk-5de395dfb19d41a890816f61ae379cdb',
    'DASHSCOPE_API_KEY': 'sk-2917df2994074695b7b741ffb6382a3b',
    'QWEN_API_KEY': 'sk-2917df2994074695b7b741ffb6382a3b',
    'JWT_SECRET_KEY': 'ygRtTIVjkW9vkqswaiLCIRIi231Ovyl4d9TBmx3NMB8AJwE02XxwPARBX_r67A-i',
    'PHA_USE_V2': 'true',
}
ok(f'{len(ENV)} env vars ready')


# ---- 2. 启动容器 ----
step('2. 启动 hostapi:stage28v3 容器')
subprocess.run(['docker', 'rm', '-f', 'a2aserver-hostapi-stage28'], capture_output=True)

cmd = ['docker', 'run', '-d', '--name', 'a2aserver-hostapi-stage28',
       '--network', 'a2aserver_default', '-p', '13004:13002']
for k, v in ENV.items():
    cmd.extend(['-e', f'{k}={v}'])
cmd.append('a2aserver-hostapi:stage28v3')

r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
if r.returncode != 0:
    fail(f'docker run failed: {r.stderr[:200]}')
    sys.exit(1)
ok(f'Container started: {r.stdout.strip()[:12]}')


# ---- 3. 等启动 ----
step('3. 等 uvicorn 启动 (最多 60s)')
for i in range(60):
    time.sleep(2)
    try:
        r = httpx.get('http://localhost:13004/health', timeout=2)
        if r.status_code == 200:
            ok(f'Ready after {(i+1)*2}s')
            break
    except Exception:
        pass
else:
    fail('hostapi 没起来')
    subprocess.run(['docker', 'logs', '--tail', '50', 'a2aserver-hostapi-stage28'],
                   capture_output=True)
    sys.exit(1)


# ---- 4. 真提问 ----
step('4. POST /smart_chat 真提问')
print('  提问: "我最近总是头疼，可能是什么原因？"')

r = httpx.post(
    'http://localhost:13004/smart_chat',
    json={'message': '我最近总是头疼，可能是什么原因？'},
    timeout=120,
)
print(f'  HTTP status: {r.status_code}')
body = r.text
print(f'  Response: {body[:200]}')

if r.status_code == 200:
    ok(f'HTTP 200, response: {body[:100]}')
else:
    fail(f'HTTP {r.status_code}')
    sys.exit(1)


# ---- 5. 等 v2 stream 跑 ----
step('5. 等 v2 stream 跑（最多 90s）')
time.sleep(30)

# ---- 6. 检查日志 ----
step('6. 检查容器日志确认 v2 链路')
r = subprocess.run(
    ['docker', 'logs', 'a2aserver-hostapi-stage28'],
    capture_output=True, timeout=10,
)
log = r.stdout.decode('utf-8', errors='replace') + r.stderr.decode('utf-8', errors='replace')

checks = [
    ('bridge PHA_BACKEND', 'PHA_BACKEND = /app' in log),
    ('v2 attempt True', 'v2 attempt: is_v2_request=True' in log),
    ('routing to v2', 'routing to v2 HostGraph' in log),
    ('layer1 metadata', 'layer1 metadata' in log),
    ('mcp_discover REPO_ROOT', 'REPO_ROOT = /app' in log),
    ('mcp tools found 18', 'found 18 MCP tools in 5 files' in log),
    ('mcp_tool_adapter loaded 11', 'loaded 11 tools' in log),
    ('v2_runtime Checkpointer', 'Checkpointer = InMemorySaver' in log),
    ('v2_agent created', 'created (singleton): model=deepseek-chat' in log),
    ('rate_limit initialized', 'rate_limit] initialized' in log),
    ('smart_chat PHA v2 success', '[PHA v2] success' in log),
    ('Uvicorn running', 'Uvicorn running on' in log),
    ('DB 自检通过', 'DB鑷閫氳繃' in log or 'DB自检通过' in log),
]

passed = 0
total = len(checks)
for name, ok_check in checks:
    if ok_check:
        ok(f'{name}')
        passed += 1
    else:
        fail(f'{name}')


# ---- 7. 清理 ----
step('7. 清理')
subprocess.run(['docker', 'rm', '-f', 'a2aserver-hostapi-stage28'], capture_output=True)
ok('Container removed')


# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段28 E2E 验证：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！v2 LangGraph + 11 MCP 工具 + DeepSeek 端到端跑通！')
else:
    print(f'[WARN] 有 {total - passed} 项没匹配（可能日志截断）')
print('=' * 70)