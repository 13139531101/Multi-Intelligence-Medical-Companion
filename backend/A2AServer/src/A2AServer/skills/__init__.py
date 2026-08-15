"""
PHA Skills 系统

从 skills/definitions/*.yaml 动态加载 skill 定义，
由 SkillRegistry 统一管理，按关键词匹配合适的 skill。

目录结构：
    skills/
        __init__.py          # 本模块入口，导出公开 API
        registry.py          # Skill, PHAToolRegistry, SkillRegistry
        loaders/
            dir_loader.py    # 扫描 definitions/ 目录批量加载 YAML
        definitions/         # YAML 格式的 skill 定义（可由运营人员直接编辑）
            health_records.yaml
            medication.yaml
            vital_signs.yaml
            visit_booking.yaml
            drug_query.yaml
            general_chat.yaml
"""
from .registry import (
    Skill,
    PHAToolRegistry,
    SkillRegistry,
    get_skill_registry,
    get_tool_registry,
    build_smart_prompt,
)

__all__ = [
    "Skill",
    "PHAToolRegistry",
    "SkillRegistry",
    "get_skill_registry",
    "get_tool_registry",
    "build_smart_prompt",
]
