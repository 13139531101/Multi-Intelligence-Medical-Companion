import os
import sys
import sqlite3

# Ensure backend path is in sys.path to reuse DB config
MODULE_DIR = os.path.dirname(__file__)
sys.path.insert(0, MODULE_DIR)

try:
    import health_records_api as h
except Exception as e:
    print("Failed to import health_records_api:", e)
    # Fallback DB path
    DB_PATH = os.path.join(MODULE_DIR, "health_records.db")
else:
    DB_PATH = getattr(h, "DB_PATH", os.path.join(MODULE_DIR, "health_records.db"))

print("DB_PATH:", DB_PATH)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

cols = [r[1] for r in c.execute('PRAGMA table_info(health_records)').fetchall()]
print("before:", cols)

# Add user_id column if missing
if "user_id" not in cols:
    c.execute("ALTER TABLE health_records ADD COLUMN user_id TEXT")
    print("added user_id column")

# Backfill legacy rows with current/default user
default_user = (
    os.environ.get("A2A_CURRENT_USER_ID")
    or os.environ.get("DEFAULT_USER_ID")
    or "user_111"
)

c.execute(
    "UPDATE health_records SET user_id = ? WHERE user_id IS NULL OR user_id = ''",
    (default_user,),
)
conn.commit()
print("backfilled user_id to:", default_user)

cols_after = [r[1] for r in c.execute('PRAGMA table_info(health_records)').fetchall()]
print("after:", cols_after)

conn.close()
print("migration done")