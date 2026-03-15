from __future__ import annotations

import json
from datetime import datetime
from typing import Any


async def get_consultation_history(
    api: Any,
    *,
    skip: int,
    limit: int,
    user_id: Any,
    include_summary: bool,
    include_health_records: bool,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            return []

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                where_clauses = ["user_id = %s"]
                if not include_summary:
                    where_clauses.append("(tags IS NULL OR NOT (tags ? 'summary'))")
                if not include_health_records:
                    where_clauses.append(
                        "(tags IS NULL OR NOT (tags ? 'health_records'))"
                    )
                where_sql = " AND ".join(where_clauses)
                sql = f"""
                    SELECT * FROM consultations
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (uid, limit, skip))
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    if isinstance(row.get("tags"), str):
                        try:
                            row["tags"] = json.loads(row["tags"])
                        except Exception:
                            row["tags"] = []
                    elif row.get("tags") is None:
                        row["tags"] = []
                    results.append(api.Consultation(**row))
                return results
    except Exception as e:
        api.logger.error(f"获取咨询历史失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def create_consultation(
    api: Any,
    *,
    consultation: Any,
    user_id: Any,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                new_consultation_id = consultation.consultation_id or api.generate_id()
                now = datetime.now()

                cursor.execute(
                    """
                    INSERT INTO consultations (
                        user_id, consultation_id, session_id, question, answer, tags, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (consultation_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        uid,
                        new_consultation_id,
                        consultation.session_id,
                        consultation.question,
                        consultation.answer,
                        api.Json(consultation.tags or []),
                        now,
                    ),
                )
                inserted = cursor.fetchone()
                if inserted:
                    new_id = inserted["id"]
                    conn.commit()
                    cursor.execute("SELECT * FROM consultations WHERE id = %s", (new_id,))
                    row = cursor.fetchone()
                else:
                    conn.rollback()
                    cursor.execute(
                        "SELECT * FROM consultations WHERE consultation_id = %s",
                        (new_consultation_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        raise api.HTTPException(status_code=409, detail="咨询ID冲突，请重试")
                    if str(row.get("user_id")) != str(uid):
                        raise api.HTTPException(status_code=409, detail="咨询ID已被其他用户占用")

                if isinstance(row.get("tags"), str):
                    try:
                        row["tags"] = json.loads(row["tags"])
                    except Exception:
                        row["tags"] = []
                elif row.get("tags") is None:
                    row["tags"] = []

                return api.Consultation(**row)

    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"创建咨询记录失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def delete_consultation(
    api: Any,
    *,
    consultation_id: int,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM consultations WHERE id = %s AND user_id = %s RETURNING id",
                    (consultation_id, uid),
                )
                deleted = cursor.fetchone()
                if not deleted:
                    raise api.HTTPException(
                        status_code=404, detail="咨询记录不存在或无权删除"
                    )
                conn.commit()
                return {"message": "删除成功", "id": consultation_id}

    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"删除咨询记录失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def save_consultation_message(
    api: Any,
    *,
    message: Any,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    try:
        api._resolve_user_id(request, user_id)

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                msg_id = api.generate_id()
                cursor.execute(
                    """
                    INSERT INTO chat_messages (id, consultation_id, role, content, files, created_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING id
                    """,
                    (
                        msg_id,
                        message.consultation_id,
                        message.role,
                        message.content,
                        json.dumps(getattr(message, "files", None) or []),
                        datetime.now(),
                    ),
                )
                conn.commit()
                return {"success": True, "id": msg_id}
    except Exception as e:
        api.logger.error(f"保存消息失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def get_consultation_messages(
    api: Any,
    *,
    consultation_id: str,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    try:
        api._resolve_user_id(request, user_id)

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM chat_messages
                    WHERE consultation_id = %s
                    ORDER BY created_at ASC
                    """,
                    (consultation_id,),
                )
                rows = cursor.fetchall()
                return {"success": True, "messages": rows}
    except Exception as e:
        api.logger.error(f"获取消息历史失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))
