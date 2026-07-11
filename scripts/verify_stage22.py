"""阶段22 验收 - CI/CD 配置文件"""
import os
import sys
import re

os.environ['PYTHONIOENCODING'] = 'utf-8'
import yaml


def _open(path, mode='r'):
    return open(path, mode, encoding='utf-8')


print('=' * 70)
print('PHA v2 阶段22 验收 - CI/CD 流水线')
print('=' * 70)

total = 0
passed = 0


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:55s} {detail}')
    total += 1
    if ok:
        passed += 1


# ---- 1. 工作流文件存在 ----
print('\n[1] .github/workflows 文件存在')
workflows = ['test.yml', 'lint.yml', 'build.yml', 'release.yml']
for wf in workflows:
    path = os.path.join('.github', 'workflows', wf)
    check(f'{wf} 存在', os.path.exists(path))


# ---- 2. test.yml 必备元素 ----
print('\n[2] test.yml 完整性')
with _open('.github/workflows/test.yml') as f:
    test = yaml.safe_load(f)
check('test.yml 有 jobs.test', 'test' in test.get('jobs', {}))
job = test['jobs'].get('test', {})
check('runs-on 是 ubuntu-latest', job.get('runs-on') == 'ubuntu-latest')
check('有 services.postgres', 'postgres' in job.get('services', {}))
check('postgres 用 pgvector 镜像', 'pgvector' in job.get('services', {}).get('postgres', {}).get('image', ''))
check('有 services.redis', 'redis' in job.get('services', {}))
check('Setup Python 用 v5', 'actions/setup-python@v5' in str(test))
check('Checkout 用 v4', 'actions/checkout@v4' in str(test))
check('包含 "verify_stage" 多次', str(test).count('verify_stage') >= 5)
check('安装依赖 (pip install)', 'pip install' in str(test))
check('含 CREATE EXTENSION vector', 'CREATE EXTENSION' in str(test) and 'vector' in str(test))


# ---- 3. lint.yml 必备元素 ----
print('\n[3] lint.yml 完整性')
with _open('.github/workflows/lint.yml') as f:
    lint = yaml.safe_load(f)
check('lint.yml 有 jobs.lint', 'lint' in lint.get('jobs', {}))
check('install ruff', 'ruff' in str(lint))
check('install black', 'black' in str(lint))
check('install mypy', 'mypy' in str(lint))


# ---- 4. build.yml 必备元素 ----
print('\n[4] build.yml 完整性')
with _open('.github/workflows/build.yml') as f:
    build = yaml.safe_load(f)
check('build.yml 有 jobs.build', 'build' in build.get('jobs', {}))
job = build['jobs'].get('build', {})
check('matrix 包含 5 个 target', len(job.get('strategy', {}).get('matrix', {}).get('target', [])) == 5)
targets = [t['name'] for t in job.get('strategy', {}).get('matrix', {}).get('target', [])]
for expected in ['hostapi', 'health_advisor', 'health_records', 'medication_reminder', 'visit_summary']:
    check(f'包含 {expected}', expected in targets)
check('使用 docker/build-push-action@v5', 'docker/build-push-action@v5' in str(build))
check('使用 docker/setup-buildx-action@v3', 'docker/setup-buildx-action@v3' in str(build))
# yaml 的 on: 转 True (YAML 1.1 'on' 是 bool)
# 用 raw text 检查更可靠
with _open('.github/workflows/build.yml') as f:
    build_raw = f.read()
check('build.yml 含 "tags:" 触发', 'tags:' in build_raw or "'v*.*.*'" in build_raw)


# ---- 5. release.yml 必备元素 ----
print('\n[5] release.yml 完整性')
with _open('.github/workflows/release.yml') as f:
    release = yaml.safe_load(f)
check('release.yml 有 jobs.release', 'release' in release.get('jobs', {}))
with _open('.github/workflows/release.yml') as f:
    release_raw = f.read()
check('release.yml 含 v*.*.* 标签', "'v*.*.*'" in release_raw)
check('用 softprops/action-gh-release@v2', 'softprops/action-gh-release@v2' in str(release))
check('包含 prerelease 字段', 'prerelease' in str(release))
check('permissions.contents: write', 'contents: write' in release_raw)


# ---- 6. YAML 语法检查 ----
print('\n[6] YAML 语法有效性')
for wf in workflows:
    path = os.path.join('.github', 'workflows', wf)
    try:
        with _open(path) as f:
            yaml.safe_load(f)
        check(f'{wf} YAML 语法正确', True)
    except yaml.YAMLError as e:
        check(f'{wf} YAML 语法', False, str(e)[:60])


# ---- 7. 触发器覆盖 ----
print('\n[7] 触发器覆盖')
all_triggers = set()
for wf in workflows:
    with _open(f'.github/workflows/{wf}') as f:
        content = f.read()
    for trigger in ['push', 'pull_request', 'tags', 'workflow_dispatch']:
        if trigger in content:
            all_triggers.add(trigger)
check('至少含 push 触发', 'push' in all_triggers)
check('至少含 pull_request 触发', 'pull_request' in all_triggers)
check('至少含 tags 触发（release）', 'tags' in all_triggers)
check('至少含 workflow_dispatch（手动）', 'workflow_dispatch' in all_triggers)


# ---- 8. 文件大小合理 ----
print('\n[8] 文件大小')
for wf in workflows:
    path = os.path.join('.github', 'workflows', wf)
    size = os.path.getsize(path)
    check(f'{wf} 大小 {size} bytes (>500, <10000)', 500 < size < 10000, f'{size}b')


# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段22 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段22 完成，CI/CD 4 个工作流就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
