"""
PHA v2 Skill 系统 + 内置工具（阶段41-1）

**目标**：
- 替代"prompt 字符串拼接" → 改为"Skill 选择 + 动态加载"
- 提供 langchain @tool 风格的 PHA 工具装饰器
- 把现有的 health_records / visit_summary / medication_reminder 拆成 Skill

**与 LangChain 关系**：
- 用 @tool 装饰器（langchain_core.tools）
- 但我们自己包一层 PHA tool registry，统一管理
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 尝试 langchain @tool
try:
    from langchain_core.tools import tool as _lc_tool
    LANGCHAIN_TOOL_OK = True
    logger.info("[skills] langchain @tool 可用")
except ImportError:
    LANGCHAIN_TOOL_OK = False
    def _lc_tool(func):
        """langchain 不可用时的兜底"""
        func.is_tool = True
        func.tool_name = func.__name__
        func.tool_description = func.__doc__ or ""
        return func


# ============================================================
# 1. Skill 数据类
# ============================================================
@dataclass
class Skill:
    """技能（独立的功能模块，可选加载）"""
    name: str                                # skill id
    display_name: str                        # 显示名
    description: str                         # 描述（给 LLM 看）
    category: str = "general"                # medical/lifestyle/admin/...
    tools: List[str] = field(default_factory=list)  # 包含的工具名
    system_prompt_addon: str = ""            # 加载时追加的 prompt
    keywords: List[str] = field(default_factory=list)  # 触发关键词
    priority: int = 50                       # 1-100，越高越先选
    enabled: bool = True
    icon: str = "🔧"                         # 前端显示
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "tools": self.tools,
            "keywords": self.keywords,
            "priority": self.priority,
            "enabled": self.enabled,
            "icon": self.icon,
            "metadata": self.metadata,
        }

    def matches(self, text: str) -> float:
        """判断文本是否触发此 skill，返回 0-1 置信度"""
        if not self.enabled:
            return 0.0
        text_lower = text.lower()
        hits = 0
        for kw in self.keywords:
            if kw.lower() in text_lower:
                hits += 1
        if hits == 0:
            return 0.0
        return min(hits / max(len(self.keywords), 1), 1.0)


# ============================================================
# 2. PHA 工具注册表（@tool 风格）
# ============================================================
class PHAToolRegistry:
    """
    PHA 工具注册表

    类似 langchain 的 tool registry，但加：
    - 元数据：category, version, auth_required
    - 调用统计：call_count, total_latency_ms, error_count
    - 工具链：tool A 输出可作为 tool B 输入
    """
    _instance: Optional["PHAToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._call_log: List[Dict[str, Any]] = []
        self._stats: Dict[str, Dict[str, int]] = {}

    @classmethod
    def get(cls) -> "PHAToolRegistry":
        if cls._instance is None:
            cls._instance = PHAToolRegistry()
        return cls._instance

    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        category: str = "general",
        version: str = "1.0",
        auth_required: bool = False,
        **metadata: Any,
    ) -> None:
        """注册工具"""
        # 兼容 langchain @tool 装饰过的函数（返回 StructuredTool）
        tool_name = getattr(func, "tool_name", name) or name
        tool_desc = getattr(func, "tool_description", description) or description

        # 检查是否是 langchain StructuredTool（有 invoke 但不能直接 call）
        is_structured = hasattr(func, "invoke") and not callable(getattr(func, "__call__", None))

        self._tools[tool_name] = {
            "name": tool_name,
            "func": func,
            "is_structured": is_structured,
            "description": tool_desc,
            "category": category,
            "version": version,
            "auth_required": auth_required,
            "metadata": metadata,
        }
        self._stats.setdefault(tool_name, {
            "call_count": 0,
            "error_count": 0,
            "total_latency_ms": 0,
            "last_called_at": 0,
        })
        logger.info("[tool_registry] registered: %s (%s)", tool_name, category)

    def call(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        """调用工具（带统计）"""
        if name not in self._tools:
            return {"success": False, "error": f"unknown tool: {name}"}
        tool = self._tools[name]
        start = time.time()
        try:
            if tool.get("is_structured"):
                # langchain StructuredTool 用 invoke
                result = tool["func"].invoke(kwargs)
            else:
                result = tool["func"](**kwargs)
            latency = (time.time() - start) * 1000
            self._stats[name]["call_count"] += 1
            self._stats[name]["total_latency_ms"] += latency
            self._stats[name]["last_called_at"] = time.time()
            # 记录到日志
            self._call_log.append({
                "tool": name,
                "args": kwargs,
                "success": True,
                "latency_ms": latency,
                "ts": time.time(),
            })
            # 截断日志到 1000 条
            if len(self._call_log) > 1000:
                self._call_log = self._call_log[-500:]
            return {"success": True, "result": result, "latency_ms": latency}
        except Exception as e:
            self._stats[name]["error_count"] += 1
            self._call_log.append({
                "tool": name,
                "args": kwargs,
                "success": False,
                "error": str(e),
                "ts": time.time(),
            })
            return {"success": False, "error": str(e)}

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出工具（不含 func）"""
        tools = []
        for t in self._tools.values():
            if category and t["category"] != category:
                continue
            tools.append({
                "name": t["name"],
                "description": t["description"],
                "category": t["category"],
                "version": t["version"],
                "auth_required": t["auth_required"],
                "stats": self._stats.get(t["name"], {}),
            })
        return tools

    def get_stats(self) -> Dict[str, Any]:
        total_calls = sum(s["call_count"] for s in self._stats.values())
        total_errors = sum(s["error_count"] for s in self._stats.values())
        return {
            "total_tools": len(self._tools),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_calls * 100) if total_calls else 0,
            "by_tool": self._stats,
            "recent_log": self._call_log[-20:],
        }


