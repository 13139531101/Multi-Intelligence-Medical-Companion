"""Agent 行为评测 CLI 入口 —— WS-A

不依赖 RAG 模式（multi_hop/single_hop/rerank），独立跑：
- 5 个 category 各自的 metric
- 每个 case 跑一次 /api/copilotkit，黑盒测

认证：默认先用 PROBE_USER/PROBE_PASS 登录拿 token；用 admin dev-token
不靠谱，因为 dev-token 通常只能调管理端点，/api/copilotkit 是用户端。
和 agui_smoke.py 一样用业务账号。

用法:
    python tests/performance/agent_eval.py \
        --dataset tests/performance/agent_eval_dataset.json \
        --categories routing tool_selection \
        --limit 5 \
        --output /tmp/eval_smoke.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

# 同目录
sys.path.insert(0, str(Path(__file__).parent))
from agent_eval_common import (  # noqa: E402
    AgentEvalCase,
    call_agui,
    load_agent_cases,
    routing_metrics,
    tool_metrics,
    abstention_metrics,
    citation_metrics,
    memory_metrics,
)


def _http_post(url: str, body: dict, token: str | None = None, timeout: int = 60) -> tuple[int, str]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _get_token(base: str, username: str, password: str) -> str:
    status, body = _http_post(f"{base}/auth/login", {"username": username, "password": password})
    if status != 200:
        raise SystemExit(f"登录失败 HTTP {status}: {body[:200]}")
    return json.loads(body)["access_token"]


# ============================================================
# 逐 case 跑
# ============================================================
async def _run_one(case: AgentEvalCase, base: str, token: str) -> dict:
    """跑一个 case，返回扁平 record（不分类）"""
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: call_agui(
            base_url=base,
            message=case.query,
            token=token,
            conversation_history=case.conversation_history or None,
            metadata={"category": case.category, "case_id": case.id, **(case.metadata or {})},
        ),
    )

    actual_agent = response.get("routing", {}).get("agent")
    actual_layer = response.get("routing", {}).get("layer")
    actual_tool_names = [tc["name"] for tc in response.get("tool_calls", [])]
    abstained = response.get("abstained", False)
    citation_count = response.get("citation_count", 0)
    text = response.get("text", "")
    elapsed_sec = response.get("elapsed_sec", 0.0)

    record = {
        "id": case.id,
        "category": case.category,
        "query": case.query,
        "elapsed_sec": elapsed_sec,
        # 通用
        "error": response.get("error"),
        "text_len": len(text),
        # routing
        "expected_agent": case.expected_agent,
        "top_k_acceptable": case.top_k_acceptable,
        "actual_agent": actual_agent,
        "layer": actual_layer,
        "pass_top1": actual_agent == case.expected_agent if case.expected_agent else False,
        "pass_topk": (
            actual_agent in case.top_k_acceptable
            if case.top_k_acceptable
            else (actual_agent == case.expected_agent if case.expected_agent else False)
        ),
        # tool
        "expected_tools": case.expected_tools,
        "forbidden_tools": case.forbidden_tools,
        "actual_tools": actual_tool_names,
        # abstention
        "must_abstain": case.must_abstain,
        "abstained": abstained,
        # citation
        "expected_citation_count": case.expected_citation_count,
        "citation_count": citation_count,
        # memory
        "memory_recall_queries": case.memory_recall_queries,
        "history_used": bool(case.conversation_history),
        # debug
        "text_preview": text[:120],
    }
    return record


# ============================================================
# 汇总
# ============================================================
def _summarize_category(cat: str, per_case: list[dict]) -> dict:
    if cat == "routing":
        m = routing_metrics(per_case)
        m["per_case"] = [
            {
                "id": c["id"],
                "expected": c["expected_agent"],
                "actual": c["actual_agent"],
                "layer": c["layer"],
                "pass_top1": c["pass_top1"],
                "pass_topk": c["pass_topk"],
            }
            for c in per_case
        ]
        return m
    if cat == "tool_selection":
        m = tool_metrics(per_case)
        m["per_case"] = [
            {
                "id": c["id"],
                "expected": c["expected_tools"],
                "actual": c["actual_tools"],
                "forbidden_hit": [t for t in c["actual_tools"] if t in (c["forbidden_tools"] or [])],
            }
            for c in per_case
        ]
        return m
    if cat == "abstention":
        m = abstention_metrics(per_case)
        m["per_case"] = [
            {
                "id": c["id"],
                "must_abstain": c["must_abstain"],
                "abstained": c["abstained"],
            }
            for c in per_case
        ]
        return m
    if cat == "citation":
        m = citation_metrics(per_case)
        m["per_case"] = [
            {
                "id": c["id"],
                "expected": c["expected_citation_count"],
                "actual": c["citation_count"],
            }
            for c in per_case
        ]
        return m
    if cat == "multi_turn_memory":
        m = memory_metrics(per_case)
        m["per_case"] = [
            {
                "id": c["id"],
                "history_used": c["history_used"],
                "hit": any(kw in c.get("text_preview", "") for kw in c["memory_recall_queries"]),
            }
            for c in per_case
        ]
        return m
    return {"cases": len(per_case), "per_case": per_case}


# ============================================================
# main
# ============================================================
async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=["routing", "tool_selection", "abstention", "citation", "multi_turn_memory"],
        help="要跑的 category 集合（默认全部 5 个）",
    )
    parser.add_argument("--limit", type=int, default=0, help="每 category 最多跑多少条 (0=全部)")
    parser.add_argument("--base", default=os.getenv("PROBE_BASE") or "http://localhost:13002")
    parser.add_argument("--user", default=os.getenv("PROBE_USER") or "probe_agui_1")
    parser.add_argument("--password", default=os.getenv("PROBE_PASS") or "ProbePass123!")
    parser.add_argument("--output", default="")
    parser.add_argument("--concurrency", type=int, default=1, help="并发跑多少 case (默认 1 串行)")
    args = parser.parse_args()

    cases = load_agent_cases(args.dataset)
    print(f"[eval] 加载 {len(cases)} 条用例", file=sys.stderr)

    # 按 category 过滤
    wanted = set(args.categories)
    cases = [c for c in cases if c.category in wanted]
    if args.limit > 0:
        cases = cases[: args.limit]
    print(f"[eval] 实际跑 {len(cases)} 条 (categories={sorted(wanted)})", file=sys.stderr)

    # 登录拿 token
    token = _get_token(args.base, args.user, args.password)
    print(f"[eval] 登录成功 -> {args.base}", file=sys.stderr)

    # 并发或串行
    t0 = time.perf_counter()
    if args.concurrency <= 1:
        records: list[dict] = []
        for i, c in enumerate(cases, 1):
            r = await _run_one(c, args.base, token)
            records.append(r)
            if i % 5 == 0 or i == len(cases):
                print(f"  [{i}/{len(cases)}] {c.id} → {r.get('actual_agent') or '?'} ({r['elapsed_sec']:.1f}s)", file=sys.stderr)
    else:
        sem = asyncio.Semaphore(args.concurrency)

        async def _bounded(c: AgentEvalCase) -> dict:
            async with sem:
                return await _run_one(c, args.base, token)

        records = await asyncio.gather(*[_bounded(c) for c in cases])
    total_elapsed = time.perf_counter() - t0

    # 按 category 聚合
    by_category: dict[str, list[dict]] = {}
    for r in records:
        by_category.setdefault(r["category"], []).append(r)

    summary_per_cat: dict[str, dict] = {}
    for cat, items in by_category.items():
        summary_per_cat[cat] = _summarize_category(cat, items)

    # 全局统计
    all_pass: list[bool] = []
    for cat, items in by_category.items():
        for r in items:
            if cat == "routing":
                all_pass.append(r["pass_top1"])
            elif cat == "tool_selection":
                all_pass.append(not (set(r["actual_tools"]) & set(r["forbidden_tools"])))
            elif cat == "abstention":
                all_pass.append(r["abstained"] == r["must_abstain"])
            elif cat == "citation":
                all_pass.append(r["citation_count"] >= r["expected_citation_count"])
            elif cat == "multi_turn_memory":
                all_pass.append(any(kw in r.get("text_preview", "") for kw in r["memory_recall_queries"]))

    latencies = [r["elapsed_sec"] for r in records if r.get("elapsed_sec") is not None]

    summary = {
        "dataset": str(args.dataset),
        "ran_at": datetime.utcnow().isoformat() + "Z",
        "cases": len(records),
        "categories": sorted(by_category.keys()),
        "total_elapsed_sec": round(total_elapsed, 2),
        "concurrency": args.concurrency,
        "latency": {
            "avg_sec": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p50_sec": round(statistics.median(latencies), 2) if latencies else 0.0,
            "p95_sec": (
                round(statistics.quantiles(latencies, n=20)[18], 2)
                if len(latencies) >= 20
                else (round(max(latencies), 2) if latencies else 0.0)
            ),
            "max_sec": round(max(latencies), 2) if latencies else 0.0,
        },
        "by_category": summary_per_cat,
        "overall_pass_rate": round(sum(all_pass) / len(all_pass), 4) if all_pass else 0.0,
    }

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[eval] 已写入 {args.output}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main_async())
