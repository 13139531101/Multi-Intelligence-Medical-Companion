"""
阶段48-p3: v2 主链路的 rerank（重排序）。

背景
----
v2 主链路（rag.py → magnetic_rag.py）此前是**纯向量检索**：pgvector cosine
top-K 直接当最终结果。而 HealthAdvisor 那套栈（mcpserver/knowledge_tool.py）
早已接入 DashScope `gte-rerank-v2`，实测 MRR 0.6167 → 1.0。

本模块把同样的能力搬到 v2，且**不本地部署任何模型** —— 全部走 DashScope
HTTP API（cross-encoder 本地推理需要 torch + 数百 MB 权重，与本项目"不本地
部署模型"的约束冲突）。

设计要点
--------
- 复用栈 B `_dashscope_rerank` 的**同一 API 契约**（同样的 URL / payload 形状），
  但改成 async（v2 全链路是 async，同步 httpx.Client 会阻塞事件循环）。
- **全程可降级**：没配 API key / 网络失败 / 超时 / 返回格式异常 → 一律返回
  None，调用方退回原始向量序。rerank 是增强项，绝不能让它拖垮检索。
- 只用 `top_k * 2` 候选去 rerank（向量已粗排过），控制延迟与成本。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "gte-rerank-v2"
DEFAULT_RERANK_BASE = "https://dashscope.aliyuncs.com"
DEFAULT_RERANK_TIMEOUT = 8  # 秒；失败就降级，不值得让用户等


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


def rerank_enabled() -> bool:
    """RERANK_ENABLED 显式关掉时直接跳过；没配 key 时也会在下面静默跳过。"""
    return _env_bool("RERANK_ENABLED", True)


def _api_key() -> str:
    # 与栈 B 的 _dashscope_api_key 保持一致的回退链
    return (
        (os.getenv("DASHSCOPE_API_KEY") or "").strip()
        or (os.getenv("RERANK_API_KEY") or "").strip()
        or (os.getenv("EMBEDDING_API_KEY") or "").strip()
        or (os.getenv("OPENAI_API_KEY") or "").strip()
    )


def _rerank_url() -> str:
    base = (os.getenv("RERANK_API_BASE") or "").strip() or DEFAULT_RERANK_BASE
    return base.rstrip("/") + "/api/v1/services/rerank/text-rerank/text-rerank"


def _record(outcome: str, elapsed: float = 0.0, candidates: int = 0) -> None:
    """记录 rerank 指标。

    打到 `observability/metrics.py` 的 REGISTRY —— 那才是 /metrics 真正
    scrape 的注册表（api.py 里 observability 的 /metrics 路由先注册, 会遮蔽
    v2/monitoring.py 的同名路由）。指标是 best-effort, 任何异常都吞掉。
    """
    try:
        from ..observability.metrics import (
            RERANK_CANDIDATES, RERANK_LATENCY, RERANK_TOTAL,
        )

        RERANK_TOTAL.labels(outcome=outcome).inc()
        if elapsed > 0:
            RERANK_LATENCY.labels(outcome=outcome).observe(elapsed)
        if candidates > 0:
            RERANK_CANDIDATES.observe(candidates)
    except Exception:  # noqa: BLE001 — 指标不能影响主链路
        pass


def _build_payload(model: str, query: str, docs: List[str], top_n: int) -> Dict[str, Any]:
    """qwen3-rerank 用扁平入参，gte-rerank 系列用 input/parameters 嵌套 —— 与栈 B 一致。"""
    if model == "qwen3-rerank":
        return {"model": model, "query": query, "documents": docs, "top_n": top_n}
    return {
        "model": model,
        "input": {"query": query, "documents": docs},
        "parameters": {"return_documents": False, "top_n": top_n},
    }


def note_skipped() -> None:
    """给"候选不足、根本没进 rerank"的调用方记账。

    magnetic_rag._rerank_chunks 在候选 <2 时会直接 return，连 rerank() 都不调。
    那样 /metrics 上 pha_rerank_total 会**一条都没有**，看起来像"指标没接上"，
    实际是"压根没轮到 rerank"。记一笔 skipped 就能把这两种情况区分开。
    """
    _record("skipped")


async def rerank(
    query: str,
    documents: Sequence[str],
    *,
    top_n: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Optional[List[Tuple[int, float]]]:
    """
    对候选文档重排序。

    Returns:
        成功 → [(原始下标, relevance_score), ...]，按相关性降序，长度为 top_n
        跳过/失败 → None（调用方保持原有顺序）

    任何异常都被吞掉并记 warning —— rerank 挂掉不能让检索挂掉。
    """
    if not rerank_enabled():
        _record("skipped")
        return None

    q = (query or "").strip()
    docs = [str(d or "").strip() for d in (documents or [])]
    # 少于 2 篇没有重排意义；空文档过滤掉但下标要保留
    if not q or len([d for d in docs if d]) < 2:
        _record("skipped")
        return None

    api_key = _api_key()
    if not api_key:
        logger.debug("[rerank] 未配置 DASHSCOPE_API_KEY，跳过 rerank（保持向量序）")
        _record("skipped")
        return None

    m = (model or os.getenv("RERANK_MODEL") or "").strip() or DEFAULT_RERANK_MODEL
    try:
        tn = int(top_n) if top_n else len(docs)
    except (TypeError, ValueError):
        tn = len(docs)
    tn = max(1, min(tn, len(docs)))

    try:
        secs = float(timeout if timeout is not None else os.getenv("RERANK_TIMEOUT") or DEFAULT_RERANK_TIMEOUT)
    except (TypeError, ValueError):
        secs = float(DEFAULT_RERANK_TIMEOUT)

    payload = _build_payload(m, q, docs, tn)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    t0 = time.monotonic()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(secs, connect=secs)) as client:
            resp = await client.post(_rerank_url(), headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = ((data or {}).get("output") or {}).get("results")
        if not isinstance(results, list) or not results:
            logger.warning("[rerank] 返回格式异常，降级为向量序")
            _record("error", time.monotonic() - t0, len(docs))
            return None

        pairs: List[Tuple[int, float]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(docs):
                continue
            try:
                score = float(item.get("relevance_score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            pairs.append((idx, score))

        if not pairs:
            _record("error", time.monotonic() - t0, len(docs))
            return None
        pairs.sort(key=lambda p: p[1], reverse=True)
        logger.info("[rerank] %s 重排 %d 篇 → 保留 %d 篇", m, len(docs), len(pairs))
        _record("success", time.monotonic() - t0, len(docs))
        return pairs

    except Exception as e:  # noqa: BLE001 — 任何失败都必须降级，不能上抛
        logger.warning("[rerank] 调用失败，降级为向量序: %s", e)
        _record("error", time.monotonic() - t0, len(docs))
        return None
