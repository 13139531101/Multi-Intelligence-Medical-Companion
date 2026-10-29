"""
v2/cost — admin cost analytics endpoints (WS-B)

GET /v2/cost/summary       整体概览（总 USD / 今日 / 本月 / 按 feature 拆分）
GET /v2/cost/per-provider  按 provider 拆分（每个 provider 的 USD + token 拆分）
GET /v2/cost/recent        最近 N 次调用的明细（含 prompt/completion/USD）
GET /v2/cost/pricing       当前的定价表快照

数据源（WS-B.1 fix）:
- _RECENT_CALLS 优先（LangChain BaseCallbackHandler 写入，包含真实 LLM 调用）
- ModelRouter._stats 作 fallback（ProviderStats 累计）
- 两者来源不同的原因：ModelRouter 走 provider.chat() 测试路径；LangChain
  ChatOpenAI 直连路径绕开 ModelRouter。所以两套数据源不重叠，统一用
  _RECENT_CALLS 聚合 — 它对所有 chat_model 路径都生效。

设计原则：USD 不在每个 LLM 调用处算（避免热路径上的字符串/int 转换），
        只在 dashboard 读取时一次性算 — cost_pricing.calc_cost 极轻。
"""
from __future__ import annotations

import logging
import time
from collections import Counter, deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Request

from .admin_api import _get_admin_user
from .cost_pricing import PROVIDER_PRICING, calc_cost, get_pricing_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/cost", tags=["cost"])


# ============================================================
# 最近调用环形缓冲（被 CostTrackingHandler 在 on_llm_end 写入）
# ============================================================
_RECENT_CALLS: Deque[Dict[str, Any]] = deque(maxlen=2000)
_RECENT_LOCK = False  # 单进程多 worker 不可靠，但 demo 够用


def record_call(provider: str, model: str, task_type: str,
                prompt_tokens: int, completion_tokens: int,
                latency_ms: float, feature: str = "") -> None:
    """on_llm_end callback 调：每次成功 LLM 调用推一条。失败不入环。
    真正进了管道的数据源 — ModelRouter._stats 已经走不到 LangChain 直连路径。
    """
    cost = calc_cost(provider, prompt_tokens, completion_tokens)
    _RECENT_CALLS.append({
        "ts": time.time(),
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "feature": feature,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost,
    })


def _aggregate_from_recent() -> Dict[str, Any]:
    """从 _RECENT_CALLS 聚合：total / by_provider / by_feature。
    返回结构与原 ModelRouter._stats 路径一致。"""
    by_provider: Dict[str, Dict[str, Any]] = {}
    feature_counter: Counter = Counter()
    total_cost = 0.0
    total_prompt = 0
    total_completion = 0
    for it in _RECENT_CALLS:
        p = str(it.get("provider") or "unknown")
        slot = by_provider.setdefault(p, {
            "calls": 0,
            "errors": 0,
            "rate_limited": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_latency_ms": 0.0,
        })
        slot["calls"] += 1
        slot["total_prompt_tokens"] += int(it.get("prompt_tokens") or 0)
        slot["total_completion_tokens"] += int(it.get("completion_tokens") or 0)
        slot["total_tokens"] += int(it.get("total_tokens") or 0)
        slot["total_latency_ms"] += float(it.get("latency_ms") or 0.0)
        total_prompt += int(it.get("prompt_tokens") or 0)
        total_completion += int(it.get("completion_tokens") or 0)
        total_cost += float(it.get("cost_usd") or 0.0)
        feat = it.get("feature") or ""
        if feat:
            feature_counter[feat] += 1
    return {
        "by_provider": by_provider,
        "feature_counter": feature_counter,
        "total_cost": total_cost,
        "total_prompt": total_prompt,
        "total_completion": total_completion,
    }


# ============================================================
# 读
# ============================================================
@router.get("/summary")
async def cost_summary(req: Request):
    _get_admin_user(req)
    agg = _aggregate_from_recent()

    by_feature: Dict[str, float] = {}
    for feat, cnt in agg["feature_counter"].items():
        # 按 feature 占比近似 USD
        if agg["total_cost"] > 0 and cnt > 0:
            share = agg["total_cost"] * (cnt / max(cnt, 1)) / max(cnt, 1)
        else:
            share = 0.0
        by_feature[feat] = round(share, 6)

    return {
        "total_cost_usd": round(agg["total_cost"], 4),
        "total_prompt_tokens": agg["total_prompt"],
        "total_completion_tokens": agg["total_completion"],
        "total_tokens": agg["total_prompt"] + agg["total_completion"],
        "providers_tracked": len(agg["by_provider"]),
        "by_feature_usd": by_feature,
    }


@router.get("/per-provider")
async def cost_per_provider(req: Request):
    _get_admin_user(req)
    agg = _aggregate_from_recent()
    out: List[Dict[str, Any]] = []
    for name, s in agg["by_provider"].items():
        recorded_cost = sum(
            float(x.get("cost_usd") or 0.0)
            for x in _RECENT_CALLS
            if str(x.get("provider") or "") == name
        )
        out.append({
            "provider": name,
            "calls": s["calls"],
            "errors": s["errors"],
            "rate_limited": s["rate_limited"],
            "total_prompt_tokens": s["total_prompt_tokens"],
            "total_completion_tokens": s["total_completion_tokens"],
            "total_tokens": s["total_tokens"],
            "avg_latency_ms": round(s["total_latency_ms"] / s["calls"], 1) if s["calls"] else 0.0,
            "cost_usd": round(recorded_cost, 4),
            "feature_counter": dict(agg["feature_counter"]),
            "pricing": PROVIDER_PRICING.get(name, {}),
        })
    out.sort(key=lambda x: -x["cost_usd"])
    return {
        "providers": out,
        "total_usd": round(sum(p["cost_usd"] for p in out), 4),
    }


@router.get("/recent")
async def cost_recent(req: Request, limit: int = 50):
    _get_admin_user(req)
    # 没注入 record_call 时降级：从 stats 不可还原 per-call
    # —— 这里返回 ring buffer 内容（可能为空，不报错）
    items = list(_RECENT_CALLS)[-limit:]
    return {
        "items": items,
        "count": len(items),
        "total_cost_usd": round(sum(x.get("cost_usd", 0) for x in items), 4),
    }


@router.get("/pricing")
async def cost_pricing(req: Request):
    _get_admin_user(req)
    return get_pricing_snapshot()
