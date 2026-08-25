# -*- coding: utf-8 -*-
"""
PHA v2 i18n 支持（阶段48-ops）
支持中文（zh）和英文（en）。

使用方式：
    from A2AServer.i18n import t, set_locale, get_locale

    set_locale("en")
    print(t("agent_not_found", agent_name="health_advisor"))
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any, Dict, Optional

# 当前语言（线程/协程安全）
_current_locale: ContextVar[str] = ContextVar("locale", default="zh")


def get_locale() -> str:
    """获取当前语言（从 context var 或环境变量）"""
    return _current_locale.get()


def set_locale(lang: str) -> None:
    """设置当前请求的语言"""
    if lang not in SUPPORTED_LOCALES:
        raise ValueError(f"Unsupported locale: {lang}. Supported: {SUPPORTED_LOCALES}")
    _current_locale.set(lang)


SUPPORTED_LOCALES = ["zh", "en"]


# ============================================================
# 翻译字典
# ============================================================

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # 通用
    "ok": {"zh": "成功", "en": "OK"},
    "error": {"zh": "错误", "en": "Error"},
    "loading": {"zh": "加载中...", "en": "Loading..."},
    "save": {"zh": "保存", "en": "Save"},
    "cancel": {"zh": "取消", "en": "Cancel"},
    "confirm": {"zh": "确认", "en": "Confirm"},
    "delete": {"zh": "删除", "en": "Delete"},
    "edit": {"zh": "编辑", "en": "Edit"},
    "submit": {"zh": "提交", "en": "Submit"},
    "search": {"zh": "搜索", "en": "Search"},
    "no_data": {"zh": "暂无数据", "en": "No data"},
    "success": {"zh": "操作成功", "en": "Success"},
    "failed": {"zh": "操作失败", "en": "Failed"},
    "network_error": {"zh": "网络错误，请稍后重试", "en": "Network error, please try again later"},
    "unknown_error": {"zh": "未知错误", "en": "Unknown error"},

    # 健康档案
    "health_records": {"zh": "健康档案", "en": "Health Records"},
    "upload_record": {"zh": "上传记录", "en": "Upload Record"},
    "no_records": {"zh": "暂无健康档案", "en": "No health records"},
    "record_type": {"zh": "记录类型", "en": "Record Type"},
    "record_date": {"zh": "记录日期", "en": "Record Date"},

    # 用药
    "medications": {"zh": "用药", "en": "Medications"},
    "current_medications": {"zh": "当前用药", "en": "Current Medications"},
    "no_medications": {"zh": "暂无用药记录", "en": "No medication records"},
    "add_medication": {"zh": "添加用药", "en": "Add Medication"},

    # Agent
    "health_advisor": {"zh": "健康顾问", "en": "Health Advisor"},
    "health_records_agent": {"zh": "健康档案管理员", "en": "Health Records Agent"},
    "medication_reminder_agent": {"zh": "用药提醒助手", "en": "Medication Reminder"},
    "visit_summary_agent": {"zh": "就诊摘要生成器", "en": "Visit Summary Agent"},

    # 错误
    "agent_not_found": {"zh": "Agent 不存在：{agent_name}", "en": "Agent not found: {agent_name}"},
    "tool_not_found": {"zh": "工具不存在：{tool_name}", "en": "Tool not found: {tool_name}"},
    "db_error": {"zh": "数据库错误", "en": "Database error"},
    "llm_error": {"zh": "AI 服务暂时不可用", "en": "AI service temporarily unavailable"},

    # 页面标题
    "page_dashboard": {"zh": "健康看板", "en": "Health Dashboard"},
    "page_chat": {"zh": "健康咨询", "en": "Health Consultation"},
    "page_medication": {"zh": "用药管理", "en": "Medication Management"},
    "page_records": {"zh": "健康档案", "en": "Health Records"},
}


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """
    翻译函数。
    用法：
        t("ok")                      → "成功"
        t("agent_not_found", agent_name="ha") → "Agent 不存在：ha"
    """
    if lang is None:
        lang = get_locale()
    if lang not in SUPPORTED_LOCALES:
        lang = "zh"

    templates = _TRANSLATIONS.get(key, {})
    template = templates.get(lang, templates.get("zh", key))
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


__all__ = ["t", "set_locale", "get_locale", "SUPPORTED_LOCALES"]
