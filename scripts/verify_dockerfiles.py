"""验证 5 个 Dockerfile 基本语法（FROM / WORKDIR / COPY / CMD）"""
import os
import re
import sys

os.environ['PYTHONIOENCODING'] = 'utf-8'

DOCKERFILES = [
    ('hostapi', 'frontend/hostAgentAPI/Dockerfile'),
    ('health_advisor', 'backend/HealthAdvisor/Dockerfile'),
    ('health_records', 'backend/HealthRecordsManager/Dockerfile'),
    ('medication_reminder', 'backend/MedicationReminder/Dockerfile'),
    ('visit_summary', 'backend/VisitSummaryGenerator/Dockerfile'),
]


def _open(p):
    return open(p, encoding='utf-8')


def parse_dockerfile(path):
    """简单解析：找 FROM / WORKDIR / COPY / CMD / EXPOSE"""
    out = {'from': None, 'workdir': None, 'cmds': [], 'copies': [], 'runs': [], 'exposes': []}
    if not os.path.exists(path):
        return out
    with _open(path) as f:
        lines = f.readlines()
    in_continuation = False
    for line in lines:
        # 跳过注释和空行
        if in_continuation:
            cmd_full += ' ' + line.rstrip()
            in_continuation = line.rstrip().endswith('\\')
            if not in_continuation:
                _process_cmd(cmd_full, out)
            continue
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        # 检查续行
        if line_stripped.endswith('\\'):
            cmd_full = line_stripped[:-1]
            in_continuation = True
            continue
        _process_cmd(line_stripped, out)
    return out


def _process_cmd(line, out):
    line = line.rstrip()
    if line.startswith('FROM '):
        out['from'] = line[5:].split(' AS ')[0].strip().split()[0] if line[5:].strip() else None
    elif line.startswith('WORKDIR '):
        out['workdir'] = line[8:].strip()
    elif line.startswith('COPY '):
        out['copies'].append(line[5:].strip())
    elif line.startswith('RUN '):
        out['runs'].append(line[4:].strip()[:60])
    elif line.startswith('CMD '):
        out['cmds'].append(line[4:].strip()[:80])
    elif line.startswith('EXPOSE '):
        out['exposes'].append(line[7:].strip())


total = 0
passed = 0
print('=' * 70)
print('PHA v2 阶段23+ 验证 - 5 Dockerfile 语法 + 基本结构')
print('=' * 70)


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:50s} {detail}')
    total += 1
    if ok:
        passed += 1


for name, path in DOCKERFILES:
    print(f'\n[{name}] {path}')
    check(f'{name} 文件存在', os.path.exists(path))
    if not os.path.exists(path):
        continue
    info = parse_dockerfile(path)
    check(f'{name} 有 FROM', info['from'] is not None, f"FROM {info['from']}")
    if info['from']:
        check(f'{name} FROM 是 python:3.11', 'python' in info['from'] and '3.11' in info['from'], info['from'])
    check(f'{name} 有 WORKDIR', info['workdir'] is not None, f"WORKDIR {info['workdir']}")
    check(f'{name} 有 COPY (>=1)', len(info['copies']) >= 1, f"{len(info['copies'])} copies")
    check(f'{name} 有 RUN (>=1)', len(info['runs']) >= 1, f"{len(info['runs'])} runs")
    # EXPOSE 检查
    print(f'    exposes: {info["exposes"]}')
    print(f'    cmds[0]: {info["cmds"][0] if info["cmds"] else "NONE"}')

print('\n' + '=' * 70)
print(f'Dockerfile 验证：{passed}/{total} 通过')
if passed == total:
    print('[OK] 5 Dockerfile 全部就绪！')
else:
    print(f'[WARN] {total - passed} 项失败')
print('=' * 70)
