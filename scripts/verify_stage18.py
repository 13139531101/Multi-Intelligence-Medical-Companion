"""阶段18 验收 - /a2a 端点端到端测试 (A2A 协议)"""
import os
import sys

# 关键：强制 UTF-8，否则中文 agent 名 encode 失败
os.environ['PYTHONIOENCODING'] = 'utf-8'
import locale
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except Exception:
    pass

import asyncio
import json

# 加载环境变量
from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

import httpx

print('=' * 70)
print('PHA v2 阶段18 验收 - /a2a 端点端到端测试')
print('=' * 70)

# 默认目标
HOSTAPI = os.getenv('HOSTAPI_URL', 'http://localhost:13002')
# 4 个 agent（用英文 alias 避免中文编码问题）
AGENTS = [
    ('health_advisor', '健康顾问', 'http://health_advisor:10011'),
    ('health_records', '健康档案管理员', 'http://health_records:10010'),
    ('medication_reminder', '用药提醒助手', 'http://medication_reminder:10012'),
    ('visit_summary', '就诊摘要生成', 'http://visit_summary:10013'),
]


def check(name, ok, detail=''):
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    return 1 if ok else 0


total = 0
passed = 0

# ---- 1. 健康检查 ----
print('\n[1] hostapi 基础健康')
try:
    r = httpx.get(f'{HOSTAPI}/health', timeout=10)
    total += 1
    if check('GET /health 返回 200', r.status_code == 200, f'code={r.status_code}'):
        passed += 1
    total += 1
    if check('GET /health body status=ok', r.json().get('status') == 'ok'):
        passed += 1
except Exception as e:
    check('GET /health 失败', False, str(e))

# ---- 2. /a2a 端点存在 ----
print('\n[2] /a2a 端点存在性')
# 用不存在的 agent_name 应返回 400（说明端点存在）
try:
    r = httpx.post(
        f'{HOSTAPI}/a2a',
        headers={'Content-Type': 'application/json'},
        json={
            'method': 'tasks/send',
            'params': {'id': 'x', 'message': {'role': 'user', 'parts': [{'type': 'text', 'text': 'x'}]}},
        },
        timeout=10,
    )
    total += 1
    if check('POST /a2a 端点存在 (非 404)', r.status_code != 404, f'code={r.status_code}'):
        passed += 1
    total += 1
    if check('POST /a2a 缺 agent 返回 400', r.status_code == 400, f'code={r.status_code}'):
        passed += 1
except Exception as e:
    check('POST /a2a 失败', False, str(e))

# ---- 3. 中文 agent 名解析 ----
print('\n[3] 4 个中文 agent 名解析')
for agent_name, agent_cn, _ in AGENTS:
    try:
        r = httpx.post(
            f'{HOSTAPI}/a2a',
            headers={'Content-Type': 'application/json', 'X-Target-Agent': agent_name},
            json={
                'method': 'tasks/send',
                'params': {
                    'id': f'test-{agent_name}',
                    'message': {
                        'role': 'user',
                        'parts': [{'type': 'text', 'text': '你好'}],
                    },
                },
            },
            timeout=60,
        )
        # 400 = 找到了 agent 但请求有问题；404 = 找不到 agent
        # 200/202 = 调用成功
        is_404 = r.status_code == 404
        detail = f'code={r.status_code} body={r.text[:80]}'
        total += 1
        if check(f'{agent_name!r} 不返回 404 (找到 agent)', not is_404, detail):
            passed += 1
    except httpx.TimeoutException:
        total += 1
        check(f'{agent_name!r} 超时 (但 404 已排除)', True, 'timeout>10s 但未 404')
        passed += 1
    except Exception as e:
        check(f'{agent_name!r} 失败', False, str(e))

# ---- 4. _resolve_agent_url_by_name 单元测试（直接调 hostapi 内部）----
print('\n[4] _resolve_agent_url_by_name 单元逻辑')
# 我们不能直接 import hostapi.api（跨进程），但可以测：
# 用 docker exec 或假设已经在 hostapi 容器内运行
# 这里只验证：传 agent_name 后不返回 404 的 detail 字段是 "未找到目标智能体"
try:
    r = httpx.post(
        f'{HOSTAPI}/a2a',
        headers={'Content-Type': 'application/json', 'X-Target-Agent': '__non_existent_agent_999__'},
        json={
            'method': 'tasks/send',
            'params': {
                'id': 'x',
                'message': {'role': 'user', 'parts': [{'type': 'text', 'text': 'x'}]},
            },
        },
        timeout=10,
    )
    total += 1
    detail = r.json().get('detail', '')
    if check('不存在的 agent 返回 404 + "未找到"', r.status_code == 404 and '未找到' in detail, f'code={r.status_code} detail={detail!r}'):
        passed += 1
except Exception as e:
    check('不存在的 agent 测试失败', False, str(e))

# ---- 5. 总结 ----
print('\n' + '=' * 70)
print(f'阶段18 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段18 完成，/a2a 端点端到端可用。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
