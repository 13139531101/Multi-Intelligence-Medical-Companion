"""给 v2 检索链路做分阶段计时（临时脚本，验证完可删）。

消融实验显示 multi_hop+rerank 平均 19.7s、p95 57s —— 生产不可用。但慢在哪
不能靠猜：这条链路上有 4~5 次 LLM 往返 + 若干次 embedding + 一次 rerank HTTP，
必须逐段计时才能知道该砍谁。

做法: 用猴子补丁把 magnetic_rag 内部每个阶段函数包一层计时, 不动源码。
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, "/app")

import A2AServer.v2.magnetic_rag as mr  # noqa: E402

TIMINGS: list[tuple[str, float]] = []


def _wrap(mod, name, label=None):
    fn = getattr(mod, name, None)
    if fn is None:
        return
    label = label or name
    if asyncio.iscoroutinefunction(fn):
        async def wrapper(*a, **kw):
            t0 = time.perf_counter()
            try:
                return await fn(*a, **kw)
            finally:
                TIMINGS.append((label, (time.perf_counter() - t0) * 1000))
    else:
        def wrapper(*a, **kw):
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                TIMINGS.append((label, (time.perf_counter() - t0) * 1000))
    setattr(mod, name, wrapper)


for _n in (
    "should_retrieve",
    "rewrite_query",
    "detect_record_types",
    "retrieve_chunks",
    "retrieve_chunks_by_type",
    "evaluate_chunks",
    "multi_hop_rag_search",
    "magnetic_rag_search",
):
    _wrap(mr, _n)

# rerank 与 KG 扩展在别的模块
try:
    import A2AServer.v2.rerank as rr
    _wrap(rr, "rerank")
except Exception as e:  # noqa: BLE001
    print(f"warn: rerank wrap failed: {e}")

try:
    import A2AServer.v2.knowledge_graph as kg
    _wrap(kg, "graph_expand_entities")
    _wrap(kg, "get_chunks_for_entities")
except Exception as e:  # noqa: BLE001
    print(f"warn: kg wrap failed: {e}")

try:
    import A2AServer.v2.rag as rag
    _wrap(rag, "index_document")
except Exception as e:  # noqa: BLE001
    print(f"warn: rag wrap failed: {e}")


QUERIES = [
    "我最近血压控制得怎么样？平时吃的什么药？",
    "我的血糖和糖尿病用药情况如何？",
    "我的心电图和血脂有什么问题吗？",
]


async def main():
    user_id = os.getenv("PROFILE_USER", "rag_eval_user")
    for q in QUERIES:
        TIMINGS.clear()
        t0 = time.perf_counter()
        r = await mr.multi_hop_rag_search(query=q, user_id=user_id, top_k=5)
        total = (time.perf_counter() - t0) * 1000
        print(f"\n=== {q}")
        print(f"    total {total:.0f} ms | chunks={len(r.chunks)} score={r.score} "
              f"relevant={r.is_relevant} rewrite={r.rewrite_count}")
        agg: dict[str, list[float]] = {}
        for name, ms in TIMINGS:
            agg.setdefault(name, []).append(ms)
        for name, xs in sorted(agg.items(), key=lambda kv: -sum(kv[1])):
            print(f"      {name:26s} n={len(xs):2d}  total={sum(xs):7.0f}ms  "
                  f"max={max(xs):7.0f}ms")
        accounted = sum(ms for _, ms in TIMINGS)
        print(f"      {'(以上合计)':26s}      {accounted:7.0f}ms  "
              f"未计入={total - accounted:.0f}ms")


asyncio.run(main())
