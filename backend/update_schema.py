import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'pha'),
    'password': os.getenv('DB_PASSWORD', 'pha_pass'),
    'dbname': os.getenv('DB_NAME', 'personal_health_assistant')
}

_db_pool: ConnectionPool | None = None


def _build_db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = DB_CONFIG["user"]
    password = DB_CONFIG.get("password") or ""
    host = DB_CONFIG["host"]
    port = DB_CONFIG["port"]
    dbname = DB_CONFIG["dbname"]
    auth = f"{user}:{password}" if password else f"{user}"
    return f"postgresql://{auth}@{host}:{port}/{dbname}"


def _get_pool() -> ConnectionPool:
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    max_size = int(os.getenv("DB_POOL_MAX_SIZE", "5"))
    timeout = float(os.getenv("DB_POOL_TIMEOUT", "5"))
    _db_pool = ConnectionPool(_build_db_dsn(), max_size=max(max_size, 1), timeout=timeout)
    return _db_pool


def add_openid_column():
    try:
        pool = _get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='openid'"
                )
                if not cur.fetchone():
                    print("Adding openid column to users table...")
                    cur.execute("ALTER TABLE users ADD COLUMN openid VARCHAR(64) UNIQUE")
                    conn.commit()
                    print("Column added.")
                else:
                    print("Column openid already exists.")

            # Check if column exists in user_sessions (optional, but good for tracking)
            # Actually users table is enough.
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    add_openid_column()
