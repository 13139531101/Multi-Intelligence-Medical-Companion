"""
LLM 定价常量表 —— WS-B

USD per 1k tokens. 来源：各 provider 官方公开报价（2024-Q4~2025-Q3 区间，
小数点后 6 位是精度需要，不是真定价精度——按 read 端显示即可）。

覆盖 PHA 项目实际接的 provider：deepseek（主）/ dashscope（兜底）/
openai（兼容模式）/ anthropic / moonshot / ollama（本地，免费）。

可被 PHA_PRICING_JSON 环境变量整体覆盖（admin 改价的逃生舱）：
    export PHA_PRICING_JSON='{"deepseek":{"input_per_1k":0.00014,"output_per_1k":0.00028}}'
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


# 公开默认表（USD / 1k tokens）
PROVIDER_PRICING: Dict[str, Dict[str, float]] = {
    # DeepSeek-V3 (官方价, cache miss)
    "deepseek": {
        "input_per_1k": 0.00014,   # $0.14 / 1M
        "output_per_1k": 0.00028,  # $0.28 / 1M
    },
    # 通义千问 DashScope (qwen-plus 公开价)
    "dashscope": {
        "input_per_1k": 0.0008,
        "output_per_1k": 0.002,
    },
    # OpenAI gpt-4o-mini (公开价, reference)
    "openai": {
        "input_per_1k": 0.00015,
        "output_per_1k": 0.0006,
    },
    # Anthropic claude-3-5-sonnet (公开价, reference)
    "anthropic": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    },
    # Moonshot kimi (公开价, reference)
    "moonshot": {
        "input_per_1k": 0.001,
        "output_per_1k": 0.002,
    },
    # Ollama 本地模型：免费，象征性 0
    "ollama": {
        "input_per_1k": 0.0,
        "output_per_1k": 0.0,
    },
}


def _load_env_override() -> None:
    """从 PHA_PRICING_JSON env 整体覆盖（admin 改价或私有部署用）"""
    raw = os.getenv("PHA_PRICING_JSON", "").strip()
    if not raw:
        return
    try:
        override = json.loads(raw)
        if not isinstance(override, dict):
            logger.warning("[cost] PHA_PRICING_JSON 不是 dict，忽略")
            return
        for prov, v in override.items():
            if not isinstance(v, dict):
                continue
            if prov not in PROVIDER_PRICING:
                PROVIDER_PRICING[prov] = {}
            for k in ("input_per_1k", "output_per_1k"):
                if k in v and isinstance(v[k], (int, float)):
                    PROVIDER_PRICING[prov][k] = float(v[k])
        logger.info(f"[cost] PHA_PRICING_JSON 已覆盖: {sorted(override.keys())}")
    except Exception as e:
        logger.warning(f"[cost] PHA_PRICING_JSON 解析失败: {e}")


_load_env_override()


def calc_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    """算一笔 LLM 调用的 USD 成本。未知 provider 返回 0（避免抛错污染 stats）。"""
    p = PROVIDER_PRICING.get(provider)
    if not p:
        return 0.0
    cost = (prompt_tokens / 1000.0) * p.get("input_per_1k", 0.0) \
         + (completion_tokens / 1000.0) * p.get("output_per_1k", 0.0)
    return round(cost, 6)


def get_pricing_snapshot() -> Dict[str, Any]:
    """返回当前生效的定价表（admin dashboard / API 用）"""
    return {
        "providers": dict(PROVIDER_PRICING),
        "source": "env" if os.getenv("PHA_PRICING_JSON") else "default",
    }
