"""v2 主链路 RAG 评测（阶段48-p4）。

与 rag_performance_test.py 的区别
--------------------------------
那份评的是**栈 B**（HealthAdvisor 的 MCP knowledge_tool，单跳向量检索）。
本文件评的是**栈 A**：v2 主链路 `magnetic_rag`，即
`detect_record_types → 多跳检索 → KG 扩展 → rerank → evaluate → 可选 rewrite`
这套带自反思的流程 —— 此前**没有任何指标**。

做四组消融，直接产出可写进简历的对比表：

    single_hop + vector   （改造前的等价形态）
    single_hop + rerank
    multi_hop  + vector
    multi_hop  + rerank   （改造后的默认形态）

标注口径
--------
按 **source_id**（业务 id，如健康记录 id）标注，而不是 rag_chunks.id ——
后者是自增主键，重新索引一次就全变，评测集没法稳定复用。

用法
----
    python tests/performance/rag_v2_eval.py \
        --dataset tests/performance/rag_v2_eval_dataset.json \
        --top-k 5 --output tests/performance/rag_v2_metrics.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _p in (PROJECT_ROOT, Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from rag_eval_common import EvalCase, calc_metrics, load_cases  # noqa: E402


def _import_magnetic_rag():
    """两种部署布局都要能跑：
      - 容器内: PYTHONPATH 含 /app, `A2AServer.v2` 直接可导入
      - 仓库内: backend/A2AServer/src 还没被 pip 安装, 走完整包路径
    """
    try:
        from A2AServer.v2 import magnetic_rag  # type: ignore
        return magnetic_rag
    except ImportError:
        from backend.A2AServer.src.A2AServer.v2 import magnetic_rag  # type: ignore
        return magnetic_rag


MODES = [
    ("single_hop_vector", "single", False),
    ("single_hop_rerank", "single", True),
    ("multi_hop_vector", "multi", False),
    ("multi_hop_rerank", "multi", True),
]


def _ranked_source_ids(result: Any, top_k: int) -> list[str]:
    """从 RetrievalResult 里按顺序取出 source_id（去重保序）"""
    out: list[str] = []
    seen: set[str] = set()
    for c in getattr(result, "chunks", []) or []:
        sid = str(getattr(c, "source_id", "") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
        if len(out) >= top_k:
            break
    return out


async def _run_one(mode: str, use_rerank: bool, case: EvalCase, top_k: int) -> tuple[list[str], float, dict]:
    # rerank.py 每次调用都重新读 env，所以这里直接开关即可
    os.environ["RERANK_ENABLED"] = "1" if use_rerank else "0"

    mr = _import_magnetic_rag()

    t0 = time.perf_counter()
    if mode == "single":
        result = await mr.magnetic_rag_search(query=case.query, user_id=case.user_id, top_k=top_k)
    else:
        result = await mr.multi_hop_rag_search(query=case.query, user_id=case.user_id, top_k=top_k)
    cost_ms = (time.perf_counter() - t0) * 1000

    info = {
        "is_relevant": getattr(result, "is_relevant", None),
        "score": getattr(result, "score", None),
        "rewrite_count": getattr(result, "rewrite_count", 0),
        "n_chunks": len(getattr(result, "chunks", []) or []),
    }
    return _ranked_source_ids(result, top_k), cost_ms, info


async def summarize_mode(
    mode_name: str,
    mode: str,
    use_rerank: bool,
    cases: list[EvalCase],
    top_k: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    top_ids: list[list[str]] = []
    eval_scores: list[float] = []
    relevant_flags: list[bool] = []

    for case in cases:
        try:
            ids, cost_ms, info = await _run_one(mode, use_rerank, case, top_k)
        except Exception as e:  # noqa: BLE001 — 单条失败不该中断整轮评测
            print(f"  [warn] {mode_name} 查询失败 ({case.query[:20]}): {e}", file=sys.stderr)
            ids, cost_ms, info = [], 0.0, {}
        latencies.append(cost_ms)
        top_ids.append(ids)
        if isinstance(info.get("score"), (int, float)):
            eval_scores.append(float(info["score"]))
        relevant_flags.append(bool(info.get("is_relevant")))

    metrics = calc_metrics(top_ids, cases)

    # 分类别拆分（local_hit / multi_hop / no_answer）
    by_category: dict[str, Any] = {}
    for cat in sorted({c.category for c in cases if c.category}):
        idx = [i for i, c in enumerate(cases) if c.category == cat]
        sub_ids = [top_ids[i] for i in idx]
        sub_cases = [cases[i] for i in idx]
        cm = calc_metrics(sub_ids, sub_cases)
        entry: dict[str, Any] = {
            "cases": len(idx),
            "recall_at_k": round(cm["recall_at_k"], 4),
            "mrr": round(cm["mrr"], 4),
        }
        if cat == "no_answer":
            # 这类 case **故意没有** relevant_ids，calc_metrics 会跳过它们，
            # recall/MRR 恒为 0 没有意义。真正该测的是"检索器会不会硬说有依据"，
            # 也就是 evaluate_chunks 的误报率 —— 越低越好。
            fp = sum(1 for i in idx if relevant_flags[i])
            entry["false_positive_rate"] = round(fp / len(idx), 4)
            entry["note"] = "recall/MRR 不适用（无标注），看 false_positive_rate"
        else:
            # 多跳/单跳都补一个 all_hit@k：relevant_ids 全部被召回才算命中。
            # 共用的 calc_metrics 只要求"命中任意一个"，会高估多跳的效果。
            labeled = [
                (sub_ids[j], sub_cases[j])
                for j in range(len(sub_cases))
                if sub_cases[j].relevant_ids
            ]
            all_hit = sum(
                1 for ids, c in labeled if set(c.relevant_ids).issubset(set(ids))
            )
            entry["all_hit_at_k"] = round(all_hit / len(labeled), 4) if labeled else 0.0
        by_category[cat] = entry

    return {
        "mode": mode_name,
        "cases": len(cases),
        "top_k": top_k,
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
        "p95_latency_ms": (
            round(statistics.quantiles(latencies, n=20)[18], 1)
            if len(latencies) >= 20
            else (round(max(latencies), 1) if latencies else 0.0)
        ),
        "avg_eval_score": round(statistics.mean(eval_scores), 3) if eval_scores else 0.0,
        "recall_at_k": round(metrics["recall_at_k"], 4),
        "mrr": round(metrics["mrr"], 4),
        "hit_rate_at_k": round(metrics["hit_rate_at_k"], 4),
        "by_category": by_category,
        "top_ids": top_ids,
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--user-id", default="")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--modes",
        nargs="*",
        default=[m[0] for m in MODES],
        help="要跑的消融组，默认全部",
    )
    args = parser.parse_args()

    top_k = max(1, min(int(args.top_k), 50))
    cases = load_cases(args.dataset, default_user_id=str(args.user_id or ""))

    results: dict[str, Any] = {}
    for mode_name, mode, use_rerank in MODES:
        if mode_name not in args.modes:
            continue
        print(f"[eval] 运行 {mode_name} …", file=sys.stderr)
        results[mode_name] = await summarize_mode(mode_name, mode, use_rerank, cases, top_k)

    # 增益对比：rerank 与 multi-hop 各自带来多少
    def _gain(a: str, b: str, key: str) -> float | None:
        if a in results and b in results:
            return round(results[a][key] - results[b][key], 4)
        return None

    def _cat_gain(a: str, b: str, cat: str, key: str) -> float | None:
        try:
            return round(
                results[a]["by_category"][cat][key]
                - results[b]["by_category"][cat][key],
                4,
            )
        except KeyError:
            return None

    summary = {
        "dataset": str(args.dataset),
        "cases": len(cases),
        "top_k": top_k,
        "results": results,
        "gains": {
            "rerank_mrr_gain_single": _gain("single_hop_rerank", "single_hop_vector", "mrr"),
            "rerank_mrr_gain_multi": _gain("multi_hop_rerank", "multi_hop_vector", "mrr"),
            "multi_hop_mrr_gain": _gain("multi_hop_rerank", "single_hop_rerank", "mrr"),
            "total_mrr_gain": _gain("multi_hop_rerank", "single_hop_vector", "mrr"),
            # 多跳的价值主要体现在"两个文档都要召回"，整体 MRR 会被 local_hit 稀释，
            # 所以单独把 multi_hop 这一类的 all_hit@k 拎出来看。
            "multi_hop_all_hit_gain_vs_single_rerank": _cat_gain(
                "multi_hop_rerank", "single_hop_rerank", "multi_hop", "all_hit_at_k"
            ),
            "rerank_all_hit_gain_multi": _cat_gain(
                "multi_hop_rerank", "multi_hop_vector", "multi_hop", "all_hit_at_k"
            ),
        },
    }

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
