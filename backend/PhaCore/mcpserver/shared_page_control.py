"""PhaCore shared_page_control —— 「AI 操控页面」的页面操作工具集。

阶段 48-29 新建。

背景
----
前端 pageContract.js 定义了 10 个页面动作，但只有 4 个（setData / navigateTo /
openRecord / fillForm）有后端生产者。另外 6 个是**有消费者、没生产者**的死代码
—— 前端把接收端写好了，却没有任何工具会发出这些指令。本模块补上生产者。

为什么放在 PhaCore，而不是某个 agent 的 mcpserver/
-----------------------------------------------
路由是「一个请求只进一个 agent」。而「刷新页面」「弹个提示」这类操作跟领域无关
—— 用户问血压时落在 health_advisor，问档案时落在 health_records。所以 4 个
agent 都得有这套工具。PhaCore 正是「被多个 agent re-export 的共享工具集」的所在。

两条硬约束（改这个文件前先读）
----------------------------
1. **工具必须写成同步 `def`。** mcp_discover._extract_mcp_tools_from_source
   （:178-180）只认 ast.FunctionDef，**不认 AsyncFunctionDef** —— 写成 async
   会被静默漏掉，工具根本不会出现在列表里。
2. **绝不写 user_id 参数。** 页面操作是纯前端信号，跟用户身份无关；而
   _wrap_function_as_base_tool 会 register_tool_sig，只要签名里有 user_id，
   _inject_user_id_if_needed 就会往里塞一个值。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("PhaCoreSharedPageControl")

_OWNER_AGENT = "pha_core"
_READER_AGENTS = ("health_advisor", "health_records", "medication_reminder", "visit_summary")


# ============================================================
# 契约名字：pageContract.js 的**字面量复制**
# 前端改契约时，这里必须一起改（后端 import 不到 JS 常量）。
# ============================================================
_PAGE_ROUTER = "PageRouter"          # 全局路由代理，始终挂载
_CURRENT_PAGE = "CurrentPage"        # 页面无关名，4 个页面共同注册
_DASHBOARD = "Dashboard"
_HEALTH_RECORDS = "HealthRecordsPage"
_MEDICATION = "MedicationPage"

_PATH_DASHBOARD = "/v2/dashboard"
_PATH_HEALTH_RECORDS = "/v2/health-records"
_PATH_MEDICATION = "/v2/medication"


def _act(component: str, action: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """单个动作。bridge.py:687-693 会按 actions[] 顺序逐个扇出成 SSE 事件。"""
    return {"component": component, "action": action, "params": params or {}}


def _pu(actions: list, summary: str = "") -> Dict[str, Any]:
    """组装返回体。形状与 HealthRecordsManager/page_control_tool.py 的
    open_health_record 一致，bridge.py:668-681 两种写法都认，这里用 actions[]。"""
    payload: Dict[str, Any] = {"success": True, "page_update": {"actions": actions}}
    if summary:
        payload["page_update"]["summary"] = summary
    return payload


# ============================================================
# 归一化：让模型传中文口语词就行，不必知道前端用的英文 key
# ============================================================
_CATEGORY_ALIASES = {
    "all": "all", "全部": "all", "所有": "all", "全部分类": "all", "所有分类": "all",
    "diagnosis": "diagnosis", "诊断": "diagnosis", "诊断记录": "diagnosis",
    "exam": "exam", "examination": "exam", "检查": "exam", "检查类": "exam",
    "检查记录": "exam", "化验": "exam", "检验": "exam", "化验单": "exam",
    "report": "report", "报告": "report", "报告类": "report", "检查报告": "report",
    "allergy": "allergy", "过敏": "allergy", "过敏史": "allergy",
    "medication": "medication", "用药": "medication", "药物": "medication",
    "药品": "medication", "处方": "medication",
}
_CATEGORY_HINT = (
    "all(全部) / diagnosis(诊断) / exam(检查) / report(报告) / "
    "allergy(过敏) / medication(用药)"
)

_VIEW_ALIASES = {
    "today": "today", "今天": "today", "今日": "today", "当天": "today",
    "week": "week", "本周": "week", "这周": "week", "这一周": "week", "本星期": "week",
    "history": "history", "历史": "history", "历史记录": "history", "全部记录": "history",
}
_VIEW_HINT = "today(今日) / week(本周) / history(历史)"

_AGENT_ALIASES = {
    "health_advisor": "health_advisor", "健康顾问": "health_advisor", "顾问": "health_advisor",
    "问诊": "health_advisor", "advisor": "health_advisor",
    "health_records": "health_records", "健康档案": "health_records",
    "档案": "health_records", "档案管理员": "health_records",
    "medication_reminder": "medication_reminder", "用药提醒": "medication_reminder",
    "用药": "medication_reminder", "提醒": "medication_reminder",
    "visit_summary": "visit_summary", "就诊摘要": "visit_summary",
    "摘要": "visit_summary", "总结": "visit_summary",
    "auto": "auto", "自动": "auto",
}


def _norm(value: str, table: Dict[str, str], default: str = "") -> str:
    """查表归一化。大小写与首尾空白都容忍。"""
    if not value:
        return default
    return table.get(str(value).strip().lower(), table.get(str(value).strip(), default))


# ============================================================
# 工具
# ============================================================
@mcp.tool()
def refresh_current_page() -> Dict[str, Any]:
    """重新拉取**用户当前所在页面**的数据。

    触发场景："刷新一下"、"重新加载"、"数据是不是旧的"、"更新一下页面"。

    注意这里**只发 refresh、不发 navigateTo** —— 两个动作在同一 tick 派发时，
    navigate() 只是排了个 React state 更新，此刻旧页面还挂着，refresh 会打在
    旧页面上。所以刷新工具永远不导航。"""
    return _pu(
        [_act(_CURRENT_PAGE, "refresh")],
        summary="已刷新当前页面",
    )


@mcp.tool()
def show_page_alert(message: str) -> Dict[str, Any]:
    """在页面右上角弹一条提示（Snackbar），不打断正在流式输出的回复。

    触发场景：需要提醒用户注意某事，但不需要跳转或改数据时。
    比如"提醒我一下今天该吃药了"、"弹个提示说血压偏高"。

    :param message: 提示内容，一句话，别超过 60 字。
    """
    text = (message or "").strip()
    if not text:
        return {"success": False, "error": "message 不能为空"}
    return _pu(
        [_act(_PAGE_ROUTER, "showAlert", {"message": text})],
        summary=text,
    )


@mcp.tool()
def highlight_agent_card(agent_name: str) -> Dict[str, Any]:
    """把用户带到智能体中心，并高亮其中某一个智能体卡片（6 秒后自动褪去）。

    触发场景："哪个智能体管档案"、"带我去找健康顾问"、"高亮一下用药提醒"。

    :param agent_name: health_advisor(健康顾问) / health_records(健康档案) /
                       medication_reminder(用药提醒) / visit_summary(就诊摘要)。
                       也接受中文说法；认不出就当 auto，不报错。
    """
    agent = _norm(agent_name, _AGENT_ALIASES, "auto")
    return _pu(
        [
            _act(_PAGE_ROUTER, "navigateTo", {"path": _PATH_DASHBOARD}),
            _act(_DASHBOARD, "highlightAgent", {"agent": agent}),
        ],
        summary=f"已定位到智能体：{agent}",
    )


@mcp.tool()
def ask_agent_in_page(agent_name: str, question: str) -> Dict[str, Any]:
    """把用户带到智能体中心，并在页内对话框里**替他发起一次提问**。

    触发场景："去问问健康顾问我该注意什么"、"在页面上帮我问一下档案助手"。

    这是"AI 替你操作页面"最直观的一个：用户不用自己打字，页面上会自己开始
    流式回答。注意提问会真的走一遍完整对话链路，别拿它做无意义的调用。

    :param agent_name: health_advisor / health_records / medication_reminder /
                       visit_summary，或中文说法；认不出就当 auto（由路由决定）。
    :param question: 要问的话，照抄用户原话即可。
    """
    q = (question or "").strip()
    if not q:
        return {"success": False, "error": "question 不能为空"}
    agent = _norm(agent_name, _AGENT_ALIASES, "auto")
    return _pu(
        [
            _act(_PAGE_ROUTER, "navigateTo", {"path": _PATH_DASHBOARD}),
            _act(_DASHBOARD, "askAgent", {"agent": agent, "question": q}),
        ],
        summary=f"已在页面内向 {agent} 提问",
    )


@mcp.tool()
def filter_health_records(category: str) -> Dict[str, Any]:
    """跳到健康档案页，并把分类筛选切到指定类别。

    触发场景："只看检查的"、"把档案筛到报告"、"看看我的过敏记录"、
    "档案页筛到用药"。

    :param category: 全部 / 诊断 / 检查 / 报告 / 过敏 / 用药，或英文 key
                     all / diagnosis / exam / report / allergy / medication。
                     认不出会返回 success=false 并列出合法值，**不会**静默展示全部
                     —— 那样用户会以为自己筛成功了。
    """
    key = _norm(category, _CATEGORY_ALIASES)
    if not key:
        return {
            "success": False,
            "error": f"认不出分类「{category}」。合法值：{_CATEGORY_HINT}",
        }
    return _pu(
        [
            _act(_PAGE_ROUTER, "navigateTo", {"path": _PATH_HEALTH_RECORDS}),
            _act(_HEALTH_RECORDS, "setFilter", {"type": key}),
        ],
        summary=f"已筛选档案分类：{key}",
    )


@mcp.tool()
def set_health_records_search(query: str) -> Dict[str, Any]:
    """跳到健康档案页，并在搜索框里填入关键词过滤列表。

    触发场景："档案里搜一下血糖"、"帮我找带'协和'的档案"、
    "把档案页搜索框填成心电图"。

    与 PageControlTool_open_health_record 的区别：那个是**打开某一条记录的详情
    弹窗**，这个是**在列表上做关键词过滤**。用户说"打开/调出某一份"时用那个，
    说"搜一下/过滤一下"时用这个。

    :param query: 关键词，照抄用户原话里的词即可。
    """
    q = (query or "").strip()
    if not q:
        return {"success": False, "error": "query 不能为空"}
    return _pu(
        [
            _act(_PAGE_ROUTER, "navigateTo", {"path": _PATH_HEALTH_RECORDS}),
            _act(_HEALTH_RECORDS, "setSearch", {"q": q}),
        ],
        summary=f"已按「{q}」过滤档案",
    )


@mcp.tool()
def switch_medication_view(view: str) -> Dict[str, Any]:
    """跳到用药页，并切换顶部的时间视图标签。

    触发场景："看看本周的用药"、"打开用药历史"、"回到今天的用药"。

    :param view: 今天 / 本周 / 历史，或英文 key today / week / history。
                 认不出会返回 success=false 并列出合法值。
    """
    key = _norm(view, _VIEW_ALIASES)
    if not key:
        return {
            "success": False,
            "error": f"认不出视图「{view}」。合法值：{_VIEW_HINT}",
        }
    return _pu(
        [
            _act(_PAGE_ROUTER, "navigateTo", {"path": _PATH_MEDICATION}),
            _act(_MEDICATION, "setView", {"view": key}),
        ],
        summary=f"已切到用药视图：{key}",
    )


# ============================================================
# FastMCP instance 暴露给 mcp_discover 用
# ============================================================
def get_mcp_server() -> FastMCP:
    return mcp


__all__ = [
    "mcp",
    "get_mcp_server",
    "refresh_current_page",
    "show_page_alert",
    "highlight_agent_card",
    "ask_agent_in_page",
    "filter_health_records",
    "set_health_records_search",
    "switch_medication_view",
]


# Compatibility - 让 mcp_discover 也能 import 这个 module
import sys
sys.modules.setdefault("PhaCore_shared_page_control", sys.modules[__name__])