# ============================================================
# 3. 内置工具（langchain @tool 风格）
# ============================================================
@_lc_tool
def get_health_records(user_id: str, limit: int = 5) -> str:
    """获取用户的健康档案（诊断、检查报告、过敏史）

    Args:
        user_id: 用户ID
        limit: 返回数量

    Returns:
        健康记录 JSON 字符串
    """
    # 模拟实现（真实应该从 health_records_api 调）
    return json.dumps({
        "user_id": user_id,
        "records": [
            {"type": "diagnosis", "name": "高血压", "date": "2024-01-15"},
            {"type": "allergy", "name": "青霉素", "severity": "严重"},
        ],
        "limit": limit,
    }, ensure_ascii=False)


@_lc_tool
def get_medication_reminders(user_id: str) -> str:
    """获取用户的用药提醒

    Args:
        user_id: 用户ID

    Returns:
        用药提醒 JSON 字符串
    """
    return json.dumps({
        "user_id": user_id,
        "reminders": [
            {"drug": "硝苯地平", "dose": "30mg", "frequency": "每日1次", "time": "08:00"},
            {"drug": "阿司匹林", "dose": "100mg", "frequency": "每日1次", "time": "20:00"},
        ],
    }, ensure_ascii=False)


@_lc_tool
def calculate_bmi(weight_kg: float, height_cm: float) -> str:
    """计算 BMI 体质指数

    Args:
        weight_kg: 体重（公斤）
        height_cm: 身高（厘米）

    Returns:
        BMI 值和分类
    """
    bmi = weight_kg / ((height_cm / 100) ** 2)
    if bmi < 18.5:
        cat = "偏瘦"
    elif bmi < 24:
        cat = "正常"
    elif bmi < 28:
        cat = "超重"
    else:
        cat = "肥胖"
    return json.dumps({
        "bmi": round(bmi, 1),
        "category": cat,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
    }, ensure_ascii=False)


@_lc_tool
def search_drug_info(drug_name: str) -> str:
    """查询药品信息（用法、副作用、禁忌）

    Args:
        drug_name: 药品名（中英）

    Returns:
        药品信息
    """
    # 简化版（生产应接药品数据库）
    drug_db = {
        "二甲双胍": {"use": "降糖", "side_effects": ["胃肠不适"], "contra": "肾功能不全"},
        "硝苯地平": {"use": "降压", "side_effects": ["面红", "头痛"], "contra": "心源性休克"},
        "阿司匹林": {"use": "抗血小板", "side_effects": ["胃出血"], "contra": "消化道溃疡"},
    }
    info = drug_db.get(drug_name, {"use": "未知", "side_effects": [], "contra": "请咨询医生"})
    return json.dumps({"drug": drug_name, **info}, ensure_ascii=False)


