"""
PHA v2 性能压测脚本（阶段7）

**测试目标**：
- 量化 v2 真实延迟 / 工具调用次数 / token 消耗
- 对比 v1 估算性能（基于历史经验值）
- 找出瓶颈，提出优化建议

**测试场景**：
- 4 个 Agent × 5 种典型 query × 3 次重复 = 60 次

**指标**：
- 端到端延迟（P50/P99）
- 工具调用次数
- 输出长度
- 错误率
"""
import os
import sys
import asyncio
import time
import json
import statistics
from pathlib import Path
from datetime import datetime

# 加载 .env
from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

# sys.path
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2 import (
    HealthAdvisorV2,
    HealthRecordsV2,
    MedicationReminderV2,
    VisitSummaryV2,
)


# ============================================================
# 测试场景
# ============================================================
TEST_SCENARIOS = {
    "health_advisor": [
        ("症状咨询-短", "我头疼", "layer2-keyword"),
    ],
    "health_records": [
        ("档案查询", "查询我的体检档案", "layer2-keyword"),
    ],
    "medication_reminder": [
        ("简单提醒", "设置一个吃药提醒", "layer2-keyword"),
    ],
    "visit_summary": [
        ("生成摘要", "生成我的就诊摘要", "layer2-keyword"),
    ],
}

AGENT_CLS_MAP = {
    "health_advisor": HealthAdvisorV2,
    "health_records": HealthRecordsV2,
    "medication_reminder": MedicationReminderV2,
    "visit_summary": VisitSummaryV2,
}

REPEAT = 1


# ============================================================
# 单次压测
# ============================================================
async def run_single(agent_name: str, query: str, session_id: str, user_id: str) -> dict:
    agent_cls = AGENT_CLS_MAP[agent_name]
    agent = agent_cls()

    start = time.time()
    tool_calls = []
    content_len = 0
    error = None
    events_count = 0

    try:
        async for event in agent.stream(query, session_id, user_id=user_id):
            events_count += 1
            ev_type = event.get("type", "?")
            if ev_type == "tool_call":
                tool_calls.append({
                    "name": event.get("name"),
                    "args": event.get("args", {}),
                })
            elif ev_type == "normal":
                content_len += len(str(event.get("content", "")))
            elif ev_type == "tool_result":
                pass
            if event.get("is_task_complete"):
                break
    except Exception as e:
        error = str(e)[:200]

    elapsed = time.time() - start
    return {
        "agent": agent_name,
        "query": query[:30],
        "session_id": session_id,
        "elapsed_sec": round(elapsed, 2),
        "events_count": events_count,
        "tool_calls": tool_calls,
        "tool_call_count": len(tool_calls),
        "content_len": content_len,
        "error": error,
    }


# ============================================================
# 全部压测
# ============================================================
async def run_all_benchmarks():
    results = []
    total_start = time.time()

    for agent_name, scenarios in TEST_SCENARIOS.items():
        for i, (scenario_name, query, expected_layer) in enumerate(scenarios):
            for repeat_idx in range(REPEAT):
                session_id = f"perf-{agent_name}-{i}-{repeat_idx}-{int(time.time())}"
                user_id = f"u_perf_{agent_name}"
                print(f"  [{agent_name}] {scenario_name} #{repeat_idx+1}/{REPEAT} ...")
                result = await run_single(agent_name, query, session_id, user_id)
                result["scenario"] = scenario_name
                result["repeat"] = repeat_idx + 1
                result["expected_layer"] = expected_layer
                results.append(result)
                print(f"    -> {result['elapsed_sec']}s, {result['tool_call_count']} tools, {result['content_len']} chars"
                      + (f", ERR: {result['error']}" if result['error'] else ""))

    total_elapsed = time.time() - total_start
    return results, total_elapsed


