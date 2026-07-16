"""E2E 真实测试 - 跑 hostapi + 真实提问"""
import sys
import time
import subprocess
import httpx
import json

print('=' * 70)
print('PHA v2 E2E 测试 - hostapi HTTP 端到端 + 真实提问')
print('=' * 70)


def step(name):
    print(f'\n[{name}]')


def ok(msg):
    print(f'  [OK]   {msg}')


def fail(msg):
    print(f'  [FAIL] {msg}')


# ---- 1. 启 hostapi (PHA_USE_V2=true 默认) ----
step('1. 启动 hostapi 容器 (PHA_USE_V2=true 默认)')
import os
os.chdir('I:\\A2A\\3\\A2AServer')
cmd = [
    'docker', 'rm', '-f', 'a2aserver-hostapi-e2e',
]
subprocess.run(cmd, capture_output=True)

cmd = [
    'docker', 'run', '-d', '--name', 'a2aserver-hostapi-e2e',
    '--network', 'a2aserver_default',
    '-p', '13003:13002',
    '-v', 'I:/A2A/3/A2AServer/backend/A2AServer/src/A2AServer:/app/A2AServer',
    '-v', 'I:/A2A/3/A2AServer/backend:/app/backend',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/api.py:/app/api.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/auth.py:/app/auth.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/auth_middleware.py:/app/auth_middleware.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/adk_host_manager.py:/app/adk_host_manager.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/agents.json:/app/agents.json',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/application_manager.py:/app/application_manager.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/server.py:/app/server.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/agent_card.py:/app/agent_card.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/ServiceTypes.py:/app/ServiceTypes.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/check_user.py:/app/check_user.py',
    '-v', 'I:/A2A/3/A2AServer/frontend/hostAgentAPI/init_database.py:/app/init_database.py',
    '-e', 'PYTHONPATH=/app:/app/backend',
    '-e', 'DB_HOST=postgres', '-e', 'DB_PORT=5432',
    '-e', 'DB_USER=pha', '-e', 'DB_PASSWORD=zTlQevKV5vzq31QzRqwfcauKX3uQZ64c',
    '-e', 'DEEPSEEK_API_KEY=sk-5de395dfb19d41a890816f61ae379cdb',
    '-e', 'DASHSCOPE_API_KEY=sk-2917df2994074695b7b741ffb6382a3b',
    '-e', 'QWEN_API_KEY=sk-2917df2994074695b7b741ffb6382a3b',
    '-e', 'JWT_SECRET_KEY=ygRtTIVjkW9vkqswaiLCIRIi231Ovyl4d9TBmx3NMB8AJwE02XxwPARBX_r67A-i',
    '-e', 'PHA_OAUTH_TEST_MODE=true',
    '-e', 'PHA_USE_V2=true',  # 默认开
    'crpi-zr8m4m7ism94623a.cn-hangzhou.personal.cr.aliyuncs.com/duozhiyiban/a2aserver-hostapi:v1.0.0',
    'python', '-m', 'uvicorn', 'api:app', '--host', '0.0.0.0', '--port', '13002',
]
print('  Starting hostapi...')
r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
if r.returncode != 0:
    fail(f'docker run failed: {r.stderr[:200]}')
    sys.exit(1)
ok(f'Container started: {r.stdout.strip()[:12]}')


# ---- 2. 等 hostapi 启动 ----
step('2. 等 hostapi 启动 (最多 60s)')
for i in range(60):
    time.sleep(2)
    try:
        r = httpx.get('http://localhost:13003/health', timeout=3)
        if r.status_code == 200:
            ok(f'hostapi ready after {(i+1)*2}s')
            break
    except Exception:
        pass
else:
    fail('hostapi 没起来')
    subprocess.run(['docker', 'logs', 'a2aserver-hostapi-e2e'], capture_output=True)
    subprocess.run(['docker', 'rm', '-f', 'a2aserver-hostapi-e2e'], capture_output=True)
    sys.exit(1)


# ---- 3. 真实健康问题 ----
step('3. 真实提问 - 健康咨询')
print('  提问: "我最近总是头疼，可能是什么原因？"')

# 先用 v2 (默认) - 走 /smart_chat 端点
try:
    r = httpx.post(
        'http://localhost:13003/smart_chat',
        json={'message': '我最近总是头疼，可能是什么原因？'},
        timeout=120,
    )
    print(f'  HTTP status: {r.status_code}')
    if r.status_code == 200:
        body = r.text
        print(f'  Response (前 500 字符): {body[:500]}')
        if '头疼' in body or '原因' in body or '建议' in body or 'health' in body.lower() or 'health' in body:
            ok('v2 真调了 + 返了相关回复')
        else:
            fail(f'v2 返回内容不像健康咨询: {body[:300]}')
    else:
        fail(f'v2 HTTP {r.status_code}: {r.text[:200]}')
except Exception as e:
    fail(f'v2 调用失败: {str(e)[:100]}')


# ---- 4. 真实用药提醒 ----
step('4. 真实提问 - 用药提醒')
print('  提问: "提醒我晚上 9 点吃高血压药"')

try:
    r = httpx.post(
        'http://localhost:13003/smart_chat',
        json={'message': '提醒我晚上 9 点吃高血压药'},
        timeout=120,
    )
    print(f'  HTTP status: {r.status_code}')
    if r.status_code == 200:
        body = r.text
        print(f'  Response (前 500 字符): {body[:500]}')
        if '提醒' in body or '用药' in body or 'medication' in body.lower() or 'agent' in body.lower():
            ok('用药提醒路径工作')
        else:
            fail(f'返回不像用药提醒: {body[:300]}')
    else:
        fail(f'用药 HTTP {r.status_code}: {r.text[:200]}')
except Exception as e:
    fail(f'用药调用失败: {str(e)[:100]}')


# ---- 5. 看日志确认 v2 真跑 ----
step('5. 容器日志确认 v2 路径')
r = subprocess.run(
    ['docker', 'logs', 'a2aserver-hostapi-e2e'],
    capture_output=True, timeout=10,
)
log_bytes = (r.stdout or b'') + (r.stderr or b'')
try:
    log = log_bytes.decode('utf-8', errors='replace')
except Exception:
    log = log_bytes.decode('gbk', errors='replace')
v2_count = log.count('PHA v2')
v2_routing = log.count('routing to v2')
v2_success = log.count('PHA v2] success')
v2_error = log.count('PHA v2] error')
v2_fallback = log.count('fallback to v1')

print(f'  PHA v2 日志次数: {v2_count}')
print(f'  routing to v2 次数: {v2_routing}')
print(f'  PHA v2 success 次数: {v2_success}')
print(f'  PHA v2 error 次数: {v2_error}')
print(f'  fallback to v1 次数: {v2_fallback}')

if v2_routing >= 2:
    ok('v2 真跑了 2 次')
else:
    fail(f'v2 路由次数 {v2_routing} 太少')


# ---- 6. 显示日志关键片段 ----
step('6. 关键日志片段 (v2 相关)')
for line in log.split('\n'):
    if 'PHA v2' in line or 'v2_host_graph' in line or 'health_advisor' in line or 'medication' in line:
        print(f'  > {line.strip()[:150]}')


# ---- 6. 清理 ----
step('6. 清理')
subprocess.run(['docker', 'rm', '-f', 'a2aserver-hostapi-e2e'], capture_output=True)
ok('Container removed')

print('\n' + '=' * 70)
print('E2E 真实测试完成')
print('=' * 70)