@_lc_tool
def schedule_visit(department: str, preferred_date: str, user_id: str) -> str:
    """预约门诊

    Args:
        department: 科室
        preferred_date: 期望日期 (YYYY-MM-DD)
        user_id: 用户ID

    Returns:
        预约结果
    """
    return json.dumps({
        "success": True,
        "user_id": user_id,
        "department": department,
        "date": preferred_date,
        "appointment_id": f"A{int(time.time())}",
        "queue_number": 12,
        "estimated_time": "10:30",
    }, ensure_ascii=False)


# ============================================================
# 4. Skill 注册（6 个 PHA Skill）
# ============================================================
DEFAULT_SKILLS: List[Skill] = [
    Skill(
        name="health_records",
        display_name="健康档案",
        description="查询、管理用户的健康档案（诊断、过敏、检查报告）",
        category="medical",
        tools=["get_health_records", "search_drug_info"],
        system_prompt_addon=(
            "你是一个健康档案管理助手。当用户询问过往疾病、过敏、用药历史时，"
            "调用 get_health_records 工具获取详细档案。"
        ),
        keywords=["病历", "档案", "过敏", "诊断", "检查", "报告", "history", "record", "allergy"],
        priority=80,
        icon="📋",
    ),
    Skill(
        name="medication",
        display_name="用药提醒",
        description="管理用户的用药计划，提醒按时服药",
        category="medical",
        tools=["get_medication_reminders", "search_drug_info"],
        system_prompt_addon=(
            "你是一个用药管理助手。当用户问'今天吃什么药'、'忘了吃药'时，"
            "调用 get_medication_reminders 工具。"
        ),
        keywords=["药", "吃", "忘记", "提醒", "medication", "remind", "吃药", "忘记吃药"],
        priority=75,
        icon="💊",
    ),
    Skill(
        name="vital_signs",
        display_name="体征计算",
        description="BMI、血压、血糖等健康指标计算",
        category="medical",
        tools=["calculate_bmi", "search_drug_info"],
        system_prompt_addon=(
            "你是一个体征计算助手。用户给出体重身高时立即调用 calculate_bmi。"
        ),
        keywords=["体重", "身高", "BMI", "血压", "血糖", "bmi", "weight", "height", "血压高"],
        priority=60,
        icon="📊",
    ),
    Skill(
        name="visit_booking",
        display_name="门诊预约",
        description="预约挂号、排班查询",
        category="service",
        tools=["schedule_visit"],
        system_prompt_addon=(
            "你是一个门诊预约助手。收集 user_id/department/date 后调用 schedule_visit。"
        ),
        keywords=["预约", "挂号", "门诊", "appointment", "book", "visit", "科室"],
        priority=55,
        icon="📅",
    ),
    Skill(
        name="drug_query",
        display_name="药品查询",
        description="查询药品说明书、副作用、禁忌",
        category="medical",
        tools=["search_drug_info"],
        system_prompt_addon="你是一个药品知识助手。调用 search_drug_info 提供信息。",
        keywords=["说明书", "副作用", "禁忌", "drug", "medicine", "副作用", "什么药"],
        priority=50,
        icon="💉",
    ),
    Skill(
        name="general_chat",
        display_name="通用对话",
        description="日常问候、生活建议、闲聊",
        category="general",
        tools=[],
        system_prompt_addon="你是一个友善的健康顾问助手，提供日常生活建议。",
        keywords=["你好", "hello", "hi", "天气", "谢谢", "thank"],
        priority=10,
        icon="💬",
    ),
]


