"""
PHASE 8: 推理过程可视化 - ReasoningTracer

记录智能体的推理链，供前端展示思考过程。
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    step_id: int
    step_type: str  # "tool_call" | "tool_result" | "reasoning" | "llm_response" | "critique"
    content: str
    tool_name: Optional[str] = None
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReasoningTrace:
    trace_id: str
    query: str
    user_id: str
    steps: list[ReasoningStep] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def duration_ms(self) -> float:
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "user_id": self.user_id,
            "duration_ms": round(self.duration_ms(), 1),
            "steps": [
                {
                    "step_id": s.step_id,
                    "type": s.step_type,
                    "content": s.content,
                    "tool": s.tool_name,
                    "latency_ms": round(s.latency_ms, 1),
                    "timestamp": s.timestamp,
                }
                for s in self.steps
            ],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class ReasoningTracer:
    """
    推理链记录器（PHASE 8）

    用法：
        tracer = ReasoningTracer()
        tracer.start_trace("trace_123", "用户问题", "user_1")
        tracer.add_step("tool_call", "get_health_records", content="调用健康档案工具")
        tracer.add_step("tool_result", "get_health_records", content="返回 5 条记录")
        tracer.end_trace()
    """

    def __init__(self, max_traces: int = 100):
        self.max_traces = max_traces
        self._traces: OrderedDict[str, ReasoningTrace] = OrderedDict()
        self._current_trace: Optional[ReasoningTrace] = None
        self._step_counter: int = 0

    def start_trace(self, trace_id: str, query: str, user_id: str) -> ReasoningTrace:
        """开始一个新的推理链"""
        self._current_trace = ReasoningTrace(
            trace_id=trace_id,
            query=query,
            user_id=user_id,
        )
        self._step_counter = 0
        logger.info(f"[reasoning_tracer] started trace_id={trace_id}, query={query!r}")
        return self._current_trace

    def add_step(
        self,
        step_type: str,
        content: str,
        tool_name: str = None,
        latency_ms: float = 0.0,
    ) -> ReasoningStep:
        """记录一个推理步骤"""
        if not self._current_trace:
            logger.warning("[reasoning_tracer] add_step called but no active trace")
            return None

        self._step_counter += 1
        step = ReasoningStep(
            step_id=self._step_counter,
            step_type=step_type,
            content=content,
            tool_name=tool_name,
            latency_ms=latency_ms,
        )
        self._current_trace.steps.append(step)
        return step

    def end_trace(self) -> ReasoningTrace:
        """结束当前推理链"""
        if not self._current_trace:
            return None

        self._current_trace.completed_at = time.time()
        trace = self._current_trace

        # 保存到 LRU 字典
        self._traces[trace.trace_id] = trace
        if len(self._traces) > self.max_traces:
            self._traces.popitem(last=False)  # 删除最旧的

        logger.info(
            f"[reasoning_tracer] ended trace_id={trace.trace_id}, "
            f"steps={len(trace.steps)}, duration={trace.duration_ms():.0f}ms"
        )
        self._current_trace = None
        return trace

    def get_trace(self, trace_id: str) -> Optional[ReasoningTrace]:
        return self._traces.get(trace_id)

    def list_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """列出最近的推理链"""
        traces = list(self._traces.values())[-limit:]
        return [t.to_dict() for t in reversed(traces)]

    def stats(self) -> dict[str, Any]:
        return {
            "total_traces": len(self._traces),
            "max_traces": self.max_traces,
            "active_trace": self._current_trace.trace_id if self._current_trace else None,
        }


# ============================================================
# 全局单例
# ============================================================
_tracer: Optional[ReasoningTracer] = None


def get_tracer() -> ReasoningTracer:
    global _tracer
    if _tracer is None:
        _tracer = ReasoningTracer()
    return _tracer


__all__ = [
    "ReasoningTracer",
    "ReasoningTrace",
    "ReasoningStep",
    "get_tracer",
]
