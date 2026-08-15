"""
从 skills/definitions/ 目录扫描所有 .yaml 文件，解析为 Skill 对象。

YAML 格式示例（definitions/health_records.yaml）：
```yaml
name: health_records
display_name: 健康档案
description: 查询、管理用户的健康档案（诊断、过敏、检查报告）
category: medical
tools:
  - get_health_records
  - search_drug_info
system_prompt_addon: |
  你是一个健康档案管理助手。当用户询问过往疾病时...
keywords:
  - 病历
  - 档案
  - 过敏
priority: 80
enabled: true
icon: "📋"
```

同名 YAML 会覆盖代码中内置的默认 Skill。
"""
from __future__ import annotations

import logging
import os
from typing import List

logger = logging.getLogger(__name__)


def load_skills_from_dir(yaml_dir: str) -> List:
    """
    扫描 yaml_dir/*.yaml，返回 Skill 对象列表。

    解析失败的文件不影响其他文件（静默跳过）。
    """
    from ..registry import Skill

    skills: List[Skill] = []

    if not os.path.isdir(yaml_dir):
        logger.debug("[dir_loader] definitions dir not found: %s", yaml_dir)
        return skills

    for filename in sorted(os.listdir(yaml_dir)):
        if not filename.endswith(".yaml"):
            continue
        filepath = os.path.join(yaml_dir, filename)
        try:
            skill = _load_yaml_skill(filepath)
            if skill:
                skills.append(skill)
                logger.info("[dir_loader] loaded: %s (%s)", skill.name, filename)
        except Exception as e:
            logger.warning("[dir_loader] failed to load %s: %s", filename, e)

    return skills


def _load_yaml_skill(filepath: str):
    """解析单个 YAML 文件为 Skill 对象"""
    import yaml

    from ..registry import Skill

    with open(filepath, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or not data.get("name"):
        return None

    return Skill(
        name=str(data["name"]),
        display_name=str(data.get("display_name", data["name"])),
        description=str(data.get("description", "")),
        category=str(data.get("category", "general")),
        tools=data.get("tools", []),
        system_prompt_addon=str(data.get("system_prompt_addon", "")),
        keywords=data.get("keywords", []),
        priority=int(data.get("priority", 50)),
        enabled=bool(data.get("enabled", True)),
        icon=str(data.get("icon", "🔧")),
        metadata=data.get("metadata", {}),
    )
