import os
import sys
import json
import traceback

# Ensure backend path is importable
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

result = {
    "current_user_id_env": os.environ.get("A2A_CURRENT_USER_ID"),
    "db_enabled": None,
    "db_connection_ok": None,
    "tables": {},
    "agents_summary": [],
    "by_user_agent_type": [],
    "recent_memories": [],
    "errors": []
}

try:
    from AgentMemorySystem.database_config import MemoryDatabaseConfig
except Exception as e:
    result["errors"].append(f"Import MemoryDatabaseConfig failed: {e}")
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)

try:
    db = MemoryDatabaseConfig()
    result["db_enabled"] = db.enabled
    if db.enabled:
        result["db_connection_ok"] = db.check_connection()
        try:
            result["tables"] = db.get_table_info()
        except Exception as e:
            result["errors"].append(f"get_table_info error: {e}")
        # Query summaries
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            # Agents total counts
            cur.execute("""
                SELECT agent_id, COUNT(*) as cnt
                FROM memories
                GROUP BY agent_id
                ORDER BY cnt DESC
            """)
            result["agents_summary"] = [(row[0], int(row[1])) for row in cur.fetchall()]

            # By user, agent, type
            cur.execute("""
                SELECT user_id, agent_id, memory_type, COUNT(*) as cnt
                FROM memories
                GROUP BY user_id, agent_id, memory_type
                ORDER BY cnt DESC
                LIMIT 100
            """)
            result["by_user_agent_type"] = [
                {
                    "user_id": row[0],
                    "agent_id": row[1],
                    "memory_type": row[2],
                    "count": int(row[3])
                } for row in cur.fetchall()
            ]

            # Recent 10 memories
            cur.execute("""
                SELECT memory_id, agent_id, user_id, memory_type, created_at
                FROM memories
                ORDER BY created_at DESC
                LIMIT 10
            """)
            result["recent_memories"] = [
                {
                    "memory_id": row[0],
                    "agent_id": row[1],
                    "user_id": row[2],
                    "memory_type": row[3],
                    "created_at": row[4].isoformat() if hasattr(row[4], 'isoformat') else str(row[4])
                } for row in cur.fetchall()
            ]
            cur.close()
            conn.close()
        except Exception as e:
            result["errors"].append(f"DB query failed: {e}\n{traceback.format_exc()}")
    else:
        result["db_connection_ok"] = False
except Exception as e:
    result["errors"].append(f"Init MemoryDatabaseConfig failed: {e}\n{traceback.format_exc()}")

print(json.dumps(result, ensure_ascii=False))
