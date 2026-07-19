"""Find user_id for username=1111."""
import os
os.environ['MEMORY_DB_PASSWORD'] = 'zTlQevKV5vzq31QzRqwfcauKX3uQZ64c'

import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect(
    host='postgres', user='pha',
    password=os.environ['MEMORY_DB_PASSWORD'],
    dbname='personal_health_assistant', row_factory=dict_row
)
cur = conn.cursor()

# 用 username=1111 直接查
cur.execute("SELECT * FROM users WHERE username='1111'")
u = cur.fetchone()
print("user '1111':", u)

# 看 chat_messages 看 user_id 格式
cur.execute("SELECT DISTINCT user_id FROM chat_messages LIMIT 20")
print("\nchat_messages user_ids:")
for r in cur.fetchall():
    print(' ', r['user_id'])

# 看 reminder_logs / consultations 看 user_id
for t in ['reminder_logs', 'consultations', 'user_sessions']:
    try:
        cur.execute(f"SELECT DISTINCT user_id FROM {t} LIMIT 10")
        rows = cur.fetchall()
        if rows:
            print(f"\n{t} user_ids:")
            for r in rows:
                print(' ', r['user_id'])
    except Exception as e:
        print(f"{t}: {e}")

# 用 1111 直接查 medication_reminders
if u:
    uid = u['id']
    print(f"\n--- medication for user.id={uid} ---")
    cur.execute("SELECT * FROM medication_reminders WHERE user_id = %s", (str(uid),))
    for r in cur.fetchall():
        print(r)
    print(f"\n--- medication for user.username={u['username']} ---")
    cur.execute("SELECT * FROM medication_reminders WHERE user_id = %s", (u['username'],))
    for r in cur.fetchall():
        print(r)
