
import asyncio
import os
import sys
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

# Add current directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Mock the model
class Consultation(BaseModel):
    id: Optional[int] = None
    user_id: str
    consultation_id: Optional[str]
    session_id: Optional[str]
    question: Optional[str]
    answer: Optional[str]
    tags: Optional[List[str]]
    created_at: datetime

# DB Config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "pha"),
    "password": os.getenv("DB_PASSWORD", "pha_pass"),
    "dbname": os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "personal_health_assistant")),
}

async def test_fetch():
    print("Connecting to DB...")
    try:
        conn = psycopg.connect(**DB_CONFIG)
        with conn.cursor(row_factory=dict_row) as cursor:
            print("Executing query...")
            cursor.execute("SELECT * FROM consultations ORDER BY created_at DESC LIMIT 10")
            rows = cursor.fetchall()
            print(f"Fetched {len(rows)} rows.")

            for i, row in enumerate(rows):
                print(f"Row {i}: {row}")
                # Simulate the logic in the API
                if isinstance(row.get('tags'), str):
                    try:
                        import json
                        row['tags'] = json.loads(row['tags'])
                    except:
                        row['tags'] = []
                elif row.get('tags') is None:
                        row['tags'] = []

                try:
                    c = Consultation(**row)
                    print(f"Row {i} valid.")
                except Exception as e:
                    print(f"Row {i} INVALID: {e}")

        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
