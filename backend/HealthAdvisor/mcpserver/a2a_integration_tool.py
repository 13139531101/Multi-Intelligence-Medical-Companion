from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any, List, Optional
import uuid
import os
import requests
import concurrent.futures
from datetime import datetime, timedelta

mcp = FastMCP("HealthAdvisorA2AIntegrationTool")

def _normalize_address(addr: str) -> str:
    try:
        if addr.startswith("http://") or addr.startswith("https://"):
            return addr.rstrip("/")
        host = addr.split("/")[0]
        svc_map = {
            "health_records": "10010",
            "health_advisor": "10011",
            "medication_reminder": "10012",
            "visit_summary": "10013",
        }
        # Prefer service DNS in container/k8s environments
        if host in svc_map:
            return f"http://{host}:{svc_map[host]}"
        # Accept patterns like service:port
        if ":" in host:
            parts = host.split(":", 1)
            return f"http://{parts[0]}:{parts[1]}"
        return f"http://{host}"
    except Exception:
        return addr

def _fetch_agent_card(base: str) -> Dict[str, Any]:
    url = f"{_normalize_address(base)}/.well-known/agent.json"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"url": url, "error": "fetch_agent_card_failed", "message": str(e)}

def _resolve_endpoint(agent_address: str) -> str:
    base = _normalize_address(agent_address)
    try:
        card = _fetch_agent_card(agent_address)
        url = str(card.get("url", base)).rstrip("/")
        if any(h in url for h in ("127.0.0.1", "localhost")):
            return base
        return url
    except Exception:
        return base

def _send_task(agent_endpoint_url: str, tool_instruction_text: str, session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    env_uid = None
    try:
        env_uid = os.environ.get("A2A_CURRENT_USER_ID") or os.environ.get("USER_ID")
    except Exception:
        env_uid = None
    body = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "id": str(uuid.uuid4()),
            "sessionId": session_id or str(uuid.uuid4()),
            "acceptedOutputModes": ["text", "data"],
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": tool_instruction_text}],
            },
            "metadata": ({"user_id": (user_id or env_uid)} if (user_id or env_uid) else None),
        },
        "id": str(uuid.uuid4()),
    }
    headers = {}
    try:
        token = os.environ.get('HOSTAPI_AUTH_TOKEN') or os.environ.get('A2A_AUTH_TOKEN')
        if isinstance(token, str) and token.strip():
            # Ensure Bearer prefix for JWT parsing on server side
            headers['Authorization'] = f"Bearer {token.strip()}"
    except Exception:
        pass
    try:
        r = requests.post(_resolve_endpoint(agent_endpoint_url), json=body, headers=headers or None, timeout=45)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": "send_task_failed", "message": str(e)}

