"""RAG 评测公共件 —— 评测集加载 + recall@k / MRR / hit_rate@k。

阶段48-p4: 从 rag_performance_test.py 抽出来，让「栈 B（HealthAdvisor MCP）」
和「栈 A（v2 主链路 multi-hop + CRAG）」两套评测共用同一份指标实现，
避免两边算法漂移导致数字不可比。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EvalCase:
    query: str
    relevant_ids: list[str]
    user_id: str
    category: str = ""   # v2 评测集用来区分 local_hit / multi_hop / web_fallback


def load_cases(file_path: str, default_user_id: str) -> list[EvalCase]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"评测集文件不存在: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("评测集必须是 JSON 数组")
    cases: list[EvalCase] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query", "")).strip()
        if not query:
            continue
        rel_ids = row.get("relevant_ids", []) or []
        rel_ids = [str(x).strip() for x in rel_ids if str(x).strip()]
        uid = str(row.get("user_id", "")).strip() or default_user_id
        cases.append(EvalCase(
            query=query,
            relevant_ids=rel_ids,
            user_id=uid,
            category=str(row.get("category", "")).strip(),
        ))
    if not cases:
        raise ValueError("评测集为空，无法执行")
    return cases


def first_hit_rank(ids: list[str], relevant: set[str]) -> int:
    """第一个命中的名次（1-based）；未命中返回 0"""
    for idx, sid in enumerate(ids, start=1):
        if sid in relevant:
            return idx
    return 0


def calc_metrics(top_ids: list[list[str]], cases: list[EvalCase]) -> dict[str, float]:
    """recall@k / MRR / hit_rate@k（只统计有标注的 case）"""
    if not top_ids:
        return {"recall_at_k": 0.0, "mrr": 0.0, "hit_rate_at_k": 0.0}
    labeled = 0
    hit = 0
    rr_total = 0.0
    for ids, case in zip(top_ids, cases):
        relevant = set(case.relevant_ids)
        if not relevant:
            continue
        labeled += 1
        rank = first_hit_rank(ids, relevant)
        if rank > 0:
            hit += 1
            rr_total += 1.0 / rank
    if labeled == 0:
        return {"recall_at_k": 0.0, "mrr": 0.0, "hit_rate_at_k": 0.0}
    return {
        "recall_at_k": hit / labeled,
        "mrr": rr_total / labeled,
        "hit_rate_at_k": hit / labeled,
    }
