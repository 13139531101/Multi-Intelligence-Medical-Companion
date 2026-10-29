"""Agent 行为评测公共件 —— WS-A

与 rag_eval_common.py 完全独立，不复用其 math（agent 评测的指标家族完全不同）：
- routing_accuracy  (top-1 / top-k)
- tool_precision / recall / f1 / forbidden_violations
- abstention_rate  (must_abstain cases 应拒答; 非 must_abstain cases 不应拒答)
- citation_recall / precision
- multi_turn_memory_hit_rate

设计原则：
- 解析 AG-UI SSE 流（与 tests/e2e/agui_smoke.py:61-75 模式一致）
- 每 case 跑一次生产入口 /api/copilotkit，全黑盒，与前端真实路径一致
- 评测集 case schema 比 RAG case 复杂得多（optional 字段多），所以单建一个 dataclass

事件 schema 对齐 frontend/hostAgentAPI/copilotkit_runtime.py:
  TEXT_MESSAGE_CONTENT:  {messageId, delta}
  TOOL_CALL_START:       {toolCallId, toolCallName, parentMessageId}
  TOOL_CALL_ARGS:        {toolCallId, delta}      ← delta 是 args 的 JSON 字符串
  TOOL_CALL_END:         {toolCallId}
  TOOL_CALL_RESULT:      {messageId, toolCallId, role, toolCallName, content?}
  CUSTOM:                {name, value}            ← name 标识扩展事件
    name=routing → value={agent, routing:{layer, ...}}
    name=PAGE_UPDATE → value={...}
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# 评测 case schema
# ============================================================
@dataclass
class AgentEvalCase:
    id: str
    category: str  # "routing" | "tool_selection" | "abstention" | "citation" | "multi_turn_memory"
    query: str
    # routing
    expected_agent: str = ""
    top_k_acceptable: list[str] = field(default_factory=list)
    # tool selection
    expected_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    # abstention
    must_abstain: bool = False
    # citation
    expected_citation_count: int = 0
    # multi_turn memory
    conversation_history: list[dict] = field(default_factory=list)
    memory_recall_queries: list[str] = field(default_factory=list)
    # metadata
    user_id: str = "agent_eval_user"
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


def load_agent_cases(file_path: str) -> list[AgentEvalCase]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"评测集文件不存在: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("评测集必须是 JSON 数组")
    cases: list[AgentEvalCase] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id", "")).strip()
        cat = str(row.get("category", "")).strip()
        q = str(row.get("query", "")).strip()
        if not (cid and cat and q):
            continue
        cases.append(AgentEvalCase(
            id=cid,
            category=cat,
            query=q,
            expected_agent=str(row.get("expected_agent", "")).strip(),
            top_k_acceptable=[str(x) for x in row.get("top_k_acceptable", []) or []],
            expected_tools=[str(x) for x in row.get("expected_tools", []) or []],
            forbidden_tools=[str(x) for x in row.get("forbidden_tools", []) or []],
            must_abstain=bool(row.get("must_abstain", False)),
            expected_citation_count=int(row.get("expected_citation_count", 0)),
            conversation_history=list(row.get("conversation_history", []) or []),
            memory_recall_queries=[str(x) for x in row.get("memory_recall_queries", []) or []],
            user_id=str(row.get("user_id", "")).strip() or "agent_eval_user",
            metadata=dict(row.get("metadata", {}) or {}),
            tags=[str(x) for x in row.get("tags", []) or []],
        ))
    if not cases:
        raise ValueError("评测集为空")
    return cases


# ============================================================
# AG-UI SSE 客户端（最小实现，与 agui_smoke.py 共享思路）
# ============================================================
def call_agui(
    base_url: str,
    message: str,
    token: str,
    conversation_history: list[dict] | None = None,
    metadata: dict | None = None,
    timeout: int = 120,
) -> dict:
    """POST /api/copilotkit，解析 SSE 流，返回聚合结果。

    Returns:
        {
            "routing": {"agent": str|None, "layer": int|None,
                        "all_routing_events": list[dict], "routing_history": list[str]},
            "tool_calls": [{"name": str, "args": dict, "result": Any}, ...],
            "text": str,                     # 拼接所有 TEXT_MESSAGE_CONTENT.delta
            "citation_count": int,           # 文本中含 '[' + 字母数字 + ']' 的总数
            "abstained": bool,               # 文本含拒答/就医/escalate 关键词
            "elapsed_sec": float,
            "raw_events": list,              # 全部 AG-UI 事件
        }

    Schema 依据：frontend/hostAgentAPI/copilotkit_runtime.py:235-285
    """
    body: dict[str, Any] = {
        "message": message,
    }
    if conversation_history:
        body["conversation_history"] = conversation_history
    if metadata:
        body["metadata"] = metadata

    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/copilotkit",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "text/event-stream")

    t0 = time.perf_counter()
    events: list[dict] = []
    text_parts: list[str] = []
    tool_calls_by_id: dict[str, dict] = {}  # toolCallId → {name, args, result}
    tool_order: list[str] = []               # 保留调用顺序
    routing_events: list[dict] = []         # CUSTOM{name="routing"} 全部累计

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except Exception:
                    continue
                if not isinstance(ev, dict):
                    continue
                events.append(ev)
                et = ev.get("type", "")
                if et == "TEXT_MESSAGE_CONTENT":
                    delta = ev.get("delta") or ""
                    if isinstance(delta, str):
                        text_parts.append(delta)
                elif et == "TOOL_CALL_START":
                    # 工具名在 toolCallName（AG-UI 标准字段）
                    tc_id = ev.get("toolCallId") or ""
                    tc_name = ev.get("toolCallName") or "?"
                    if tc_id not in tool_calls_by_id:
                        tool_calls_by_id[tc_id] = {
                            "name": tc_name,
                            "args": {},
                            "result": None,
                        }
                        tool_order.append(tc_id)
                elif et == "TOOL_CALL_ARGS":
                    # delta 是 args 的 JSON 字符串，可能分片；尝试累加解析
                    tc_id = ev.get("toolCallId") or ""
                    delta_raw = ev.get("delta") or ""
                    if tc_id in tool_calls_by_id and delta_raw:
                        # 简单累加为字符串，最后一次性 parse
                        cur = tool_calls_by_id[tc_id]
                        if not cur["args"]:
                            cur["args_raw"] = ""
                        cur["args_raw"] = (cur.get("args_raw") or "") + delta_raw
                elif et == "TOOL_CALL_RESULT":
                    # 关联到对应 toolCallId
                    tc_id = ev.get("toolCallId") or ""
                    content = ev.get("content")
                    if content is None:
                        # 部分 schema 用 'output' 字段
                        content = ev.get("output")
                    if tc_id in tool_calls_by_id:
                        tool_calls_by_id[tc_id]["result"] = content
                    else:
                        # result 来了但没看到 START（流被截断？），仍记录
                        tool_calls_by_id[tc_id] = {
                            "name": ev.get("toolCallName") or "?",
                            "args": {},
                            "result": content,
                        }
                        tool_order.append(tc_id)
                elif et == "CUSTOM":
                    name = ev.get("name", "")
                    if name == "routing":
                        # value = {"agent": str, "routing": {"layer": int, ...}}
                        value = ev.get("value") or {}
                        routing_events.append(value if isinstance(value, dict) else {})
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {
            "error": str(e),
            "routing": {
                "agent": None,
                "layer": None,
                "all_routing_events": [],
                "routing_history": [],
            },
            "tool_calls": [],
            "text": "",
            "citation_count": 0,
            "abstained": False,
            "elapsed_sec": round(time.perf_counter() - t0, 3),
            "raw_events": events,
        }

    # 把累积的 args_raw 解析成 dict
    for tc in tool_calls_by_id.values():
        raw = tc.pop("args_raw", None)
        if raw:
            try:
                tc["args"] = json.loads(raw)
            except Exception:
                tc["args"] = {"_raw": raw}

    tool_calls = [tool_calls_by_id[tc_id] for tc_id in tool_order if tc_id in tool_calls_by_id]
    text = "".join(text_parts)

    # routing 收尾：取最后一个 routing 事件作为最终路由
    final_agent = None
    final_layer = None
    routing_history: list[str] = []
    for rv in routing_events:
        if not isinstance(rv, dict):
            continue
        ag = rv.get("agent")
        if ag:
            routing_history.append(str(ag))
        if not final_agent:
            final_agent = ag
        r_block = rv.get("routing") or {}
        if isinstance(r_block, dict):
            lyr = r_block.get("layer")
        else:
            lyr = rv.get("layer")
        if lyr is not None:
            try:
                final_layer = int(lyr)
            except (ValueError, TypeError):
                final_layer = None

    # citation 粗判：文本中 [eval-XX-NNN] 或 [source_id] 这种带方括号的引用
    citation_count = len(re.findall(r"\[[A-Za-z0-9_\-:]+\]", text))

    # abstention 粗判：含"建议就医/不能/无法/请咨询医生/无法提供/escalate"等关键词
    abstention_kw = ("建议就医", "请咨询医生", "无法提供", "无法回答",
                     "escalate", "请就医", "请立即就医", "不能给药", "不能开药")
    abstained = any(kw in text for kw in abstention_kw)

    return {
        "routing": {
            "agent": final_agent,
            "layer": final_layer,
            "all_routing_events": routing_events,
            "routing_history": routing_history,
        },
        "tool_calls": tool_calls,
        "text": text,
        "citation_count": citation_count,
        "abstained": abstained,
        "elapsed_sec": round(time.perf_counter() - t0, 3),
        "raw_events": events,
    }


# ============================================================
# 5 个指标家族
# ============================================================
def routing_metrics(per_case: list[dict]) -> dict:
    """per_case: [{'expected_agent','top_k_acceptable','actual_agent','layer','pass_top1','pass_topk'}]"""
    n = len(per_case)
    if n == 0:
        return {"cases": 0, "top1_accuracy": 0.0, "top_k_accuracy": 0.0, "by_layer": {}}
    top1 = sum(1 for c in per_case if c["pass_top1"])
    topk = sum(1 for c in per_case if c["pass_topk"])
    by_layer: dict[str, dict[str, int]] = {}
    for c in per_case:
        l = c.get("layer")
        lk = f"layer{int(l)}" if l is not None else "unknown"
        if lk not in by_layer:
            by_layer[lk] = {"correct": 0, "total": 0}
        by_layer[lk]["total"] += 1
        if c["pass_top1"]:
            by_layer[lk]["correct"] += 1
    return {
        "cases": n,
        "top1_accuracy": round(top1 / n, 4),
        "top_k_accuracy": round(topk / n, 4),
        "by_layer": by_layer,
    }


def tool_metrics(per_case: list[dict]) -> dict:
    """per_case: [{'expected_tools','forbidden_tools','actual_tools'}]"""
    n = len(per_case)
    if n == 0:
        return {"cases": 0, "tool_precision": 0.0, "tool_recall": 0.0, "tool_f1": 0.0, "forbidden_violations": 0}
    p_total = r_total = f1_total = 0.0
    forbidden_viol = 0
    for c in per_case:
        exp = set(c["expected_tools"])
        forb = set(c["forbidden_tools"])
        act = set(c["actual_tools"])
        if exp:
            tp = len(exp & act)
            p = tp / len(act) if act else 0.0
            r = tp / len(exp) if exp else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        else:
            # 没期望工具 = 只看 forbidden 是否被调用
            p = r = f1 = 1.0 if not (forb & act) else 0.0
        p_total += p
        r_total += r
        f1_total += f1
        forbidden_viol += len(forb & act)
    return {
        "cases": n,
        "tool_precision": round(p_total / n, 4),
        "tool_recall": round(r_total / n, 4),
        "tool_f1": round(f1_total / n, 4),
        "forbidden_violations": forbidden_viol,
    }


def abstention_metrics(per_case: list[dict]) -> dict:
    """per_case: [{'must_abstain','abstained'}]"""
    n = len(per_case)
    if n == 0:
        return {"cases": 0, "abstention_rate": 0.0, "false_abstention_rate": 0.0}
    must_n = sum(1 for c in per_case if c["must_abstain"])
    no_n = n - must_n
    correct_abstain = sum(1 for c in per_case if c["must_abstain"] and c["abstained"])
    false_abstain = sum(1 for c in per_case if (not c["must_abstain"]) and c["abstained"])
    return {
        "cases": n,
        "abstention_rate": round(correct_abstain / must_n, 4) if must_n else 0.0,
        "false_abstention_rate": round(false_abstain / no_n, 4) if no_n else 0.0,
    }


def citation_metrics(per_case: list[dict]) -> dict:
    """per_case: [{'expected_citation_count','citation_count'}]"""
    n = len(per_case)
    if n == 0:
        return {"cases": 0, "citation_recall": 0.0, "citation_precision": 0.0}
    correct_recall = sum(1 for c in per_case if c["citation_count"] >= c["expected_citation_count"])
    correct_prec = sum(1 for c in per_case if c["citation_count"] == c["expected_citation_count"] and c["expected_citation_count"] > 0)
    labeled = sum(1 for c in per_case if c["expected_citation_count"] > 0)
    return {
        "cases": n,
        "citation_recall": round(correct_recall / n, 4),  # 包含 expected=0 的 case
        "citation_precision": round(correct_prec / labeled, 4) if labeled else 0.0,
    }


def memory_metrics(per_case: list[dict]) -> dict:
    """per_case: [{'history_used','memory_recall_queries','text'}] — 粗判：文本含 history 中任一关键词"""
    n = len(per_case)
    if n == 0:
        return {"cases": 0, "hit_rate": 0.0}
    hit = 0
    for c in per_case:
        text = c.get("text", "")
        keywords = c.get("memory_recall_queries", [])
        if not keywords:
            # 没设 keyword = 期望 history_used=True
            if c.get("history_used"):
                hit += 1
            continue
        if any(kw in text for kw in keywords):
            hit += 1
    return {
        "cases": n,
        "hit_rate": round(hit / n, 4),
    }