def _send_call_tool(agent_endpoint_url: str, tool_name: str, tool_args: Dict[str, Any], session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    instr = (
        f"必须仅调用一次名为 {tool_name} 的工具，参数为 {json.dumps(tool_args, ensure_ascii=False)}。"
        f"禁止写入或修改数据库，不要生成普通文本，直接返回工具的原始JSON。"
    )
    return _send_task(agent_endpoint_url, instr, session_id=session_id, user_id=user_id)


def get_health_records_overview(agent_address: str, user_id: Optional[str] = "", days: int = 180) -> Dict[str, Any]:
    card = _fetch_agent_card(agent_address)
    endpoint = _resolve_endpoint(agent_address)
    instr = (
        f"必须调用工具完成查询，不要输出说明文字。"
        f"优先调用：StorageTool_get_health_records 或 MemoryIntegrationTool_get_health_history，参数仅包含当前用户与时间范围。"
        f"请根据工具返回结果生成JSON：{'stats': {record_type: count}, 'examples': [{id,type,title,created_at,excerpt}]}，示例最多10条。"
        f"禁止长文本生成，若工具不可用请返回 {'error':'tool_unavailable'}。时间范围：最近 {days} 天。"
    )
    try:
        data = _send_call_tool(endpoint, "MemoryIntegrationTool_get_health_history", {"user_id": user_id, "days": days}, user_id=user_id)
        return {"success": True, "agent": card.get("name"), "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
def get_medication_overview(agent_address: str, user_id: Optional[str] = "") -> Dict[str, Any]:
    """通过A2A协议获取药物提醒Agent的用药概览，返回当前用药和已停药列表"""
    card = _fetch_agent_card(agent_address)
    endpoint = _resolve_endpoint(agent_address)
    instr = (
        f"必须调用工具完成查询，不要输出说明文字。"
        f"优先调用：get_medication_reminders 或 get_today_reminders。"
        f"请根据工具返回结果生成JSON：{{'current': [{{medication_name,dosage,frequency}}], 'inactive': [...]}。"
        f"禁止长文本生成，若工具不可用请返回 {{'error':'tool_unavailable'}}。"
    )
    try:
        data = _send_task(endpoint, instr, user_id=user_id)
        # 阶段48-27: 如果有数据，加入 page_update 让前端渲染用药列表
        page_update = None
        if isinstance(data, dict):
            meds = data.get("current", [])
            if meds:
                page_update = {
                    "component": "TodayDashboard",
                    "action": "setData",
                    "params": {"type": "medications", "medications": meds, "title": "当前用药"},
                    "summary": f"当前有 {len(meds)} 种用药",
                }
        return {"success": True, "agent": card.get("name"), "data": data, "page_update": page_update}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
def get_visit_summary_overview(agent_address: str, user_id: Optional[str] = "", days: int = 180) -> Dict[str, Any]:
    """通过A2A协议获取就诊摘要Agent的统计和最近就诊记录"""
    card = _fetch_agent_card(agent_address)
    endpoint = _resolve_endpoint(agent_address)
    instr = (
        f"必须调用工具完成查询，不要输出说明文字。"
        f"优先调用：DocumentTool_get_visit_summaries 或 MemoryIntegrationTool_get_visit_history。"
        f"请根据工具返回结果生成JSON：{{'stats': {{type: count}}, 'recent': [{{date,summary,doctor}}]}}，示例最多10条。"
        f"禁止长文本生成，若工具不可用请返回 {{'error':'tool_unavailable'}}。时间范围：最近 {days} 天。"
    )
    try:
        data = _send_task(endpoint, instr, user_id=user_id)
        # 阶段48-27: 如果有数据，加入 page_update 让前端渲染就诊摘要
        page_update = None
        if isinstance(data, dict) and data.get("recent"):
            summaries = data.get("recent", [])
            page_update = {
                "component": "TodayDashboard",
                "action": "setData",
                "params": {"type": "visit_summaries", "summaries": summaries, "title": f"最近{days}天就诊记录"},
                "summary": f"最近 {len(summaries)} 条就诊记录",
            }
        return {"success": True, "agent": card.get("name"), "data": data, "page_update": page_update}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
def aggregate_health_report(user_id: str,
                            health_records_agent: str = "health_records:10010",
                            medication_agent: str = "medication_reminder:10012",
                            visit_summary_agent: str = "visit_summary:10013",
                            days: int = 180) -> Dict[str, Any]:
    """聚合健康报告，同时查询健康记录、用药提醒、就诊摘要三个Agent并汇总"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(get_health_records_history, health_records_agent, user_id, days)
        f2 = executor.submit(get_medication_overview, medication_agent, user_id)
        f3 = executor.submit(get_visit_summary_overview, visit_summary_agent, user_id, days)

        hr = f1.result()
        med = f2.result()
        vs = f3.result()

    return {"success": True, "user_id": user_id, "days": days, "sections": {"health_records": hr, "medication": med, "visit_summaries": vs}}

@mcp.tool()
def get_health_records_history(agent_address: str, user_id: str, days: int = 180) -> Dict[str, Any]:
    """通过A2A协议获取健康记录Agent的历史健康记录，包含统计和最近记录"""
    card = _fetch_agent_card(agent_address)
    endpoint = _resolve_endpoint(agent_address)
    instr = (
        f"必须调用工具完成查询，不要输出说明文字。"
        f"优先调用：get_health_records 或 get_health_history，参数仅包含当前用户与时间范围。"
        f"请根据工具返回结果生成JSON：{{'stats': {{record_type: count}}, 'recent': [{{id,type,title,created_at,excerpt}}]}}，示例最多10条。"
        f"禁止长文本生成，若工具不可用请返回 {{'error':'tool_unavailable'}}。时间范围：最近 {days} 天。"
    )
    try:
        data = _send_task(endpoint, instr, user_id=user_id)
        # 阶段48-27: 如果有数据，加入 page_update 让前端渲染健康档案表格
        page_update = None
        if isinstance(data, dict) and data.get("recent"):
            records = data.get("recent", [])
            page_update = {
                "component": "TodayDashboard",
                "action": "setData",
                "params": {"type": "health_records", "records": records, "title": f"最近{days}天健康档案"},
                "summary": f"已加载 {len(records)} 条健康档案记录",
            }
        return {"success": True, "agent": card.get("name"), "data": data, "page_update": page_update}
    except Exception as e:
        return {"success": False, "error": str(e)}

def analyze_symptoms_via_agent(symptoms: List[str], user_id: str, days: int = 180) -> Dict[str, Any]:
    agent_address = "health_records:10010"
    endpoint = _resolve_endpoint(agent_address)
    query = " ".join(symptoms)

    try:
        # Call search_health_memories on Health Records Agent
        args = {
            "user_id": user_id,
            "query": query,
            "limit": 10,
            "time_range_days": days
        }
        # Try to use MemoryIntegrationTool_search_health_memories
        res = _send_call_tool(endpoint, "MemoryIntegrationTool_search_health_memories", args, user_id=user_id)

        # If the tool call fails or agent returns error, we might get an error dict
        if isinstance(res, dict) and res.get("error"):
             # Fallback or return empty
             return {"status": "error", "message": res.get("message", "Agent error")}

        evidence = []
        # Expected res structure from search_health_memories: {"success": True, "memories": [...]}
        # But _send_call_tool returns whatever the agent returns.
        # The agent might wrap it?
        # Based on _send_call_tool implementation:
        # instr = "...直接返回工具的原始JSON。"
        # So likely we get the tool output directly.

        if isinstance(res, dict) and res.get("success"):
            memories = res.get("memories") or []
            for m in memories:
                content = m.get("content", "")
                excerpt = ""
                if isinstance(content, dict):
                    excerpt = str(content.get("text") or content)
                else:
                    excerpt = str(content)

                evidence.append({
                    "id": str(m.get("id") or uuid.uuid4()),
                    "type": "memory",
                    "title": "相关健康记录",
                    "excerpt": excerpt[:200],
                    "created_at": m.get("created_at")
                })

        return {
            "status": "success",
            "symptoms": symptoms,
            "evidence_count": len(evidence),
            "evidence": evidence
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def generate_consultation_summary(question: str, user_id: str, days: int = 180) -> Dict[str, Any]:
    # Extract symptoms first
    q = str(question or "")
    kw = [
        "发热","高热","咳嗽","咽痛","乏力","头痛","头晕","胸闷","气短","呼吸困难",
        "心悸","恶心","呕吐","腹痛","腹泻","便秘","血压","血糖","心率","浮肿",
        "睡眠障碍","焦虑","抑郁","食欲不振"
    ]
    symptoms = [s for s in kw if s in q]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Task 1: Aggregate Report (which internally runs 3 tasks)
        f_agg = executor.submit(aggregate_health_report, user_id, "health_records:10010", "medication_reminder:10012", "visit_summary:10013", days)

        # Task 2: Analyze Symptoms (if any)
        f_sym = None
        if symptoms:
            f_sym = executor.submit(analyze_symptoms_via_agent, symptoms, user_id, days)

        # Collect results
        try:
            agg = f_agg.result()
        except Exception as e:
            agg = {"success": False, "error": str(e)}

        sym_data = {}
        if f_sym:
            try:
                res = f_sym.result()
                sym_data = {
                    "detected": symptoms,
                    "evidence_count": (res.get("evidence_count") if isinstance(res, dict) else 0) or 0,
                    "evidence": (res.get("evidence") if isinstance(res, dict) else []) or []
                }
            except Exception as e:
                sym_data = {"error": str(e)}
        else:
             sym_data = {"detected": [], "evidence_count": 0, "evidence": []}

    # Format summary
    med = None
    vis = None
    rec = None
    if isinstance(agg, dict):
        sec = agg.get("sections") or {}
        rec = sec.get("health_records")
        med = sec.get("medication")
        vis = sec.get("visit_summaries")
    tips = []
    try:
        cur = (med or {}).get("current") or []
        if cur:
            tips.append("保持用药依从性，按时服用并记录不良反应")
        st = ((rec or {}).get("stats") or {})
        if st.get("lab_result"):
            tips.append("关注检验结果变化，必要时复查关键指标")
        vst = ((vis or {}).get("stats") or {})
        if sum(int(v) for v in vst.values()) > 0:
            tips.append("结合近期就诊情况调整随访与生活方式")
        if not tips:
            tips = ["规律作息与均衡饮食","适度运动并监测关键指标","出现加重或异常及时就医"]
    except Exception:
        tips = ["规律作息与均衡饮食","适度运动并监测关键指标","出现加重或异常及时就医"]
    return {
        "success": True,
        "user_id": user_id,
        "question": question,
        "days": days,
        "summary": {
            "health_records": rec,
            "medication": med,
            "visit_summaries": vis,
            "symptoms": sym_data,
            "recommendations": tips[:5]
        }
    }

if __name__ == "__main__":
    mcp.run()
