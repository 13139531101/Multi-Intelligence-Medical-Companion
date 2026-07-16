"""
PHA v2 性能监控 + 报警（阶段38-3）

**作用**：基于 monitoring.py 的指标，加阈值报警系统

**功能**：
- AlertRule: 报警规则（指标 + 阈值 + 比较符）
- AlertManager: 报警管理器（评估规则 + 触发报警 + 历史）
- 报警通道：日志 / Webhook / 邮件（接口预留）
- 报警历史：内存最近 100 条

**用法**：
    manager = get_alert_manager()
    manager.add_rule(AlertRule("error_rate", ">", 0.1, severity="warning"))
    await manager.evaluate(metrics)  # 每次 scrape 时调
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 1. 严重度 + 报警规则
# ============================================================

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """单个报警规则"""
    name: str                              # 唯一名
    metric_path: str                       # 指标路径，如 "request.error_rate" 或 "llm.error_rate"
    comparator: str                        # > / < / >= / <= / == / !=
    threshold: float                       # 阈值
    severity: Severity = Severity.WARNING  # 严重度
    description: str = ""                  # 描述
    enabled: bool = True                   # 是否启用

    def evaluate(self, value: float) -> bool:
        """评估指标是否触发"""
        if not self.enabled:
            return False
        if self.comparator == ">":
            return value > self.threshold
        elif self.comparator == "<":
            return value < self.threshold
        elif self.comparator == ">=":
            return value >= self.threshold
        elif self.comparator == "<=":
            return value <= self.threshold
        elif self.comparator == "==":
            return value == self.threshold
        elif self.comparator == "!=":
            return value != self.threshold
        return False


@dataclass
class Alert:
    """一次触发的报警实例"""
    rule_name: str
    severity: Severity
    metric_path: str
    value: float
    threshold: float
    comparator: str
    description: str
    triggered_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


# ============================================================
# 2. 报警管理器
# ============================================================

class AlertManager:
    """报警管理器（单例）"""

    def __init__(self, max_history: int = 100):
        self._rules: Dict[str, AlertRule] = {}
        self._active: Dict[str, Alert] = {}  # 当前触发的报警
        self._history: Deque[Alert] = deque(maxlen=max_history)
        self._handlers: List[Callable[[Alert], None]] = []
        self._stats = {
            "total_triggered": 0,
            "total_resolved": 0,
            "total_evaluations": 0,
        }
        self._init_default_rules()

    def _init_default_rules(self):
        """默认报警规则"""
        # 错误率 > 10% 警告，> 30% 严重
        self.add_rule(AlertRule(
            name="request_error_rate_high",
            metric_path="request.error_rate",
            comparator=">",
            threshold=0.10,
            severity=Severity.WARNING,
            description="请求错误率超过 10%",
        ))
        self.add_rule(AlertRule(
            name="request_error_rate_critical",
            metric_path="request.error_rate",
            comparator=">",
            threshold=0.30,
            severity=Severity.CRITICAL,
            description="请求错误率超过 30%",
        ))
        # LLM 错误率 > 20%
        self.add_rule(AlertRule(
            name="llm_error_rate_high",
            metric_path="llm.error_rate",
            comparator=">",
            threshold=0.20,
            severity=Severity.ERROR,
            description="LLM API 错误率超过 20%",
        ))
        # P95 延迟 > 10 秒
        self.add_rule(AlertRule(
            name="p95_latency_high",
            metric_path="request.p95",
            comparator=">",
            threshold=10.0,
            severity=Severity.WARNING,
            description="P95 延迟超过 10 秒",
        ))
        # 缓存命中率 < 30%
        self.add_rule(AlertRule(
            name="cache_hit_rate_low",
            metric_path="cache.hit_rate",
            comparator="<",
            threshold=30.0,
            severity=Severity.INFO,
            description="缓存命中率低于 30%",
        ))

    def add_rule(self, rule: AlertRule):
        self._rules[rule.name] = rule
        logger.info("[alert] rule added: %s (%s %s %s)",
                    rule.name, rule.metric_path, rule.comparator, rule.threshold)

    def remove_rule(self, name: str):
        self._rules.pop(name, None)
        self._active.pop(name, None)

    def list_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": r.name,
                "metric_path": r.metric_path,
                "comparator": r.comparator,
                "threshold": r.threshold,
                "severity": r.severity.value,
                "description": r.description,
                "enabled": r.enabled,
                "active": r.name in self._active,
            }
            for r in self._rules.values()
        ]

    def add_handler(self, handler: Callable[[Alert], None]):
        """添加报警 handler（用于 webhook / 邮件）"""
        self._handlers.append(handler)

    def _get_metric(self, path: str, metrics: dict) -> float:
        """从 metrics 字典里按 path 取值（支持 'a.b.c'）"""
        parts = path.split(".")
        val = metrics
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
                if val is None:
                    return 0.0
            else:
                return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    async def evaluate(self, metrics: dict):
        """评估所有规则（每次 scrape 时调）"""
        self._stats["total_evaluations"] += 1
        for rule in self._rules.values():
            value = self._get_metric(rule.metric_path, metrics)
            triggered = rule.evaluate(value)
            if triggered:
                if rule.name not in self._active:
                    # 新触发
                    alert = Alert(
                        rule_name=rule.name,
                        severity=rule.severity,
                        metric_path=rule.metric_path,
                        value=value,
                        threshold=rule.threshold,
                        comparator=rule.comparator,
                        description=rule.description,
                        message=f"[{rule.severity.value.upper()}] {rule.description}: "
                                f"{rule.metric_path}={value:.4f} {rule.comparator} {rule.threshold}",
                    )
                    self._active[rule.name] = alert
                    self._history.append(alert)
                    self._stats["total_triggered"] += 1
                    logger.warning("[alert] TRIGGERED: %s", alert.message)
                    # 通知所有 handler
                    for handler in self._handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(alert)
                            else:
                                handler(alert)
                        except Exception as e:
                            logger.exception("[alert] handler failed: %s", e)
            else:
                # 解除报警
                if rule.name in self._active:
                    alert = self._active.pop(rule.name)
                    alert.resolved_at = time.time()
                    self._stats["total_resolved"] += 1
                    logger.info("[alert] RESOLVED: %s (duration: %.1fs)",
                                rule.name, alert.resolved_at - alert.triggered_at)

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._active.values()]

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in list(self._history)[-limit:]]

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "active_count": len(self._active),
            "rule_count": len(self._rules),
            "history_size": len(self._history),
        }


# ============================================================
# 3. 单例 + 内置 handler
# ============================================================

_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        # 加 webhook handler
        webhook_url = os.getenv("PHA_ALERT_WEBHOOK_URL", "")
        if webhook_url:
            _alert_manager.add_handler(make_webhook_handler(webhook_url))
    return _alert_manager


def make_webhook_handler(url: str):
    """构造 webhook handler"""
    import httpx

    async def webhook_handler(alert: Alert):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=alert.to_dict())
        except Exception as e:
            logger.warning("[alert] webhook failed: %s", e)

    return webhook_handler


__all__ = [
    "Severity",
    "AlertRule",
    "Alert",
    "AlertManager",
    "get_alert_manager",
]