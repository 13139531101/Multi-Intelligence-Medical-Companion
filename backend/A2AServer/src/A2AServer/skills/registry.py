"""
Skill 注册表核心代码（从 v2/skills.py 迁移）

保留所有原有逻辑，仅改动：
- 内置工具从本文件移至 tools/ 目录
- DEFAULT_SKILLS 从 YAML 文件动态加载（可通过 dir_loader 覆盖）
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# LangChain @tool 兼容
# ============================================================
try:
    from langchain_core.tools import tool as _lc_tool
    LANGCHAIN_TOOL_OK = True
except ImportError:
    LANGCHAIN_TOOL_OK = False
    def _lc_tool(func):
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
    name: str
    display_name: str
    description: str
    category: str = "general"
    tools: List[str] = field(default_factory=list)
    system_prompt_addon: str = ""
    keywords: List[str] = field(default_factory=list)
    priority: int = 50
    enabled: bool = True
    icon: str = "🔧"
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
        hits = sum(1 for kw in self.keywords if kw.lower() in text_lower)
        if hits == 0:
            return 0.0
        return min(hits / max(len(self.keywords), 1), 1.0)


# ============================================================
# 2. PHAToolRegistry
# ============================================================
class PHAToolRegistry:
    _instance: Optional["PHAToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._call_log: List[Dict[str, Any]] = []
        self._stats: Dict[str, Dict[str, int]] = {}

    @classmethod
    def get(cls) -> "PHAToolRegistry":
        if cls._instance is None:
            cls._instance = PHAToolRegistry()
            cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self) -> None:
        """注册 5 个内置工具（阶段41-1 → PHASE 6 动态选择）"""
        self.register(
            name="get_health_records",
            func=get_health_records,
            description="获取用户的健康档案（诊断、检查报告、过敏史）",
            category="medical",
        )
        self.register(
            name="get_medication_reminders",
            func=get_medication_reminders,
            description="获取用户的用药提醒",
            category="medical",
        )
        self.register(
            name="calculate_bmi",
            func=calculate_bmi,
            description="计算 BMI 体质指数",
            category="medical",
        )
        self.register(
            name="search_drug_info",
            func=search_drug_info,
            description="查询药品信息（用法、副作用、禁忌）",
            category="medical",
        )
        self.register(
            name="schedule_visit",
            func=schedule_visit,
            description="预约门诊",
            category="service",
        )

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
        tool_name = getattr(func, "tool_name", name) or name
        tool_desc = getattr(func, "tool_description", description) or description
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
            "call_count": 0, "error_count": 0,
            "total_latency_ms": 0, "last_called_at": 0,
        })
        logger.info("[tool_registry] registered: %s (%s)", tool_name, category)

    def call(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        if name not in self._tools:
            return {"success": False, "error": f"unknown tool: {name}"}
        tool = self._tools[name]
        start = time.time()
        try:
            result = tool["func"].invoke(kwargs) if tool.get("is_structured") else tool["func"](**kwargs)
            latency = (time.time() - start) * 1000
            self._stats[name]["call_count"] += 1
            self._stats[name]["total_latency_ms"] += latency
            self._stats[name]["last_called_at"] = time.time()
            self._call_log.append({"tool": name, "args": kwargs, "success": True, "latency_ms": latency, "ts": time.time()})
            if len(self._call_log) > 1000:
                self._call_log = self._call_log[-500:]
            return {"success": True, "result": result, "latency_ms": latency}
        except Exception as e:
            self._stats[name]["error_count"] += 1
            self._call_log.append({"tool": name, "args": kwargs, "success": False, "error": str(e), "ts": time.time()})
            return {"success": False, "error": str(e)}

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            {"name": t["name"], "description": t["description"],
             "category": t["category"], "version": t["version"],
             "auth_required": t["auth_required"], "stats": self._stats.get(t["name"], {})}
            for t in self._tools.values()
            if not category or t["category"] == category
        ]

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

    def select_tools(self, query: str, top_k: int = 5, min_score: float = 0.05) -> List[Dict[str, Any]]:
        """根据 query 文本动态选择最相关的 top_k 工具（PHASE 6 动态工具选择）

        评分策略：
        1. 工具名称精确匹配 → 1.0
        2. 工具 description 子串匹配 → +0.4（中文友好）
        3. 工具 description 关键词匹配 → 累计加分
        4. 类别匹配 → +0.1
        低于 min_score 的工具不返回
        """
        query_lower = query.lower()
        # 中文字符串没有空格分隔，用 set(query_lower) 按字符匹配
        # 英文用 split() 按空格/下划线分隔
        query_words = set(query_lower.split()) if ' ' in query_lower or '_' in query_lower else set(query_lower)

        scored = []
        for tool in self._tools.values():
            score = 0.0
            name = tool["name"].lower()
            desc = tool.get("description", "").lower()
            category = tool.get("category", "").lower()

            # 1. 名称精确匹配
            if query_lower in name or name in query_lower:
                score = 1.0
            else:
                # 2. 中文友好：子串匹配（任意 query word 在 desc 中）
                has_substring = any(qw in desc for qw in query_words)
                if has_substring:
                    score += 0.4
                # 2b. 大小写不敏感子串（英文词如 BMI）
                if query_lower in desc:
                    score += 0.5
                # 3. 描述关键词匹配（英文/空格分隔语言）
                desc_words = set(desc.split())
                overlap = query_words & desc_words
                if overlap:
                    score += min(len(overlap) * 0.15, 0.6)
                # 名称分词匹配
                name_words = set(name.replace("_", " ").split())
                name_overlap = query_words & name_words
                if name_overlap:
                    score += min(len(name_overlap) * 0.2, 0.4)
                # 4. 类别匹配
                if query_words & {category}:
                    score += 0.1

            if score >= min_score:
                scored.append((score, tool))

        scored.sort(key=lambda x: -x[0])
        # 返回时排除 func（不可序列化），只保留可序列化字段
        return [
            {k: v for k, v in t.items() if k != "func"}
            for _, t in scored[:top_k]
        ]


# ============================================================
# 3. 内置工具（@tool 风格）
# ============================================================
@_lc_tool
def get_health_records(user_id: str, limit: int = 5) -> str:
    """获取用户的健康档案（诊断、检查报告、过敏史）"""
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
    """获取用户的用药提醒"""
    return json.dumps({
        "user_id": user_id,
        "reminders": [
            {"drug": "硝苯地平", "dose": "30mg", "frequency": "每日1次", "time": "08:00"},
            {"drug": "阿司匹林", "dose": "100mg", "frequency": "每日1次", "time": "20:00"},
        ],
    }, ensure_ascii=False)


@_lc_tool
def calculate_bmi(weight_kg: float, height_cm: float) -> str:
    """计算 BMI 体质指数"""
    bmi = weight_kg / ((height_cm / 100) ** 2)
    cat = "偏瘦" if bmi < 18.5 else "正常" if bmi < 24 else "超重" if bmi < 28 else "肥胖"
    return json.dumps({"bmi": round(bmi, 1), "category": cat, "weight_kg": weight_kg, "height_cm": height_cm}, ensure_ascii=False)


@_lc_tool
def search_drug_info(drug_name: str) -> str:
    """查询药品信息（用法、副作用、禁忌）"""
    drug_db = {
        "二甲双胍": {"use": "降糖", "side_effects": ["胃肠不适"], "contra": "肾功能不全"},
        "硝苯地平": {"use": "降压", "side_effects": ["面红", "头痛"], "contra": "心源性休克"},
        "阿司匹林": {"use": "抗血小板", "side_effects": ["胃出血"], "contra": "消化道溃疡"},
    }
    info = drug_db.get(drug_name, {"use": "未知", "side_effects": [], "contra": "请咨询医生"})
    return json.dumps({"drug": drug_name, **info}, ensure_ascii=False)


@_lc_tool
def schedule_visit(department: str, preferred_date: str, user_id: str) -> str:
    """预约门诊"""
    return json.dumps({
        "success": True, "user_id": user_id, "department": department,
        "date": preferred_date, "appointment_id": f"A{int(time.time())}",
        "queue_number": 12, "estimated_time": "10:30",
    }, ensure_ascii=False)


# ============================================================
# 4. SkillRegistry（默认内置 Skill，可被 YAML 覆盖）
# ============================================================
_BUILTIN_SKILLS: List[Skill] = [
    Skill(
        name="health_records",
        display_name="健康档案",
        description="查询、管理用户的健康档案（诊断、过敏、检查报告）",
        category="medical",
        tools=["get_health_records", "search_drug_info"],
        system_prompt_addon="你是一个健康档案管理助手。当用户询问过往疾病、过敏、用药历史时，调用 get_health_records 工具获取详细档案。",
        keywords=["病历", "档案", "过敏", "诊断", "检查", "报告", "history", "record", "allergy"],
        priority=80, icon="📋",
    ),
    Skill(
        name="medication",
        display_name="用药提醒",
        description="管理用户的用药计划，提醒按时服药",
        category="medical",
        tools=["get_medication_reminders", "search_drug_info"],
        system_prompt_addon="你是一个用药管理助手。当用户问'今天吃什么药'、'忘了吃药'时，调用 get_medication_reminders 工具。",
        keywords=["药", "吃", "忘记", "提醒", "medication", "remind", "吃药", "忘记吃药"],
        priority=75, icon="💊",
    ),
    Skill(
        name="vital_signs",
        display_name="体征计算",
        description="BMI、血压、血糖等健康指标计算",
        category="medical",
        tools=["calculate_bmi", "search_drug_info"],
        system_prompt_addon="你是一个体征计算助手。用户给出体重身高时立即调用 calculate_bmi。",
        keywords=["体重", "身高", "BMI", "血压", "血糖", "bmi", "weight", "height", "血压高"],
        priority=60, icon="📊",
    ),
    Skill(
        name="visit_booking",
        display_name="门诊预约",
        description="预约挂号、排班查询",
        category="service",
        tools=["schedule_visit"],
        system_prompt_addon="你是一个门诊预约助手。收集 user_id/department/date 后调用 schedule_visit。",
        keywords=["预约", "挂号", "门诊", "appointment", "book", "visit", "科室"],
        priority=55, icon="📅",
    ),
    Skill(
        name="drug_query",
        display_name="药品查询",
        description="查询药品说明书、副作用、禁忌",
        category="medical",
        tools=["search_drug_info"],
        system_prompt_addon="你是一个药品知识助手。调用 search_drug_info 提供信息。",
        keywords=["说明书", "副作用", "禁忌", "drug", "medicine", "副作用", "什么药"],
        priority=50, icon="💉",
    ),
    Skill(
        name="general_chat",
        display_name="通用对话",
        description="日常问候、生活建议、闲聊",
        category="general",
        tools=[],
        system_prompt_addon="你是一个友善的健康顾问助手，提供日常生活建议。",
        keywords=["你好", "hello", "hi", "天气", "谢谢", "thank"],
        priority=10, icon="💬",
    ),
]


class SkillRegistry:
    """Skill 注册表（单例），支持 YAML 动态加载覆盖默认 Skill"""
    _instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._yaml_loaded: bool = False
        # 注册默认内置 Skill
        for skill in _BUILTIN_SKILLS:
            self._skills[skill.name] = skill

    @classmethod
    def get(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = SkillRegistry()
            cls._instance._register_default_tools()
            cls._instance._try_load_yaml()
        return cls._instance

    def _try_load_yaml(self) -> None:
        """尝试从 YAML 目录加载 Skill 定义，覆盖同名默认 Skill"""
        if self._yaml_loaded:
            return
        try:
            from .loaders.dir_loader import load_skills_from_dir
            base = __file__.rsplit("/", 1)[0]
            yaml_dir = f"{base}/definitions"
            loaded = load_skills_from_dir(yaml_dir)
            for skill in loaded:
                self._skills[skill.name] = skill
            if loaded:
                logger.info("[skill_registry] loaded %d skills from YAML", len(loaded))
            self._yaml_loaded = True
        except Exception as e:
            logger.debug("[skill_registry] YAML loading skipped: %s", e)
            self._yaml_loaded = True  # 不重试

    def _register_default_tools(self) -> None:
        registry = PHAToolRegistry.get()
        for name, func, desc, cat in [
            ("get_health_records", get_health_records, "获取用户健康档案", "medical"),
            ("get_medication_reminders", get_medication_reminders, "获取用药提醒", "medical"),
            ("calculate_bmi", calculate_bmi, "计算 BMI", "medical"),
            ("search_drug_info", search_drug_info, "查询药品信息", "medical"),
            ("schedule_visit", schedule_visit, "预约门诊", "service"),
        ]:
            registry.register(name=name, func=func, description=desc, category=cat)

    def register_skill(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
        logger.info("[skill_registry] registered: %s", skill.name)

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        skills = sorted(self._skills.values(), key=lambda s: -s.priority)
        if category:
            skills = [s for s in skills if s.category == category]
        return [s.to_dict() for s in skills]

    def select_skills(self, text: str, top_k: int = 3, min_score: float = 0.1) -> List[Skill]:
        scored = [(s.matches(text), s) for s in self._skills.values() if s.matches(text) >= min_score]
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def build_system_prompt(self, base: str, skills: List[Skill]) -> str:
        if not skills:
            return base
        addons = "\n\n".join([f"## Skill: {s.display_name}\n{s.system_prompt_addon}" for s in skills])
        return f"{base}\n\n# 已加载 Skills（自动选择）\n{addons}"

    def build_skill_context(self, skills: List[Skill]) -> str:
        if not skills:
            return ""
        parts = ["## 激活的 Skills（基于当前问题自动选择）\n"]
        for s in skills:
            parts.append(f"### {s.display_name}")
            parts.append(f"描述：{s.description}")
            if s.system_prompt_addon:
                parts.append(f"提示：{s.system_prompt_addon}")
            parts.append("")
        return "\n".join(parts).strip()


# ============================================================
# 5. 便捷函数
# ============================================================
def get_skill_registry() -> SkillRegistry:
    return SkillRegistry.get()


def get_tool_registry() -> PHAToolRegistry:
    return PHAToolRegistry.get()


def build_smart_prompt(base: str, user_text: str, top_k: int = 2) -> tuple[str, list[str]]:
    registry = get_skill_registry()
    skills = registry.select_skills(user_text, top_k=top_k)
    return registry.build_system_prompt(base, skills), [s.name for s in skills]
