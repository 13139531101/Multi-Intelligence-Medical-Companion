"""阶段48-16/48-21: HumanInTheLoop 危险 tool 配置.

阶段48-21 起: 自动从 DomainManifest 读 (manifest.agents[].dangerously=true
的 agent 的所有写类 tool 自动 require HITL). 同时保留阶段48-16 的硬编码
fallback (向后兼容).

判定流程:
  1. agent_name 在 manifest.dangerous_agents() 中?
     - 是 → 该 agent 暴露的所有 tool 名匹配 *_DANGEROUS_KEYWORDS (delete/add/save/log_taken/send_/update_/complete) → require HITL
  2. 否则: 读 manifest 里的 dangerously_keywords (per-agent 自定义)
  3. 否则: 读旧硬编码 fallback 表
  4. 否则: 全空 (此 agent 任何 tool 不 trigger HITL)
"""
from __future__ import annotations
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 通用危险操作关键字 (tool 名匹配这些关键词的会被默认 require HITL)
# ============================================================
_DANGEROUS_KEYWORDS = (
    "delete",    # 删除数据
    "complete",  # 完成/标记完成
    "log_taken", # 记录已服用 (改变状态)
    "save_",     # 保存 (写入新数据)
    "add_",      # 添加 (新增数据)
    "update_",   # 更新
    "send_",     # 发送 (通知/邮件)
)


def is_dangerous(tool_name: str) -> bool:
    """简单关键词检查: tool 名含危险关键字 → dangerous."""
    n = tool_name.lower()
    return any(kw in n for kw in _DANGEROUS_KEYWORDS)


def get_interrupt_config(
    agent_name: str,
    available_tools: Optional[List[str]] = None,
) -> dict:
    """返回 {tool_name: True} 给 HumanInTheLoopMiddleware.interrupt_on.

    Args:
        agent_name: 当前 agent 名字 (e.g. 'medication_reminder')
        available_tools: 此 agent 实际暴露的工具名列表 (用于精确匹配)

    判定优先级:
      1. manifest.dangerous_agents() 包含 → 用 *_DANGEROUS_KEYWORDS 自动 match
      2. manifest.agents[name].dangerously_keywords (自定义) → 精确匹配
      3. 硬编码 PHA fallback
      4. 留空

    Returns:
        dict: tool_name -> True (需要 interrupt) 或 tool_name -> {"decision_options": [...]}
    """
    tools = available_tools or []

    # ----------------------------------------------------------
    # 1. 阶段48-21: 从 manifest 自动收集
    # ----------------------------------------------------------
    try:
        from .domain_manifest import load_default
        manifest = load_default()
        agent_spec = manifest.get_agent(agent_name)
        if agent_spec:
            cfg: dict = {}
            if agent_spec.dangerously:
                # 自动匹配 — 此 agent 的所有写类工具都要 HITL
                matched = [t for t in tools if is_dangerous(t)]
                for t in matched:
                    cfg[t] = True
                logger.debug("[dangerous_tools] %s auto-matched dangerous tools: %s", agent_name, matched)
            # 自定义 keywords (per-agent, 比 dangerous 更细)
            custom_kw = getattr(agent_spec, "dangerously_keywords", None) or []
            for t in tools:
                for kw in custom_kw:
                    if kw.lower() in t.lower():
                        cfg[t] = True
                        break
            if cfg:
                return cfg
    except Exception as e:
        logger.debug("[dangerous_tools] manifest 读失败, fallback 硬编码: %s", e)

    # ----------------------------------------------------------
    # 2. 阶段48-16: 硬编码 PHA fallback (向后兼容)
    # ----------------------------------------------------------
    if agent_name == "health_records":
        return {
            "delete_reminder": True,
            "delete_health_record": True,
            "complete_reminder": True,
            "mark_reminder_taken": True,
            "add_medication_reminder": True,
            "save_health_record": True,
            "save_medication": True,
        }
    elif agent_name == "medication_reminder":
        return {
            "add_medication_reminder": True,
            "add_appointment_reminder": True,
            "log_medication_taken": True,
            "send_medication_notification": True,
            "send_appointment_notification": True,
            "set_notification_preferences": True,
        }
    elif agent_name == "visit_summary":
        return {
            "save_generated_summary": True,
            "delete_visit_summary": True,
            "delete_health_record": True,
        }
    elif agent_name == "health_advisor":
        return {
            "delete_medical_kb_document": True,
            "save_consultation": True,
            "upsert_medical_kb_document": True,
        }
    return {}


__all__ = ["is_dangerous", "get_interrupt_config"]
