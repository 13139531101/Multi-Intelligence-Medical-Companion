"""
v2/config — admin runtime configuration endpoints (WS-D)

GET  /v2/config/get    — full snapshot
POST /v2/config/update — PATCH-style: {"cache_ttl_sec": 7200, ...}
POST /v2/config/reset  — 全部回到 env 默认

写入流程：setter 同步改内存 + 异步写 Postgres（pha_runtime_config 表）
读取：直接走 RuntimeConfig 单例
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional

from .admin_api import _get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/config", tags=["config"])


# ============================================================
# 允许运行时调整的 key 集合（白名单防止 admin 误改无关 env）
# ============================================================
ALLOWED_KEYS = {
    "cache_similarity_threshold",
    "cache_ttl_sec",
    "cache_max_size",
    "fallback_chain",
    "task_routing",
}


class UpdateBody(BaseModel):
    values: Dict[str, Any]


# ============================================================
# 读
# ============================================================
@router.get("/get")
async def get_config(req: Request):
    _get_admin_user(req)
    from .runtime_config import get_runtime_config
    rc = get_runtime_config()
    snap = rc.snapshot()
    # 加每个 key 的 version（用于 audit 展示）
    return {
        "values": snap,
        "versions": {k: rc.version(k) for k in snap},
        "allowed_keys": sorted(ALLOWED_KEYS),
    }


# ============================================================
# 写
# ============================================================
@router.post("/update")
async def update_config(body: UpdateBody, req: Request):
    _get_admin_user(req)
    from .runtime_config import get_runtime_config
    rc = get_runtime_config()

    rejected = []
    for k, v in body.values.items():
        if k not in ALLOWED_KEYS:
            rejected.append(k)
            continue
        # 类型快校验
        if k in ("cache_ttl_sec", "cache_max_size"):
            if not isinstance(v, int) or v <= 0:
                raise HTTPException(status_code=400, detail=f"{k} must be positive int")
        if k == "cache_similarity_threshold":
            if not isinstance(v, (int, float)) or not (0 <= v <= 1):
                raise HTTPException(status_code=400, detail=f"{k} must be 0..1")
        if k == "fallback_chain":
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise HTTPException(status_code=400, detail=f"{k} must be list[str]")
        if k == "task_routing":
            if not isinstance(v, dict):
                raise HTTPException(status_code=400, detail=f"{k} must be dict")
        rc.set(k, v)

    # 关键钩子：把 cache_ttl_sec / cache_max_size 同步推到 live cache 实例
    if "cache_ttl_sec" in body.values or "cache_max_size" in body.values:
        try:
            from .semantic_cache import get_cache
            cache = get_cache()
            if cache is not None:
                if "cache_ttl_sec" in body.values:
                    cache.set_ttl(int(body.values["cache_ttl_sec"]))
                if "cache_max_size" in body.values:
                    cache.set_max_size(int(body.values["cache_max_size"]))
        except Exception as e:
            logger.warning(f"[config] live cache update failed: {e}")

    return {
        "ok": True,
        "rejected": rejected,
        "new_versions": {k: rc.version(k) for k in body.values if k in ALLOWED_KEYS},
    }


# ============================================================
# 重置
# ============================================================
@router.post("/reset")
async def reset_config(req: Request):
    _get_admin_user(req)
    from .runtime_config import get_runtime_config
    rc = get_runtime_config()
    rc.reset_all()
    return {"ok": True, "message": "reset to env defaults (and cleared Postgres rows)"}
