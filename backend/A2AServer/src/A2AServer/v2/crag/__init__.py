"""
PHA v2 Corrective RAG (CRAG) — 阶段48-CRAG

CRAG 三分支决策：
- CORRECT  : 本地检索结果足够好，直接使用
- AMBIGUOUS: 本地结果部分相关，混合 web 搜索
- INCORRECT: 本地结果不相关，切换到纯 web 搜索

模块结构：
- action_policy : 三分支决策逻辑
- web_search    : WebSearchProvider 抽象 + DuckDuckGo/Tavily/SerpApi 实现
- merge         : 本地 + web 混合上下文组装
"""
from .action_policy import decide_action, Action, DEFAULT_THRESHOLDS
from .web_search import WebSearchProvider, WebResult, get_web_search_provider
from .merge import MergedContext, merge_local_web

__all__ = [
    "decide_action", "Action", "DEFAULT_THRESHOLDS",
    "WebSearchProvider", "WebResult", "get_web_search_provider",
    "MergedContext", "merge_local_web",
]
