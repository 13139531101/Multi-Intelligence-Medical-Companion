from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


async def get_api_status(api: Any) -> dict[str, Any]:
    return {"status": "healthy", "timestamp": datetime.now()}


async def get_dashboard_recent_activities(
    api: Any,
    *,
    limit: int,
    user_id: Any,
    request: Any,
) -> list[dict[str, Any]]:
    def _format_time(dt: Any) -> str:
        if not dt:
            return ""
        if isinstance(dt, str):
            return dt[:16].replace("T", " ")
        try:
            if hasattr(dt, "astimezone"):
                dt_local = dt.astimezone()
            else:
                dt_local = dt
            now_local = (
                datetime.now(dt_local.tzinfo)
                if getattr(dt_local, "tzinfo", None)
                else datetime.now()
            )
            if dt_local.date() == now_local.date():
                return f"今天 {dt_local.strftime('%H:%M')}"
            if dt_local.date() == (now_local.date() - timedelta(days=1)):
                return f"昨天 {dt_local.strftime('%H:%M')}"
            return dt_local.strftime("%m-%d %H:%M")
        except Exception:
            try:
                return str(dt)
            except Exception:
                return ""

    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            return []

        activities: list[dict[str, Any]] = []

        def _to_sort_ts(v: Any) -> float:
            if not v:
                return 0.0
            if isinstance(v, datetime):
                try:
                    return float(v.timestamp())
                except Exception:
                    return 0.0
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return 0.0
                try:
                    return float(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
                except Exception:
                    try:
                        return float(
                            datetime.fromisoformat(
                                s.replace("T", " ").replace("Z", "+00:00")
                            ).timestamp()
                        )
                    except Exception:
                        return 0.0
            try:
                return float(v)
            except Exception:
                return 0.0

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                try:
                    cursor.execute(
                        """
                        SELECT id, record_type, title, created_at
                        FROM health_records
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        activities.append(
                            {
                                "id": f"health_record:{r.get('id')}",
                                "title": "新增健康档案",
                                "time": _format_time(r.get("created_at")),
                                "icon": "📋",
                                "_ts": r.get("created_at"),
                            }
                        )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        """
                        SELECT id, created_at
                        FROM visit_summaries
                        WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        activities.append(
                            {
                                "id": f"visit_summary:{r.get('id')}",
                                "title": "生成就诊摘要",
                                "time": _format_time(r.get("created_at")),
                                "icon": "📝",
                                "_ts": r.get("created_at"),
                            }
                        )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        """
                        SELECT id, created_at
                        FROM user_medications
                        WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        activities.append(
                            {
                                "id": f"medication:{r.get('id')}",
                                "title": "新增用药记录",
                                "time": _format_time(r.get("created_at")),
                                "icon": "💊",
                                "_ts": r.get("created_at"),
                            }
                        )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        """
                        SELECT reminder_id, scheduled_time, completion_time, status
                        FROM reminder_logs
                        WHERE user_id = %s
                        ORDER BY COALESCE(completion_time, created_at, scheduled_time) DESC NULLS LAST
                        LIMIT %s
                        """,
                        (uid, limit),
                    )
                    for r in cursor.fetchall() or []:
                        status = str(r.get("status") or "").lower()
                        if status in ("completed", "taken"):
                            title = "完成服药"
                            icon = "✅"
                        elif status in ("missed", "skipped"):
                            title = "标记跳过用药"
                            icon = "⏭️"
                        else:
                            title = "用药记录"
                            icon = "💊"

                        ts = r.get("completion_time") or r.get("scheduled_time")
                        activities.append(
                            {
                                "id": f"reminder_log:{r.get('reminder_id')}:{r.get('scheduled_time')}",
                                "title": title,
                                "time": _format_time(ts),
                                "icon": icon,
                                "_ts": ts,
                            }
                        )
                except Exception:
                    pass

        uniq: dict[str, dict[str, Any]] = {}
        for a in activities:
            aid = str(a.get("id") or "")
            if not aid:
                continue
            uniq[aid] = a

        merged = list(uniq.values())
        merged.sort(key=lambda x: _to_sort_ts(x.get("_ts")), reverse=True)
        for a in merged:
            a.pop("_ts", None)
        return merged[: int(limit)]
    except Exception as e:
        api.logger.error(f"获取最近活动失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def get_dashboard_stats(
    api: Any,
    *,
    user_id: Any,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            return api.DashboardStats()

        health_records_count = 0
        medication_count = 0
        summary_count = 0

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(
                        "SELECT COUNT(1) FROM health_records WHERE user_id = %s",
                        (uid,),
                    )
                    row = cursor.fetchone()
                    health_records_count = int(row[0] or 0) if row else 0
                except Exception:
                    health_records_count = 0

                try:
                    cursor.execute(
                        "SELECT COUNT(1) FROM visit_summaries WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0",
                        (uid,),
                    )
                    row = cursor.fetchone()
                    summary_count = int(row[0] or 0) if row else 0
                except Exception:
                    summary_count = 0

                try:
                    cursor.execute(
                        "SELECT COUNT(1) FROM user_medications WHERE user_id = %s AND COALESCE(is_deleted, 0) = 0",
                        (uid,),
                    )
                    row = cursor.fetchone()
                    medication_count = int(row[0] or 0) if row else 0
                except Exception:
                    medication_count = 0

        recent_raw = await get_dashboard_recent_activities(
            api,
            limit=10,
            user_id=uid,
            request=request,
        )
        activities: list[Any] = []
        try:
            for item in recent_raw or []:
                activities.append(
                    api.DashboardActivity(
                        id=str(item.get("id") or ""),
                        title=str(item.get("title") or ""),
                        time=str(item.get("time") or ""),
                        icon=str(item.get("icon") or ""),
                    )
                )
        except Exception:
            activities = []

        return api.DashboardStats(
            health_records_count=health_records_count,
            medication_count=medication_count,
            summary_count=summary_count,
            recent_activities=activities,
        )
    except Exception as e:
        api.logger.error(f"获取仪表板统计失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))
