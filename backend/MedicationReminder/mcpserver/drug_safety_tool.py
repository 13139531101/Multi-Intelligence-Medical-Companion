import json
import os
import uuid
from typing import Any
from urllib.parse import urlparse, urlunparse

import psycopg
import requests
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row

mcp = FastMCP("DrugSafetyTool")

PG_DSN = (
    os.environ.get("PG_DSN")
    or os.environ.get("DATABASE_URL")
    or (
        "postgresql://"
        + (os.environ.get("MEMORY_DB_USER") or os.environ.get("DB_USER") or "pha")
        + ":"
        + (os.environ.get("MEMORY_DB_PASSWORD") or os.environ.get("DB_PASSWORD") or "pha_pass")
        + "@"
        + (os.environ.get("MEMORY_DB_HOST") or os.environ.get("DB_HOST") or "postgres")
        + ":"
        + (os.environ.get("DB_PORT", "5432"))
        + "/"
        + (os.environ.get("MEMORY_DB_NAME") or os.environ.get("DB_NAME") or "personal_health_assistant")
    )
)


def _normalize_pg_dsn(dsn: str) -> str:
    dsn = (dsn or "").strip()
    if not dsn:
        return dsn
    if os.name != "nt":
        return dsn
    try:
        u = urlparse(dsn)
        host = (u.hostname or "").strip().lower()
        if host != "postgres":
            return dsn
        userinfo = ""
        if u.username:
            userinfo = u.username
            if u.password:
                userinfo = f"{userinfo}:{u.password}"
            userinfo = f"{userinfo}@"
        port = f":{u.port}" if u.port else ""
        netloc = f"{userinfo}localhost{port}"
        return urlunparse(u._replace(netloc=netloc))
    except Exception:
        return dsn


PG_DSN = _normalize_pg_dsn(PG_DSN)


def _get_pg_conn():
    return psycopg.connect(PG_DSN, row_factory=dict_row)


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
        if host in svc_map:
            return f"http://{host}:{svc_map[host]}"
        if ":" in host:
            parts = host.split(":", 1)
            return f"http://{parts[0]}:{parts[1]}"
        return f"http://{host}"
    except Exception:
        return addr


def _fetch_agent_card(base: str) -> dict[str, Any]:
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


def _send_task(
    agent_endpoint_url: str,
    tool_instruction_text: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
):
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
            "metadata": (
                {"user_id": (user_id or env_uid)} if (user_id or env_uid) else None
            ),
        },
        "id": str(uuid.uuid4()),
    }
    headers = {}
    try:
        token = os.environ.get("HOSTAPI_AUTH_TOKEN") or os.environ.get("A2A_AUTH_TOKEN")
        if isinstance(token, str) and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
    except Exception:
        pass
    r = requests.post(
        _resolve_endpoint(agent_endpoint_url),
        json=body,
        headers=headers or None,
        timeout=45,
    )
    r.raise_for_status()
    return r.json()


def _get_active_medication_names(user_id: str) -> list[str]:
    user_id = (user_id or "").strip()
    if not user_id:
        return []
    try:
        with _get_pg_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT drug_name
                        FROM user_medications
                        WHERE user_id = %s
                          AND is_active = TRUE
                          AND (is_deleted IS NULL OR is_deleted = FALSE)
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC
                        """,
                        (user_id,),
                    )
                except Exception:
                    cur.execute(
                        """
                        SELECT drug_name
                        FROM user_medications
                        WHERE user_id = %s
                          AND is_active = TRUE
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC
                        """,
                        (user_id,),
                    )
                rows = cur.fetchall() or []
        names: list[str] = []
        for r in rows:
            try:
                v = r["drug_name"] if isinstance(r, dict) else r[0]
                if v:
                    names.append(str(v).strip())
            except Exception:
                continue
        return [x for x in names if x]
    except Exception:
        return []


@mcp.tool()
def check_drug_interaction(
    new_drug: str,
    user_id: str | None = None,
    current_drugs: list[str] | None = None,
) -> dict[str, Any]:
    """检查新药物与当前用药之间是否存在相互作用或禁忌"""
    new_drug = (new_drug or "").strip()
    uid = (user_id or "").strip()
    if not new_drug:
        return {"status": "error", "message": "new_drug 不能为空"}

    if current_drugs is None:
        current_drugs = _get_active_medication_names(uid)
    current_drugs = [str(x).strip() for x in (current_drugs or []) if str(x).strip()]

    advisor = os.environ.get("HEALTH_ADVISOR_URL") or "http://health_advisor:10011"
    instr = (
        "你是用药安全核查助手。"
        "请评估新药与当前用药列表的相互作用、重复用药风险与常见禁忌。"
        "只输出JSON，不要解释，不要markdown。"
        f"新药: {json.dumps(new_drug, ensure_ascii=False)}。"
        f"当前用药列表: {json.dumps(current_drugs, ensure_ascii=False)}。"
        "返回格式: {"
        "'risk_level':'low|medium|high|unknown',"
        "'interactions':[{'with':str,'type':str,'severity':str,'note':str}],"
        "'warnings':[str],"
        "'recommendation':str"
        "}。"
        "若信息不足请 risk_level=unknown，并给出保守建议(咨询医生/药师)。"
    )
    try:
        res = _send_task(advisor, instr, user_id=uid or None)
        return {
            "status": "success",
            "new_drug": new_drug,
            "current_drugs": current_drugs,
            "advisor_response": res,
        }
    except Exception as e:
        return {
            "status": "error",
            "new_drug": new_drug,
            "current_drugs": current_drugs,
            "risk_level": "unknown",
            "message": str(e),
        }


if __name__ == "__main__":
    mcp.run()
