"""
v2/routing/distribution — agent 路由分布聚合 (WS-C)

GET /v2/routing/distribution
返回：
  {
    "total": N,            # 缓冲中路由事件总数
    "by_agent": {agent: count, ...},
    "by_layer": {layer: count, ...},
    "by_agent_layer": {agent: {layer: count, ...}, ...},
    "recent": [...],       # 最近 20 条
    "buffer_size": N
  }

数据源: bridge._ROUTING_EVENTS（in-memory deque，PHA_ROUTING_BUFFER_SIZE 控制大小）

注意：
- 这是同进程内 in-memory 状态。多 worker 下需要 redis/hazelcast；当前 demo
  阶段单 uvicorn worker 够用。
- 进程重启会清空；监控角度没问题（监控关心的是当下）
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict

from fastapi import APIRouter, Request

from .admin_api import _get_admin_user
from .bridge import _ROUTING_EVENTS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/routing", tags=["routing"])


@router.get("/distribution")
async def routing_distribution(req: Request):
    _get_admin_user(req)
    items = list(_ROUTING_EVENTS)
    total = len(items)

    by_agent: Counter = Counter()
    by_layer: Counter = Counter()
    by_agent_layer: Dict[str, Counter] = {}

    for ev in items:
        ag = str(ev.get("agent") or "unknown")
        ly = ev.get("layer")
        ly_key = f"layer{int(ly)}" if ly is not None else "unknown"
        by_agent[ag] += 1
        by_layer[ly_key] += 1
        by_agent_layer.setdefault(ag, Counter())[ly_key] += 1

    recent = items[-20:]  # deque[-20:] 实际是 last 20（按插入顺序）

    return {
        "total": total,
        "by_agent": dict(by_agent),
        "by_layer": dict(by_layer),
        "by_agent_layer": {k: dict(v) for k, v in by_agent_layer.items()},
        "recent": recent,
        "buffer_size": _ROUTING_EVENTS.maxlen or 0,
    }
