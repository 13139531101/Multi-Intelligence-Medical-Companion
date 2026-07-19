"""Inspect medication_reminders table."""
import os
os.environ['MEMORY_DB_HOST'] = 'postgres'
os.environ['MEMORY_DB_USER'] = 'pha'
os.environ['MEMORY_DB_PASSWORD'] = 'zTlQevKV5vzq31QzRqwfcauKX3uQZ64c'
os.environ['MEMORY_DB_NAME'] = 'personal_health_assistant'

import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect(
    host='postgres', user='pha',
    password=os.environ['MEMORY_DB_PASSWORD'],
    dbname='personal_health_assistant', row_factory=dict_row
)
cur = conn.cursor()

# Users
cur.execute("SELECT id, username, created_at FROM users LIMIT 20")
print("=== USERS ===")
for r in cur.fetchall():
    print(r)

# All tables
cur.execute("""SELECT table_name FROM information_schema.tables
              WHERE table_schema='public' ORDER BY table_name""")
print("\n=== TABLES ===")
for r in cur.fetchall():
    print(r['table_name'])

# Find medication table
for tname in ['medication_reminders', 'medications', 'reminders', 'drug_schedules',
              'medication_records', 'medication_notifications']:
    try:
        cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{tname}'")
        cols = cur.fetchall()
        if cols:
            print(f"\n=== {tname} COLUMNS ===")
            for c in cols:
                print(f"  {c['column_name']}: {c['data_type']}")
    except Exception as e:
        pass

# Sample data
for tname in ['medication_reminders', 'medications', 'reminders', 'drug_schedules']:
    try:
        cur.execute(f"SELECT * FROM {tname} LIMIT 10")
        rows = cur.fetchall()
        if rows:
            print(f"\n=== {tname} sample ===")
            for r in rows:
                print(r)
    except Exception:
        pass
