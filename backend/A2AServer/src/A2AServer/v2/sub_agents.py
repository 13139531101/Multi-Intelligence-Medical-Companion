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

import logging
import os
from pathlib import Path
from typing import List

from .v2_agent import V2Agent
from ..mcp.mcp_tool_adapter import load_mcp_tools, load_phacore_tools   # 阶段48-19

logger = logging.getLogger(__name__)

# 阶段48-15: 读 PHA_MCP_TRANSPORT env var 决定 transport 类型
#   - "streamable_http" (默认, 推荐) → HTTP MCP server (1 process / agent)
#   - "stdio" → stdio subprocess + JSON-RPC
#   - "inprocess" → 旧的 in-process import (fallback)
import os as _os
_MCP_TRANSPORT = _os.environ.get("PHA_MCP_TRANSPORT", "streamable_http")
from .agent_registry import register_agent


_PROMPT_FILENAME = "memory_enhanced_agent_prompt.md"


def _prompt_roots():
    """仓库根的候选位置。容器与本地开发目录深度不同，逐个试：

      容器: /app/A2AServer/v2/sub_agents.py          → parents[2] == /app
      仓库: .../backend/A2AServer/src/A2AServer/v2/  → parents[5] == 仓库根

    Path.cwd() 排最前，因为容器的 WORKDIR 就是 /app。

    注意 parents[i] 越界会抛 IndexError，所以这里必须**按需**取、且判长度 ——
    写成模块级常量列表会在容器里直接 import 失败（容器只有 3 层 parent），
    整个 hostapi 起不来。
    """
    here = Path(__file__).resolve()
    roots = [Path.cwd()]
    for i in (2, 5):
        if len(here.parents) > i:
            roots.append(here.parents[i])
    return roots


def _load_prompt(agent_dir: str, default: str = "", filename: str = _PROMPT_FILENAME) -> str:
    """加载**指定 agent** 的 prompt 文件。

    :param agent_dir: agent 目录名，如 "HealthAdvisor"。这个参数必须显式传 ——
        四个 agent 的 prompt 内容完全不同（顾问/档案/用药/摘要，10.8K/11.9K/7.5K/8.5K），
        不能让它们互相串用。

    为什么改掉旧的"按固定顺序探测、返回第一个存在的文件"
    ----------------------------------------------------
    旧实现把四个目录写死成一个候选列表，谁先存在就用谁。而 hostapi 的
    Dockerfile 只整体 COPY 了 HealthRecordsManager（另外三个 agent 只 COPY 了
    mcpserver/），于是容器里四个 agent **全部**加载了 HealthRecordsManager 的
    prompt —— 改 HealthAdvisor 的 prompt 完全没效果，且不报任何错。
    现在按目录显式定位；四份文件都随镜像发出去（见 hostapi/Dockerfile）。

    找不到时退回 default 并告警：静默退化正是上面那个 bug 藏了这么久的原因。
    """
    roots = _prompt_roots()
    for root in roots:
        p = root / "backend" / agent_dir / filename
        try:
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                logger.info("[_load_prompt] %s ← %s (%d 字符)", agent_dir, p, len(text))
                return text
        except Exception as e:  # 权限/编码问题不该让 agent 起不来
            logger.warning("[_load_prompt] 读取 %s 失败: %s", p, e)
    logger.warning(
        "[_load_prompt] 未找到 %s/%s（试过 %d 个根目录），退回内置 default",
        agent_dir, filename, len(roots),
    )
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
        "HealthAdvisor",
        default="你是 PHA 健康顾问，基于循证医学为用户提供健康教育与建议（不能替代医生诊断）。",
    )

    def get_tools(self) -> List:
        """加载 HealthAdvisor 的 MCP 工具（阶段2-3 接入 + 阶段48-19: PhaCore re-export）"""
        try:
            return (
                load_mcp_tools("health_advisor", transport=_MCP_TRANSPORT)
                + load_phacore_tools(("ocr",))  # health_advisor 也需要 OCR (顾问阅报告)
            )
        except RuntimeError as e:
            if "无法定位仓库根目录" in str(e):
                logger.warning("[HealthAdvisorV2] MCP tools unavailable (no repo root): %s", e)
                return []
            raise
        except Exception:
            return []


# ============================================================
# 2. 健康档案管理（Health Records Manager）
# ============================================================
@register_agent(
    name="health_records",
    description="检查报告 OCR、存储、检索",
    # 阶段48-28: 补高精度名词。之前只有"报告/检查单"，而"血常规""化验"这类
    # 具体说法会被 health_advisor 的泛词（怎么办/如何/为什么）抢走 —— advisor
    # 没有档案工具，于是"打开上个月的血常规"只回文字、不跳转。
    # 刻意不加"打开""跳转"这类泛动词：它们和档案领域无关，加了会劫持无关查询。
    keywords=[
        "档案", "记录", "体检", "报告", "record", "检查单",
        "血常规", "化验", "检验", "影像", "病理", "处方单", "化验单", "检验单",
    ],
    tools_module="health_records",
    aliases=["健康档案管理员", "健康档案管理", "健康档案", "档案管理员"],
)
class HealthRecordsV2(V2Agent):
    """健康档案 - 检查报告 OCR、存储、检索"""

    name = "health_records"
    system_prompt = _load_prompt(
        "HealthRecordsManager",
        default="你是 PHA 健康档案管理员，负责检查报告、处方单的结构化存储与检索。",
    )

    def get_tools(self) -> List:
        """阶段48-19: OCR 工具从 HRM/mcpserver/ocr_tool.py 搬到 PhaCore/shared_ocr.py"""
        try:
            return (
                load_mcp_tools("health_records", transport=_MCP_TRANSPORT)
                + load_phacore_tools(("ocr",))   # OCR 是 PhaCore owner
            )
        except RuntimeError as e:
            if "无法定位仓库根目录" in str(e):
                logger.warning("[HealthRecordsV2] MCP tools unavailable: %s", e)
                return []
            raise
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
        "MedicationReminder",
        default="你是 PHA 用药提醒助手，负责用药计划、药品相互作用提醒、依从性管理。",
    )

    def get_tools(self) -> List:
        """阶段48-19: OCR tool 从 MedReminder/mcpserver/ocr_tool.py 搬到 PhaCore/shared_ocr.py"""
        try:
            return (
                load_mcp_tools("medication_reminder", transport=_MCP_TRANSPORT)
                + load_phacore_tools(("ocr",))   # re-export OCR (用于扫描药盒/处方)
            )
        except RuntimeError as e:
            if "无法定位仓库根目录" in str(e):
                logger.warning("[MedicationReminderV2] MCP tools unavailable: %s", e)
                return []
            raise
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
        "VisitSummaryGenerator",
        default="你是 PHA 就诊摘要生成助手，根据健康档案自动生成结构化就诊摘要。",
    )

    def get_tools(self) -> List:
        """阶段48-19: 不需要 OCR (visit_summary 处理的是已抽取的 text, 不是 image)"""
        try:
            return load_mcp_tools("visit_summary", transport=_MCP_TRANSPORT)
        except RuntimeError as e:
            if "无法定位仓库根目录" in str(e):
                logger.warning("[VisitSummaryV2] MCP tools unavailable: %s", e)
                return []
            raise
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
