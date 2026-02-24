import os
import sys
import uuid
import json
from datetime import datetime

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


def main():
    from AgentMemorySystem.database_config import MemoryDatabaseConfig

    db = MemoryDatabaseConfig()
    assert db.enabled and db.check_connection(), "DB not connected"
    mem_id = str(uuid.uuid4())
    conn = db.get_connection()
    cur = conn.cursor()
    # insert a simple working memory for user 111, agent medication_reminder
    cur.execute(
        """
        INSERT INTO memories (memory_id, agent_id, user_id, memory_type,
                               content_text, metadata, importance_score, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            mem_id,
            'medication_reminder',
            '111',
            'working',
            'diagnostics: test write for user 111',
            json.dumps({"source": "diagnostics", "note": "add_test_memory_111"}, ensure_ascii=False),
            0.1,
            datetime.utcnow()
        )
    )
    conn.commit()
    cur.close()
    conn.close()
    print(mem_id)


if __name__ == '__main__':
    main()
