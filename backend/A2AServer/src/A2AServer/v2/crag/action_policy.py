"""
PHA v2 CRAG Action Policy — 三分支决策

根据 LLM 评估的 is_relevant 和 score，决定：
- CORRECT   : 直接使用本地检索结果
- AMBIGUOUS : 混合 web 搜索
- INCORRECT : 切换到纯 web 搜索

阈值通过环境变量配置：
- PHA_CRAG_CORRECT_THRESHOLD   = 0.75  (is_relevant=True 且 score >= 此值 → CORRECT)
- PHA_CRAG_INCORRECT_THRESHOLD = 0.30  (is_relevant=False 且 score < 此值 → INCORRECT)
- 其他情况 → AMBIGUOUS
"""
from __future__ import annotations

import os
from typing import Literal

Action = Literal["CORRECT", "AMBIGUOUS", "INCORRECT"]


# 默认阈值（医疗场景偏保守：宁可多搜索，不要漏掉重要信息）
DEFAULT_THRESHOLDS = {
    "correct": float(os.getenv("PHA_CRAG_CORRECT_THRESHOLD", "0.75")),
    "incorrect": float(os.getenv("PHA_CRAG_INCORRECT_THRESHOLD", "0.30")),
}


def decide_action(
    score: float,
    is_relevant: bool,
    thresholds: dict | None = None,
) -> Action:
    """
    根据检索评估结果决定 CRAG 行动。

    决策逻辑（医疗场景优先安全）：
    - CORRECT   : is_relevant=True AND score >= correct_threshold
                  本地结果足够好，无需外部补充
    - INCORRECT : is_relevant=False AND score < incorrect_threshold
                  本地结果完全不相关，切换 web 搜索
    - AMBIGUOUS : 其他情况（部分相关，需要混合补充）
                  混合本地 + web，提升召回率

    Args:
        score: evaluate_chunks 返回的置信度分数 [0.0, 1.0]
        is_relevant: evaluate_chunks 返回的相关性判断
        thresholds: 可选，覆盖默认阈值

    Returns:
        Action: CORRECT | AMBIGUOUS | INCORRECT
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    correct_thresh = thresholds["correct"]
    incorrect_thresh = thresholds["incorrect"]

    if is_relevant and score >= correct_thresh:
        return "CORRECT"
    if not is_relevant and score < incorrect_thresh:
        return "INCORRECT"
    return "AMBIGUOUS"


def action_to_confidence_level(action: Action) -> str:
    """将 action 映射为用户可见的置信度标签"""
    mapping = {
        "CORRECT": "high",
        "AMBIGUOUS": "medium",
        "INCORRECT": "low",
    }
    return mapping.get(action, "unknown")


def action_to_source_mix(action: Action) -> str:
    """将 action 映射为 source_mix 标签"""
    mapping = {
        "CORRECT": "local",
        "AMBIGUOUS": "mixed",
        "INCORRECT": "web",
    }
    return mapping.get(action, "none")
