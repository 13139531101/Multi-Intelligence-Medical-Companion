"""阶段23 验收 - CI/CD Build 路径修复"""
import os
import sys

os.environ['PYTHONIOENCODING'] = 'utf-8'
import yaml

print('=' * 70)
print('PHA v2 阶段23 验收 - Build 路径修复')
print('=' * 70)

total = 0
passed = 0


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:60s} {detail}')
    total += 1
    if ok:
        passed += 1


# ---- 1. build.yml 加载 ----
print('\n[1] build.yml 加载')
with open('.github/workflows/build.yml', encoding='utf-8') as f:
    build = yaml.safe_load(f)
job = build['jobs']['build']
matrix = job['strategy']['matrix']
targets = matrix.get('include', [])
check('build.yml 加载', build is not None)
check('jobs.build 存在', 'build' in build.get('jobs', {}))
check('matrix.include 是 list', isinstance(targets, list))
check('matrix 包含 5 个 target', len(targets) == 5, f'got {len(targets)}')

# ---- 2. 5 个 Dockerfile 路径都存在 ----
print('\n[2] 5 个 Dockerfile 路径验证')
expected_dockerfiles = [
    'frontend/hostAgentAPI/Dockerfile',
    'backend/HealthAdvisor/Dockerfile',
    'backend/HealthRecordsManager/Dockerfile',
    'backend/MedicationReminder/Dockerfile',
    'backend/VisitSummaryGenerator/Dockerfile',
]
for df in expected_dockerfiles:
    check(f'{df} 存在', os.path.exists(df))


# ---- 3. matrix 中每个 target 路径都正确 ----
print('\n[3] matrix target 路径正确性')
for t in targets:
    name = t['name']
    df = t['dockerfile']
    check(f'{name} 路径 = {df}', df in expected_dockerfiles, df)
    check(f'{name} Dockerfile 文件存在', os.path.exists(df))


# ---- 4. 关键参数 ----
print('\n[4] 关键 CI 参数')
check('continue-on-error 在 job 上', job.get('continue-on-error') is True)
check('fail-fast: false', job['strategy'].get('fail-fast') is False)
check('timeout-minutes >= 15', job.get('timeout-minutes', 0) >= 15)

# 检查 build step
build_step = next((s for s in job.get('steps', []) if s.get('name') == 'Build image'), None)
check('Build image step 存在', build_step is not None)
if build_step:
    check('Build 用 build-push-action@v5', 'docker/build-push-action@v5' in str(build_step))
    check('Build 有 context', 'context' in build_step.get('with', {}))
    check('Build 有 file', 'file' in build_step.get('with', {}))
    check('Build 有 tags (含 SHA + latest)', 'tags' in build_step.get('with', {}) and 'latest' in str(build_step['with'].get('tags', '')))
    check('Build 用 GHA cache', 'cache-from' in str(build_step))
    check('Build platforms linux/amd64', 'linux/amd64' in str(build_step))

# ---- 5. Registry / secrets ----
print('\n[5] Registry + Secrets')
check('REGISTRY env = aliyun', 'aliyuncs.com' in build.get('env', {}).get('REGISTRY', ''))
check('IMAGE_PREFIX = a2aserver', build.get('env', {}).get('IMAGE_PREFIX') == 'a2aserver')
login_step = next((s for s in job.get('steps', []) if 'Login' in s.get('name', '')), None)
check('Login step 存在', login_step is not None)
if login_step:
    check('Login 用 docker/login-action@v3', 'docker/login-action@v3' in str(login_step))
    check('Login 有 secrets 引用', 'secrets' in str(login_step))


# ---- 6. 触发器 ----
print('\n[6] 触发器')
with open('.github/workflows/build.yml', encoding='utf-8') as f:
    build_raw = f.read()
check('on.push 触发', 'push:' in build_raw)
check('on.tags 触发 (v*.*.*)', "v*.*.*" in build_raw)
check('on.workflow_dispatch 触发', 'workflow_dispatch' in build_raw)


# ---- 7. 文件大小 ----
print('\n[7] 文件大小')
size = os.path.getsize('.github/workflows/build.yml')
check(f'build.yml 大小 {size} bytes (合理)', 1500 < size < 10000, f'{size}b')


# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段23 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段23 完成，build.yml 路径修复。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