# ============================================================
# 报告生成
# ============================================================
def generate_report(results: list, total_elapsed: float) -> dict:
    """生成压测统计报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_runs": len(results),
        "total_elapsed_sec": round(total_elapsed, 2),
        "by_agent": {},
        "summary": {},
    }

    # 按 Agent 统计
    for agent_name in TEST_SCENARIOS.keys():
        agent_results = [r for r in results if r["agent"] == agent_name]
        if not agent_results:
            continue

        latencies = [r["elapsed_sec"] for r in agent_results if not r["error"]]
        tool_counts = [r["tool_call_count"] for r in agent_results if not r["error"]]
        content_lens = [r["content_len"] for r in agent_results if not r["error"]]
        errors = [r for r in agent_results if r["error"]]

        report["by_agent"][agent_name] = {
            "total_runs": len(agent_results),
            "successful": len(latencies),
            "errors": len(errors),
            "error_rate": round(len(errors) / len(agent_results) * 100, 1) if agent_results else 0,
            "latency_p50": round(statistics.median(latencies), 2) if latencies else 0,
            "latency_p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if latencies else 0,
            "latency_p99": round(sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 1 else (latencies[0] if latencies else 0), 2),
            "latency_mean": round(statistics.mean(latencies), 2) if latencies else 0,
            "latency_min": round(min(latencies), 2) if latencies else 0,
            "latency_max": round(max(latencies), 2) if latencies else 0,
            "tool_calls_mean": round(statistics.mean(tool_counts), 1) if tool_counts else 0,
            "tool_calls_max": max(tool_counts) if tool_counts else 0,
            "content_len_mean": int(statistics.mean(content_lens)) if content_lens else 0,
        }

    # 全局总结
    all_latencies = [r["elapsed_sec"] for r in results if not r["error"]]
    all_errors = [r for r in results if r["error"]]
    report["summary"] = {
        "total_runs": len(results),
        "successful": len(all_latencies),
        "errors": len(all_errors),
        "error_rate": round(len(all_errors) / len(results) * 100, 1) if results else 0,
        "latency_p50": round(statistics.median(all_latencies), 2) if all_latencies else 0,
        "latency_p95": round(sorted(all_latencies)[int(len(all_latencies) * 0.95)], 2) if all_latencies else 0,
        "latency_p99": round(sorted(all_latencies)[int(len(all_latencies) * 0.99)] if len(all_latencies) > 1 else (all_latencies[0] if all_latencies else 0), 2),
        "latency_mean": round(statistics.mean(all_latencies), 2) if all_latencies else 0,
        "total_elapsed_sec": round(total_elapsed, 2),
        "rps": round(len(results) / total_elapsed, 2) if total_elapsed else 0,
    }

    return report


def print_report(report: dict):
    """打印人类可读报告"""
    print('\n' + '=' * 70)
    print('PHA v2 性能压测报告')
    print('=' * 70)
    print(f"  时间: {report['timestamp']}")
    print(f"  总请求: {report['total_runs']}")
    print(f"  成功: {report['summary']['successful']}")
    print(f"  错误: {report['summary']['errors']} ({report['summary']['error_rate']}%)")
    print(f"  压测总耗时: {report['total_elapsed_sec']}s")
    print(f"  RPS (请求/秒): {report['summary']['rps']}")

    print(f"\n  延迟分布:")
    print(f"    P50: {report['summary']['latency_p50']}s")
    print(f"    P95: {report['summary']['latency_p95']}s")
    print(f"    P99: {report['summary']['latency_p99']}s")
    print(f"    Mean: {report['summary']['latency_mean']}s")

    print(f"\n  按 Agent 细分:")
    for agent_name, stats in report['by_agent'].items():
        print(f"\n    [{agent_name}]")
        print(f"      延迟 P50/P95/P99: {stats['latency_p50']}s / {stats['latency_p95']}s / {stats['latency_p99']}s")
        print(f"      工具调用 mean/max: {stats['tool_calls_mean']} / {stats['tool_calls_max']}")
        print(f"      输出长度 mean: {stats['content_len_mean']} chars")
        print(f"      错误率: {stats['error_rate']}%")


# ============================================================
# main
# ============================================================
async def main():
    print('=' * 70)
    print('PHA v2 性能压测 - v2 真实延迟 / 工具调用 / 输出长度')
    print('=' * 70)

    results, total_elapsed = await run_all_benchmarks()
    report = generate_report(results, total_elapsed)
    print_report(report)

    # 保存报告
    report_path = Path('docs/Chinese/PERF_REPORT.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"summary": report["summary"], "by_agent": report["by_agent"]}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"\n  详细报告: {report_path}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
