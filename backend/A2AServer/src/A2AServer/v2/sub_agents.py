"""
PHA v2 子智能体（阶段2 占位实现）

**当前状态**：
- 每个子 Agent 提供 v2 入口（继承 V2Agent）
- 工具列表暂时为空（阶段2-3 会接入真实 MCP 工具）
- 通过 v1 BasicAgent 已有 prompt 加载逻辑

**下一步**：
- 阶段2-3：从 mcpserver/*_tool.py 加载真实工具，转 BaseTool
- 阶段2-4：把 LangChain 1.x 工具调用串起来
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from .v2_agent import V2Agent
from .mcp_tool_adapter import load_mcp_tools

# 阶段48-15: 读 PHA_MCP_TRANSPORT env var 决定 transport 类型
#   - "streamable_http" (默认, 推荐) → HTTP MCP server (1 process / agent)
#   - "stdio" → stdio subprocess + JSON-RPC
#   - "inprocess" → 旧的 in-process import (fallback)
import os as _os
_MCP_TRANSPORT = _os.environ.get("PHA_MCP_TRANSPORT", "streamable_http")
from .agent_registry import register_agent


def _load_prompt(filename: str, default: str = "") -> str:
    """加载 prompt 文件（兼容项目原有结构）"""
    candidates = [
        Path(f"backend/HealthAdvisor/{filename}"),
        Path(f"backend/HealthRecordsManager/{filename}"),
        Path(f"backend/MedicationReminder/{filename}"),
        Path(f"backend/VisitSummaryGenerator/{filename}"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
    return default


# ============================================================
# 1. 健康顾问（Health Advisor）
# ============================================================
@register_agent(
    name="health_advisor",
    description="AI 问诊、健康教育、症状分析",
    keywords=[
        "头疼", "发烧", "痛", "病", "医生", "建议", "咨询", "症状",
        "不舒服", "难受", "health", "symptom", "咳嗽", "感冒", "头晕", "头痛",
        # 阶段48-7: 把高频健康词加进去, 让 routing 真正命中 advisor
        "血压", "血糖", "血脂", "胆固醇", "心率", "胸闷", "心悸",
        "失眠", "睡眠", "焦虑", "抑郁", "体重", "BMI",
        "饮食", "营养", "运动", "锻炼", "怎么办", "如何", "为什么",
    ],
    tools_module="health_advisor",
    aliases=["健康顾问"],
)
class HealthAdvisorV2(V2Agent):
    """健康顾问 - AI 问诊、健康教育、症状分析"""

    name = "health_advisor"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 健康顾问，基于循证医学为用户提供健康教育与建议（不能替代医生诊断）。",
    )

    def get_tools(self) -> List:
        """加载 HealthAdvisor 的 MCP 工具（阶段2-3 接入）"""
        try:
            return load_mcp_tools("health_advisor", transport=_MCP_TRANSPORT)
        except Exception:
            return []


# ============================================================
# 2. 健康档案管理（Health Records Manager）
# ============================================================
@register_agent(
    name="health_records",
    description="检查报告 OCR、存储、检索",
    keywords=["档案", "记录", "体检", "报告", "record", "检查单"],
    tools_module="health_records",
    aliases=["健康档案管理员", "健康档案管理", "健康档案", "档案管理员"],
)
class HealthRecordsV2(V2Agent):
    """健康档案 - 检查报告 OCR、存储、检索"""

    name = "health_records"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 健康档案管理员，负责检查报告、处方单的结构化存储与检索。",
    )

    def get_tools(self) -> List:
        try:
            return load_mcp_tools("health_records", transport=_MCP_TRANSPORT)
        except Exception:
            return []


# ============================================================
# 3. 用药提醒（Medication Reminder）
# ============================================================
@register_agent(
    name="medication_reminder",
    description="药品安全、用药计划、提醒通知",
    keywords=["药", "吃药", "提醒", "medication", "服药", "用药", "剂量"],
    tools_module="medication_reminder",
    aliases=["用药提醒助手", "用药提醒"],
)
class MedicationReminderV2(V2Agent):
    """用药提醒 - 药品安全、用药计划、提醒通知"""

    name = "medication_reminder"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 用药提醒助手，负责用药计划、药品相互作用提醒、依从性管理。",
    )

    def get_tools(self) -> List:
        try:
            return load_mcp_tools("medication_reminder", transport=_MCP_TRANSPORT)
        except Exception:
            return []


# ============================================================
# 4. 就诊摘要生成（Visit Summary Generator）
# ============================================================
@register_agent(
    name="visit_summary",
    description="就诊记录整理、报告生成",
    keywords=["摘要", "总结", "就诊", "summary"],
    tools_module="visit_summary",
    aliases=["就诊摘要生成器", "就诊摘要生成", "就诊摘要", "就诊摘要助手"],
)
class VisitSummaryV2(V2Agent):
    """就诊摘要 - 就诊记录整理、报告生成"""

    name = "visit_summary"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 就诊摘要生成助手，根据健康档案自动生成结构化就诊摘要。",
    )

    def get_tools(self) -> List:
        try:
            return load_mcp_tools("visit_summary", transport=_MCP_TRANSPORT)
        except Exception:
            return []


# ============================================================
# 阶段31 演示：动态添加新 agent 只需要再加一个 @register_agent class
# ============================================================
# @register_agent(
#     name="nutrition_advisor",
#     description="营养建议、饮食分析",
#     keywords=["营养", "饮食", "食物", "nutrition", "diet"],
#     tools_module="nutrition_advisor",
#     aliases=["营养师"],
# )
# class NutritionAdvisorV2(V2Agent):
#     name = "nutrition_advisor"
#     system_prompt = "你是 PHA 营养顾问..."
#
#     def get_tools(self):
#         try:
#             return load_mcp_tools("nutrition_advisor")
#         except Exception:
#             return []
