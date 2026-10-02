import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 本文件所在目录（rag_eval_common 就在旁边）
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from backend.HealthAdvisor.mcpserver import knowledge_tool as kt

# 阶段48-p4: 指标实现抽到 rag_eval_common，与 v2 评测共用（避免两边算法漂移）
from rag_eval_common import EvalCase, calc_metrics, first_hit_rank, load_cases  # noqa: F401


def run_search(
    mode: str,
    query: str,
    user_id: str,
    top_k: int,
    source_types: list[str],
    include_global: bool,
) -> tuple[list[dict[str, Any]], float]:
    start = time.perf_counter()
    if mode == "vector":
        os.environ["RAG_RERANK_ENABLED"] = "0"
        items = kt._rag_search(
            query=query,
            user_id=user_id,
            limit=top_k,
            source_types=source_types,
            include_global=include_global,
        )
    elif mode == "rerank":
        os.environ["RAG_RERANK_ENABLED"] = "1"
        items = kt._rag_search(
            query=query,
            user_id=user_id,
            limit=top_k,
            source_types=source_types,
            include_global=include_global,
        )
    elif mode == "fallback":
        items = kt._keyword_search_medical_kb(
            query=query,
            user_id=user_id,
            limit=top_k,
            include_global=include_global,
        )
    else:
        raise ValueError(f"未知模式: {mode}")
    cost_ms = (time.perf_counter() - start) * 1000
    return items, cost_ms


def summarize_mode(
    mode: str,
    cases: list[EvalCase],
    top_k: int,
    source_types: list[str],
    include_global: bool,
) -> dict[str, Any]:
    latencies: list[float] = []
    top_ids: list[list[str]] = []
    counts: list[int] = []
    for case in cases:
        items, cost_ms = run_search(
            mode=mode,
            query=case.query,
            user_id=case.user_id,
            top_k=top_k,
            source_types=source_types,
            include_global=include_global,
        )
        latencies.append(cost_ms)
        ids = [str(it.get("id", "")).strip() for it in items if str(it.get("id", "")).strip()]
        top_ids.append(ids[:top_k])
        counts.append(len(items))
    metrics = calc_metrics(top_ids, cases)
    return {
        "mode": mode,
        "cases": len(cases),
        "top_k": top_k,
        "avg_latency_ms": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(statistics.quantiles(latencies, n=20)[18], 3) if len(latencies) >= 20 else (round(max(latencies), 3) if latencies else 0.0),
        "avg_result_count": round(statistics.mean(counts), 3) if counts else 0.0,
        "recall_at_k": round(metrics["recall_at_k"], 4),
        "mrr": round(metrics["mrr"], 4),
        "hit_rate_at_k": round(metrics["hit_rate_at_k"], 4),
        "top_ids": top_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--user-id", default="")
    parser.add_argument("--source-types", nargs="*", default=["health_records", "visit_summaries", "medical_kb"])
    parser.add_argument("--include-global", action="store_true", default=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    top_k = max(1, min(int(args.top_k), 50))
    cases = load_cases(args.dataset, default_user_id=str(args.user_id or ""))
    result_vector = summarize_mode(
        mode="vector",
        cases=cases,
        top_k=top_k,
        source_types=list(args.source_types),
        include_global=bool(args.include_global),
    )
    result_rerank = summarize_mode(
        mode="rerank",
        cases=cases,
        top_k=top_k,
        source_types=list(args.source_types),
        include_global=bool(args.include_global),
    )
    result_fallback = summarize_mode(
        mode="fallback",
        cases=cases,
        top_k=top_k,
        source_types=list(args.source_types),
        include_global=bool(args.include_global),
    )

    rerank_gain = round(result_rerank["hit_rate_at_k"] - result_vector["hit_rate_at_k"], 4)
    summary = {
        "dataset": str(args.dataset),
        "cases": len(cases),
        "top_k": top_k,
        "vector": result_vector,
        "rerank": result_rerank,
        "fallback": result_fallback,
        "rerank_hit_rate_gain": rerank_gain,
    }

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
