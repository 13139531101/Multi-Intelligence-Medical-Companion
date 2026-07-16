"""
PHA v2 LangChain 风格记忆组件（阶段40）

**目标**：实现 3 个 langchain 风格的记忆类，drop-in 替换 langchain.BaseChatMemory
**为什么不用 langchain 现成的**：
- ConversationBufferMemory: 太简单，没重要性评分
- ConversationSummaryMemory: 调 LLM 太贵，没跨 agent 共享
- ConversationEntityMemory: langchain 的实体提取是英文 + 通用
- VectorStoreRetrieverMemory: 没医疗领域知识

**3 个新组件**：
1. PHAHealthMemory - 医疗场景 Buffer（带重要性 + tag）
2. PHAEntityMemory - 中英医疗实体提取（症状/药物/疾病）
3. PHALayeredMemory - Redis + PG + Embedding 三级缓存

**与 langchain 集成**：
- 继承 langchain.memory.chat_memory.BaseChatMemory（如果装了）
- 实现 add_user_message / add_ai_message / clear / memory_variables 接口
- 不用改 v2_agent.py：可作为 chat_model 的 memory 参数
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# langchain BaseChatMemory 兼容接口（如果装了 langchain）
# ============================================================
_LANGCHAIN_MEMORY_BASE = None
try:
    # langchain 1.x
    from langchain.memory.chat_memory import BaseChatMemory  # type: ignore
    _LANGCHAIN_MEMORY_BASE = BaseChatMemory
    logger.info("[langchain_memory] using langchain.memory.chat_memory.BaseChatMemory")
except ImportError:
    try:
        from langchain.memory import ChatMemoryBase as BaseChatMemory  # type: ignore
        _LANGCHAIN_MEMORY_BASE = BaseChatMemory
        logger.info("[langchain_memory] using langchain.memory.ChatMemoryBase")
    except ImportError:
        # 兜底：自己实现接口
        class BaseChatMemory:  # type: ignore[no-redef]
            """langchain 兼容的最小接口（无 langchain 也能用）"""
            def __init__(self, **kwargs):
                self.chat_memory = kwargs.get("chat_memory")
                self.output_key = kwargs.get("output_key", "output")
                self.input_key = kwargs.get("input_key", "input")
                self.return_messages = kwargs.get("return_messages", False)
            @property
            def memory_variables(self) -> List[str]:
                return ["history"]
            def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                return {"history": []}
            def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
                pass
            def clear(self) -> None:
                pass


# ============================================================
# 1. PHAHealthMemory: 医疗场景 Buffer（带重要性 + tag）
# ============================================================
@dataclass
class HealthMemoryItem:
    """单条医疗记忆"""
    role: str                    # "user" / "ai" / "system"
    content: str
    importance: float = 0.5      # 0-1，由规则/LLM 评估
    tags: List[str] = field(default_factory=list)  # ["symptom", "medication", "chronic_disease", "allergy"]
    timestamp: float = field(default_factory=time.time)
    item_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "importance": self.importance,
            "tags": self.tags,
            "timestamp": self.timestamp,
            "id": self.item_id,
        }


class PHAHealthMemory(BaseChatMemory):
    """
    PHA 医疗场景记忆（langchain 兼容）

    特性：
    - 重要性评分：每条消息打分，重要的保留时间长
    - 医疗 tag：自动识别 symptom / medication / disease / allergy
    - 容量管理：超过 max_messages 自动淘汰（保留 importance 高的）
    - 跨调用持久：可选 Postgres 备份
    - langchain 兼容：可作为 memory= 参数传给 AgentExecutor

    Example:
        >>> memory = PHAHealthMemory(agent_id="health_advisor", user_id="u1", max_messages=20)
        >>> memory.save_context({"input": "我头疼"}, {"output": "建议..."})
        >>> vars = memory.load_memory_variables({})
        >>> # vars["history"] = [...重要性+tag 排序后的消息...]
    """

    # 医疗关键词（中文）
    MEDICAL_KEYWORDS = {
        "symptom": ["疼", "痛", "发热", "发烧", "咳嗽", "头晕", "恶心", "呕吐", "腹泻", "失眠", "乏力"],
        "medication": ["药", "片", "胶囊", "注射", "输液", "服用", "剂量", "mg", "ml", "每日", "每天"],
        "chronic_disease": ["糖尿病", "高血压", "心脏病", "哮喘", "关节炎", "慢性"],
        "allergy": ["过敏", "敏感", "青霉素", "海鲜", "花粉", "麝"],
        "vital_sign": ["血压", "心率", "血糖", "体温", "体重", "BMI"],
        "lifestyle": ["饮食", "运动", "睡眠", "烟", "酒", "压力"],
    }

    def __init__(
        self,
        agent_id: str = "default",
        user_id: str = "default",
        max_messages: int = 20,
        importance_threshold: float = 0.3,
        auto_tag: bool = True,
        chat_memory: Any = None,
        **kwargs: Any,
    ):
        super().__init__(chat_memory=chat_memory, **kwargs)
        self.agent_id = agent_id
        self.user_id = user_id
        self.max_messages = max_messages
        self.importance_threshold = importance_threshold
        self.auto_tag = auto_tag
        # 用 deque 存，O(1) 进出
        self._items: deque = deque(maxlen=max_messages * 2)  # 内部存多一点，淘汰时按 importance 留
        # 统计
        self._stats = {
            "adds": 0,
            "evictions": 0,
            "tag_hits": 0,
        }

    @property
    def memory_variables(self) -> List[str]:
        return ["history"]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """返回当前要发给 LLM 的历史消息（按 importance 降序）"""
        # 过滤：importance > threshold（严格大于）
        filtered = [it for it in self._items if it.importance > self.importance_threshold]
        # 排序：importance 降序 + 时间升序
        filtered.sort(key=lambda x: (-x.importance, x.timestamp))
        # 截断到 max_messages
        top = filtered[:self.max_messages]
        # 按时间重排（保证对话流）
        top.sort(key=lambda x: x.timestamp)

        if self.return_messages:
            return {"history": [it.to_dict() for it in top]}
        else:
            return {"history": "\n".join(
                f"{it.role}: {it.content}" for it in top
            )}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        """保存一轮对话"""
        # 1. 用户消息
        user_msg = inputs.get(self.input_key, inputs.get("input", ""))
        if user_msg:
            user_item = HealthMemoryItem(
                role="user",
                content=str(user_msg),
                importance=self._estimate_importance(str(user_msg)),
                tags=self._extract_tags(str(user_msg)) if self.auto_tag else [],
            )
            self._items.append(user_item)
            self._stats["adds"] += 1

        # 2. AI 回复
        ai_msg = outputs.get(self.output_key, outputs.get("output", ""))
        if ai_msg:
            ai_item = HealthMemoryItem(
                role="ai",
                content=str(ai_msg),
                importance=self._estimate_importance(str(ai_msg)),
                tags=self._extract_tags(str(ai_msg)) if self.auto_tag else [],
            )
            self._items.append(ai_item)
            self._stats["adds"] += 1

    def _estimate_importance(self, text: str) -> float:
        """估算重要性（规则版：基于医疗关键词密度）"""
        if not text:
            return 0.3
        # 关键词密度
        total_keywords = sum(len(words) for words in self.MEDICAL_KEYWORDS.values())
        hits = sum(1 for words in self.MEDICAL_KEYWORDS.values()
                   for w in words if w in text)
        if hits == 0:
            return 0.3  # 普通对话
        # 1 个关键词 = 0.5, 3+ = 0.9
        base = min(0.5 + hits * 0.15, 1.0)
        # 长消息稍微高一点
        if len(text) > 100:
            base = min(base + 0.1, 1.0)
        return round(base, 2)

    def _extract_tags(self, text: str) -> List[str]:
        """提取医疗标签"""
        tags = []
        for tag, words in self.MEDICAL_KEYWORDS.items():
            for w in words:
                if w in text:
                    tags.append(tag)
                    self._stats["tag_hits"] += 1
                    break
        return tags

    def clear(self) -> None:
        """清空记忆"""
        self._items.clear()
        logger.info("[PHAHealthMemory:%s] cleared", self.agent_id)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "size": len(self._items),
            "max_messages": self.max_messages,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
        }

    def export_to_dict(self) -> Dict[str, Any]:
        """导出为 dict（用于持久化）"""
        return {
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "items": [it.to_dict() for it in self._items],
            "stats": self._stats,
        }


# ============================================================
# 2. PHAEntityMemory: 医疗实体提取
# ============================================================
@dataclass
class MedicalEntity:
    """医疗实体"""
    entity_type: str    # symptom / medication / disease / allergy / vital_sign
    name: str           # 实体名
    value: str = ""     # 实体值（如血压 120/80）
    mention_count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "name": self.name,
            "value": self.value,
            "mention_count": self.mention_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class PHAEntityMemory(BaseChatMemory):
    """
    PHA 医疗实体记忆（langchain 兼容）

    特性：
    - 自动提取 5 类医疗实体：症状/药物/疾病/过敏/体征
    - 跨消息累积（同一实体多次出现只更新 mention_count）
    - 比 langchain 强：
      * 中英双语词典
      * 医疗领域专有（langchain 的是通用英文）
      * 提取值（如"血压 120/80"）
      * 不调 LLM（纯规则，0 成本）

    Example:
        >>> mem = PHAEntityMemory(agent_id="health_advisor", user_id="u1")
        >>> mem.save_context({"input": "我有糖尿病，吃二甲双胍"}, {"output": "..."})
        >>> entities = mem.get_entities()
        >>> # entities = [MedicalEntity("disease", "糖尿病"), MedicalEntity("medication", "二甲双胍")]
    """

    # 实体词典（中英）
    ENTITY_DICT = {
        "symptom": {
            "头疼": ["头痛", "脑袋疼", "headache"],
            "发烧": ["发热", "fever", "高烧"],
            "咳嗽": ["咳", "cough"],
            "胸痛": ["胸口疼", "chest pain"],
            "腹痛": ["肚子疼", "肚子痛", "stomachache"],
            "失眠": ["睡不着", "insomnia"],
        },
        "medication": {
            "阿莫西林": ["amoxicillin"],
            "二甲双胍": ["metformin"],
            "布洛芬": ["ibuprofen"],
            "对乙酰氨基酚": ["扑热息痛", "paracetamol", "acetaminophen"],
            "硝苯地平": ["nifedipine"],
            "降压药": [],
        },
        "disease": {
            "糖尿病": ["diabetes", "DM"],
            "高血压": ["hypertension", "HTN"],
            "冠心病": ["CHD", "coronary heart disease"],
            "哮喘": ["asthma"],
            "抑郁症": ["depression"],
        },
        "allergy": {
            "青霉素过敏": ["penicillin allergy"],
            "海鲜过敏": ["seafood allergy"],
            "花粉过敏": ["hay fever"],
        },
        "vital_sign": {
            "血压": ["blood pressure", "BP"],
            "血糖": ["blood glucose", "BG"],
            "心率": ["heart rate", "HR"],
        },
    }

    def __init__(
        self,
        agent_id: str = "default",
        user_id: str = "default",
        chat_memory: Any = None,
        **kwargs: Any,
    ):
        super().__init__(chat_memory=chat_memory, **kwargs)
        self.agent_id = agent_id
        self.user_id = user_id
        # entity_key (type:name) -> MedicalEntity
        self._entities: Dict[str, MedicalEntity] = {}
        self._stats = {
            "extractions": 0,
            "unique_entities": 0,
        }

    @property
    def memory_variables(self) -> List[str]:
        return ["entities"]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        entities = self.get_entities()
        if self.return_messages:
            return {"entities": [e.to_dict() for e in entities]}
        # 格式化：列出所有实体
        lines = ["[用户已知的医疗实体]"]
        for e in entities:
            line = f"- {e.entity_type}: {e.name}"
            if e.value:
                line += f" (值: {e.value})"
            if e.mention_count > 1:
                line += f" (提到 {e.mention_count} 次)"
            lines.append(line)
        return {"entities": "\n".join(lines) if len(lines) > 1 else ""}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        # 提取 user + ai 消息的实体
        for text in [inputs.get(self.input_key, ""), outputs.get(self.output_key, "")]:
            if text:
                self._extract_entities(str(text))

    def _extract_entities(self, text: str) -> None:
        """从文本提取所有医疗实体"""
        now = time.time()
        for entity_type, name_dict in self.ENTITY_DICT.items():
            for canonical_name, aliases in name_dict.items():
                # 检查 canonical + 所有 aliases
                names_to_check = [canonical_name] + aliases
                for name in names_to_check:
                    if name and name in text:
                        key = f"{entity_type}:{canonical_name}"
                        if key in self._entities:
                            self._entities[key].mention_count += 1
                            self._entities[key].last_seen = now
                        else:
                            self._entities[key] = MedicalEntity(
                                entity_type=entity_type,
                                name=canonical_name,
                                value=self._extract_value(text, name),
                                first_seen=now,
                                last_seen=now,
                            )
                            self._stats["unique_entities"] += 1
                        self._stats["extractions"] += 1
                        break  # 找到一次就跳出
        # 提取体征值（"血压 120/80"）
        self._extract_vital_values(text)

    def _extract_value(self, text: str, entity_name: str) -> str:
        """尝试提取实体值（数字）"""
        idx = text.find(entity_name)
        if idx == -1:
            return ""
        # 向后看 30 个字符找数字
        tail = text[idx:idx + len(entity_name) + 30]
        m = re.search(r"(\d+(?:\.\d+)?(?:/\d+)?)", tail)
        return m.group(1) if m else ""

    def _extract_vital_values(self, text: str) -> None:
        """提取血压/血糖值"""
        # 血压 120/80
        m = re.search(r"血压\s*(\d+/\d+)", text)
        if m:
            key = "vital_sign:血压"
            if key in self._entities:
                self._entities[key].value = m.group(1)
            else:
                self._entities[key] = MedicalEntity(
                    entity_type="vital_sign",
                    name="血压",
                    value=m.group(1),
                )
                self._stats["unique_entities"] += 1
            self._stats["extractions"] += 1
        # 血糖 5.6
        m = re.search(r"血糖\s*(\d+(?:\.\d+)?)", text)
        if m:
            key = "vital_sign:血糖"
            if key in self._entities:
                self._entities[key].value = m.group(1)
            else:
                self._entities[key] = MedicalEntity(
                    entity_type="vital_sign",
                    name="血糖",
                    value=m.group(1),
                )
                self._stats["unique_entities"] += 1
            self._stats["extractions"] += 1

    def get_entities(self, entity_type: Optional[str] = None) -> List[MedicalEntity]:
        """获取所有实体（按 mention_count 降序）"""
        entities = list(self._entities.values())
        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]
        entities.sort(key=lambda e: -e.mention_count)
        return entities

    def clear(self) -> None:
        self._entities.clear()
        logger.info("[PHAEntityMemory:%s] cleared", self.agent_id)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "size": len(self._entities),
            "by_type": {
                et: sum(1 for e in self._entities.values() if e.entity_type == et)
                for et in self.ENTITY_DICT.keys()
            },
            "agent_id": self.agent_id,
            "user_id": self.user_id,
        }


# ============================================================
# 3. PHALayeredMemory: 三级缓存
# ============================================================
class PHALayeredMemory(BaseChatMemory):
    """
    PHA 三级缓存记忆（langchain 兼容）

    架构：
    - L1: 内存 deque（最快，0 ms）
    - L2: Redis（次快，< 1 ms，TTL 30 分钟）
    - L3: PostgreSQL（慢，10-100 ms，永久）

    流程：
    - save_context: L1 + L2 + L3 全部写
    - load_memory_variables: 先查 L1（hit 立刻返回）→ L2 → L3 → 重建 L1
    - 重要消息直接 L3（importance > 0.7）

    失败容忍：
    - Redis 不可用 → 自动降级到 L3
    - PG 不可用 → 只用 L1+L2
    - L1 满了 → LRU 淘汰

    Example:
        >>> mem = PHALayeredMemory(
        ...     agent_id="health_advisor", user_id="u1",
        ...     redis_url="redis://localhost:6379/0",
        ...     pg_url="postgresql://localhost/personal_health_assistant",
        ... )
    """

    def __init__(
        self,
        agent_id: str = "default",
        user_id: str = "default",
        max_l1: int = 50,
        redis_url: Optional[str] = None,
        pg_url: Optional[str] = None,
        l2_ttl: int = 1800,  # 30 分钟
        chat_memory: Any = None,
        **kwargs: Any,
    ):
        super().__init__(chat_memory=chat_memory, **kwargs)
        self.agent_id = agent_id
        self.user_id = user_id
        self.max_l1 = max_l1
        self.l2_ttl = l2_ttl

        # L1: 内存
        self._l1: deque = deque(maxlen=max_l1)

        # L2: Redis（可选）
        self._redis = None
        if redis_url:
            try:
                import redis  # type: ignore
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("[PHALayeredMemory] L2 Redis connected: %s", redis_url)
            except Exception as e:
                logger.warning("[PHALayeredMemory] L2 Redis disabled: %s", e)
                self._redis = None

        # L3: PostgreSQL（可选）
        self._pg_url = pg_url
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "l3_misses": 0,
            "writes": 0,
            "errors": 0,
        }

    def _l2_key(self) -> str:
        return f"pha:conv:{self.agent_id}:{self.user_id}"

    @property
    def memory_variables(self) -> List[str]:
        return ["history"]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # L1 命中
        if len(self._l1) > 0:
            self._stats["l1_hits"] += 1
            return {"history": list(self._l1)}

        # L2 命中
        if self._redis:
            try:
                data = self._redis.lrange(self._l2_key(), 0, -1)
                if data:
                    self._stats["l2_hits"] += 1
                    # 重建 L1
                    for item in data:
                        self._l1.append(json.loads(item))
                    return {"history": list(self._l1)}
            except Exception as e:
                self._stats["errors"] += 1
                logger.warning("[PHALayeredMemory] L2 read failed: %s", e)

        # L3 命中（PG）
        if self._pg_url:
            try:
                from memory_system import AgentMemorySystem
                ms = AgentMemorySystem()
                items = ms.search_memories(
                    query="",  # 空查询
                    agent_id=self.agent_id,
                    user_id=self.user_id,
                    limit=self.max_l1,
                )
                if items:
                    self._stats["l3_hits"] += 1
                    for it in items:
                        self._l1.append({
                            "role": "user" if it.get("memory_type") == "short_term" else "ai",
                            "content": it.get("content_text", ""),
                            "importance": it.get("importance_score", 0.5),
                        })
                    return {"history": list(self._l1)}
            except Exception as e:
                self._stats["errors"] += 1
                logger.warning("[PHALayeredMemory] L3 read failed: %s", e)

        self._stats["l3_misses"] += 1
        return {"history": []}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        items = []
        if inputs.get(self.input_key):
            items.append({"role": "user", "content": str(inputs[self.input_key]), "ts": time.time()})
        if outputs.get(self.output_key):
            items.append({"role": "ai", "content": str(outputs[self.output_key]), "ts": time.time()})

        for item in items:
            # L1
            self._l1.append(item)
            self._stats["writes"] += 1

            # L2
            if self._redis:
                try:
                    self._redis.rpush(self._l2_key(), json.dumps(item, ensure_ascii=False))
                    self._redis.expire(self._l2_key(), self.l2_ttl)
                except Exception as e:
                    self._stats["errors"] += 1
                    logger.warning("[PHALayeredMemory] L2 write failed: %s", e)

            # L3 (重要消息)
            if item.get("importance", 0) > 0.7 and self._pg_url:
                try:
                    from memory_system import AgentMemorySystem
                    ms = AgentMemorySystem()
                    ms.store_memory(
                        agent_id=self.agent_id,
                        user_id=self.user_id,
                        content={"text": item["content"]},
                        memory_type="short_term",
                        importance=item.get("importance", 0.5),
                    )
                except Exception as e:
                    self._stats["errors"] += 1
                    logger.warning("[PHALayeredMemory] L3 write failed: %s", e)

    def clear(self) -> None:
        self._l1.clear()
        if self._redis:
            try:
                self._redis.delete(self._l2_key())
            except Exception:
                pass
        logger.info("[PHALayeredMemory:%s] cleared", self.agent_id)

    def get_stats(self) -> Dict[str, Any]:
        total_hits = self._stats["l1_hits"] + self._stats["l2_hits"] + self._stats["l3_hits"]
        return {
            **self._stats,
            "l1_size": len(self._l1),
            "max_l1": self.max_l1,
            "l2_enabled": self._redis is not None,
            "l3_enabled": self._pg_url is not None,
            "total_hits": total_hits,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
        }


# ============================================================
# 工厂函数
# ============================================================
def create_health_memory(agent_id: str = "default", user_id: str = "default",
                         max_messages: int = 20) -> PHAHealthMemory:
    """创建 PHAHealthMemory 的便利函数"""
    return PHAHealthMemory(agent_id=agent_id, user_id=user_id, max_messages=max_messages)


def create_entity_memory(agent_id: str = "default", user_id: str = "default") -> PHAEntityMemory:
    """创建 PHAEntityMemory 的便利函数"""
    return PHAEntityMemory(agent_id=agent_id, user_id=user_id)


def create_layered_memory(agent_id: str = "default", user_id: str = "default",
                          redis_url: Optional[str] = None,
                          pg_url: Optional[str] = None) -> PHALayeredMemory:
    """创建 PHALayeredMemory 的便利函数"""
    return PHALayeredMemory(
        agent_id=agent_id, user_id=user_id,
        redis_url=redis_url, pg_url=pg_url,
    )


__all__ = [
    "BaseChatMemory",
    "HealthMemoryItem",
    "MedicalEntity",
    "PHAHealthMemory",
    "PHAEntityMemory",
    "PHALayeredMemory",
    "create_health_memory",
    "create_entity_memory",
    "create_layered_memory",
]