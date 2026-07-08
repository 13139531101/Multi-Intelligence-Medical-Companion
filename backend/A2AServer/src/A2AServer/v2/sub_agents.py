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
            return load_mcp_tools("health_advisor")
        except Exception:
            return []


# ============================================================
# 2. 健康档案管理（Health Records Manager）
# ============================================================
class HealthRecordsV2(V2Agent):
    """健康档案 - 检查报告 OCR、存储、检索"""

    name = "health_records"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 健康档案管理员，负责检查报告、处方单的结构化存储与检索。",
    )

    def get_tools(self) -> List:
        try:
            return load_mcp_tools("health_records")
        except Exception:
            return []


# ============================================================
# 3. 用药提醒（Medication Reminder）
# ============================================================
class MedicationReminderV2(V2Agent):
    """用药提醒 - 药品安全、用药计划、提醒通知"""

    name = "medication_reminder"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 用药提醒助手，负责用药计划、药品相互作用提醒、依从性管理。",
    )

    def get_tools(self) -> List:
        try:
            return load_mcp_tools("medication_reminder")
        except Exception:
            return []


# ============================================================
# 4. 就诊摘要生成（Visit Summary Generator）
# ============================================================
class VisitSummaryV2(V2Agent):
    """就诊摘要 - 就诊记录整理、报告生成"""

    name = "visit_summary"
    system_prompt = _load_prompt(
        "memory_enhanced_agent_prompt.md",
        default="你是 PHA 就诊摘要生成助手，根据健康档案自动生成结构化就诊摘要。",
    )

    def get_tools(self) -> List:
        try:
            return load_mcp_tools("visit_summary")
        except Exception:
            return []