class SkillRegistry:
    """Skill 注册表（单例）"""
    _instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        for skill in DEFAULT_SKILLS:
            self._skills[skill.name] = skill
        # 注册所有内置工具
        for tool_func in [_get_health_records_impl, _get_medication_reminders_impl,
                          _calculate_bmi_impl, _search_drug_info_impl, _schedule_visit_impl]:
            pass  # 实际注册在 _register_tools() 中

    @classmethod
    def get(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = SkillRegistry()
            cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self) -> None:
        """注册默认工具"""
        registry = PHAToolRegistry.get()
        registry.register(
            name="get_health_records",
            func=get_health_records,
            description="获取用户的健康档案（诊断、检查报告、过敏史）",
            category="medical",
        )
        registry.register(
            name="get_medication_reminders",
            func=get_medication_reminders,
            description="获取用户的用药提醒",
            category="medical",
        )
        registry.register(
            name="calculate_bmi",
            func=calculate_bmi,
            description="计算 BMI 体质指数",
            category="medical",
        )
        registry.register(
            name="search_drug_info",
            func=search_drug_info,
            description="查询药品信息（用法、副作用、禁忌）",
            category="medical",
        )
        registry.register(
            name="schedule_visit",
            func=schedule_visit,
            description="预约门诊",
            category="service",
        )

    def register_skill(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
        logger.info("[skill_registry] registered: %s", skill.name)

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        skills.sort(key=lambda s: -s.priority)
        return [s.to_dict() for s in skills]

    def select_skills(self, text: str, top_k: int = 3,
                      min_score: float = 0.1) -> List[Skill]:
        """根据文本选择最相关的 skill"""
        scored = []
        for skill in self._skills.values():
            score = skill.matches(text)
            if score >= min_score:
                scored.append((score, skill))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def build_system_prompt(self, base: str, skills: List[Skill]) -> str:
        """根据选中的 skills 拼接 system prompt"""
        if not skills:
            return base
        addons = "\n\n".join([
            f"## Skill: {s.display_name}\n{s.system_prompt_addon}"
            for s in skills
        ])
        return f"{base}\n\n# 已加载 Skills（自动选择）\n{addons}"

    def build_skill_context(self, skills: List[Skill]) -> str:
        """
        构建 skill context 文本，直接拼入用户 query（用于 injection）。

        格式：
        ## 激活的 Skills（基于当前问题自动选择）

        ### {display_name}
        {description}
        提示：{system_prompt_addon}

        Args:
            user_query: 原始用户问题
            skills: SkillRegistry.select_skills() 返回的选中技能

        Returns:
            格式化的 skill context 字符串，可直接拼入 query
        """
        if not skills:
            return ""
        header = "## 激活的 Skills（基于当前问题自动选择）\n"
        parts = [header]
        for s in skills:
            parts.append(f"### {s.display_name}")
            parts.append(f"描述：{s.description}")
            if s.system_prompt_addon:
                parts.append(f"提示：{s.system_prompt_addon}")
            parts.append("")  # 空行分隔
        return "\n".join(parts).strip()


# 占位函数（实际指向 @tool 装饰的）
def _get_health_records_impl(*args, **kwargs): return get_health_records(*args, **kwargs)
def _get_medication_reminders_impl(*args, **kwargs): return get_medication_reminders(*args, **kwargs)
def _calculate_bmi_impl(*args, **kwargs): return calculate_bmi(*args, **kwargs)
def _search_drug_info_impl(*args, **kwargs): return search_drug_info(*args, **kwargs)
def _schedule_visit_impl(*args, **kwargs): return schedule_visit(*args, **kwargs)


# ============================================================
# 5. 工厂 + 便捷函数
# ============================================================
def get_skill_registry() -> SkillRegistry:
    return SkillRegistry.get()


def get_tool_registry() -> PHAToolRegistry:
    return PHAToolRegistry.get()


def build_smart_prompt(base: str, user_text: str, top_k: int = 2) -> str:
    """根据用户输入动态选 skill 并构造 prompt"""
    registry = get_skill_registry()
    skills = registry.select_skills(user_text, top_k=top_k)
    return registry.build_system_prompt(base, skills), [s.name for s in skills]


__all__ = [
    "Skill",
    "PHAToolRegistry",
    "SkillRegistry",
    "get_health_records",
    "get_medication_reminders",
    "calculate_bmi",
    "search_drug_info",
    "schedule_visit",
    "get_skill_registry",
    "get_tool_registry",
    "build_smart_prompt",
    "LANGCHAIN_TOOL_OK",
]