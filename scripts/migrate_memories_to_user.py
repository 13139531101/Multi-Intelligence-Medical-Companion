import os
import sys
import json
import argparse
from datetime import datetime

# Ensure we can import AgentMemorySystem config
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
AGENT_MEMORY_PATH = os.path.join(PROJECT_ROOT, 'backend', 'AgentMemorySystem')
if AGENT_MEMORY_PATH not in sys.path:
    sys.path.append(AGENT_MEMORY_PATH)

from database_config import MemoryDatabaseConfig  # type: ignore

BAD_USER_PATTERNS = [
    ("IS_NULL", "user_id IS NULL"),
    ("EMPTY", "user_id = ''"),
    ("DEFAULT", "user_id LIKE 'default%'"),
    ("ANNOTATION", "user_id LIKE 'annotation%'"),
    ("REQUIRED", "user_id LIKE '%required%'"),
    ("FORM", "user_id LIKE '%Form%'"),
    ("OBJECT", "user_id LIKE '%object%'"),
    ("NON_ALNUM", "user_id REGEXP '[^A-Za-z0-9_-]'"),
]

DEF_SAMPLE_LIMIT = 20

def summarize_bad_users(cursor):
    summary = {}
    for key, condition in BAD_USER_PATTERNS:
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM memories WHERE {condition}")
        row = cursor.fetchone()
        summary[key] = row[0] if row else 0
    # also list distinct suspicious user_ids (top 20)
    cursor.execute(
        """
        SELECT user_id, COUNT(*) AS cnt
        FROM memories
        WHERE user_id IS NULL OR user_id = ''
           OR user_id LIKE 'default%'
           OR user_id LIKE 'annotation%'
           OR user_id LIKE '%required%'
           OR user_id LIKE '%Form%'
           OR user_id LIKE '%object%'
           OR user_id REGEXP '[^A-Za-z0-9_-]'
        GROUP BY user_id
        ORDER BY cnt DESC
        LIMIT 20
        """
    )
    suspicious = []
    for row in cursor.fetchall():
        suspicious.append({
            'user_id': row[0],
            'count': row[1]
        })
    return summary, suspicious


def sample_bad_records(cursor, limit=DEF_SAMPLE_LIMIT):
    cursor.execute(
        """
        SELECT memory_id, agent_id, user_id, memory_type, created_at
        FROM memories
        WHERE user_id IS NULL OR user_id = ''
           OR user_id LIKE 'default%'
           OR user_id LIKE 'annotation%'
           OR user_id LIKE '%required%'
           OR user_id LIKE '%Form%'
           OR user_id LIKE '%object%'
           OR user_id REGEXP '[^A-Za-z0-9_-]'
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,)
    )
    rows = cursor.fetchall()
    results = []
    for r in rows:
        # Depending on cursor config, fetch as tuple or dict
        if isinstance(r, dict):
            results.append(r)
        else:
            results.append({
                'memory_id': r[0],
                'agent_id': r[1],
                'user_id': r[2],
                'memory_type': r[3],
                'created_at': r[4].isoformat() if hasattr(r[4], 'isoformat') else str(r[4])
            })
    return results


def migrate_user_id(connection, target_user_id: str):
    cursor = connection.cursor()
    update_sql = (
        "UPDATE memories SET user_id = %s WHERE "
        "user_id IS NULL OR user_id = '' "
        "OR user_id LIKE 'default%' "
        "OR user_id LIKE 'annotation%' "
        "OR user_id LIKE '%required%' "
        "OR user_id LIKE '%Form%' "
        "OR user_id LIKE '%object%' "
        "OR user_id REGEXP '[^A-Za-z0-9_-]'"
    )
    cursor.execute(update_sql, (target_user_id,))
    affected = cursor.rowcount
    connection.commit()
    return affected


def main():
    parser = argparse.ArgumentParser(description='Migrate malformed user_id in memories to target user.')
    parser.add_argument('--target-user-id', default=os.environ.get('A2A_CURRENT_USER_ID', '111'), help='Target user_id to assign (default from A2A_CURRENT_USER_ID or 111)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying updates')
    parser.add_argument('--commit', action='store_true', help='Apply updates')
    parser.add_argument('--sample-limit', type=int, default=DEF_SAMPLE_LIMIT, help='Preview sample size')
    args = parser.parse_args()

    cfg = MemoryDatabaseConfig()
    if not cfg._enabled:
        print(json.dumps({'ok': False, 'error': 'DB not enabled'}))
        return
    try:
        conn = cfg.get_connection()
        cur = conn.cursor()
        summary, suspicious = summarize_bad_users(cur)
        samples = sample_bad_records(cur, limit=args.sample_limit)
        result = {
            'ok': True,
            'time': datetime.now().isoformat(),
            'db_enabled': True,
            'target_user_id': args.target_user_id,
            'summary': summary,
            'suspicious_user_ids': suspicious,
            'sample_records': samples,
        }
        if args.commit and not args.dry_run:
            affected = migrate_user_id(conn, args.target_user_id)
            result['migrated_rows'] = affected
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({'ok': False, 'error': str(e)}))
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()