import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'pha'),
    'password': os.getenv('DB_PASSWORD', 'pha_pass'),
    'dbname': os.getenv('DB_NAME', 'personal_health_assistant')
}

def add_openid_column():
    try:
        conn = psycopg.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Check if column exists
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='openid'")
            if not cur.fetchone():
                print("Adding openid column to users table...")
                cur.execute("ALTER TABLE users ADD COLUMN openid VARCHAR(64) UNIQUE")
                conn.commit()
                print("Column added.")
            else:
                print("Column openid already exists.")

            # Check if column exists in user_sessions (optional, but good for tracking)
            # Actually users table is enough.

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    add_openid_column()
