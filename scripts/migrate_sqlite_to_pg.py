import os
import sqlite3
import json
from datetime import datetime, date, time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json


BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"

SQLITE_MED_REM_PATH = str(BACKEND_DIR / "medication_reminders.db")
SQLITE_HEALTH_REC_PATH = str(BACKEND_DIR / "health_records.db")

PG_DSN = (
    os.environ.get("PG_DSN")
    or os.environ.get("DATABASE_URL")
    or "postgresql://postgres:postgres@localhost:5432/postgres"
)


def ensure_tables(conn: psycopg.Connection) -> None:
    """Create target tables in PostgreSQL if they do not exist."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS medication_reminders (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                medication_name TEXT NOT NULL,
                dosage TEXT NOT NULL,
                frequency TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE,
                reminder_times JSONB NOT NULL,
                notes TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS appointment_reminders (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                doctor_name TEXT NOT NULL,
                department TEXT NOT NULL,
                appointment_date DATE NOT NULL,
                appointment_time TIME NOT NULL,
                hospital TEXT NOT NULL,
                notes TEXT,
                reminder_advance_days INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_logs (
                id SERIAL PRIMARY KEY,
                reminder_id INTEGER NOT NULL REFERENCES medication_reminders(id) ON DELETE CASCADE,
                scheduled_time TIMESTAMPTZ NOT NULL,
                actual_time TIMESTAMPTZ,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS health_records (
                id UUID PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                record_type TEXT NOT NULL,
                summary TEXT,
                content TEXT,
                importance TEXT NOT NULL DEFAULT 'medium',
                tags JSONB,
                metadata JSONB,
                record_date DATE,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS file_attachments (
                id UUID PRIMARY KEY,
                record_id UUID REFERENCES health_records(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                mime_type TEXT,
                upload_time TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        conn.commit()


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Accept both ISO format and sqlite CURRENT_TIMESTAMP strings
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def migrate_medication_reminders(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()
    cur.execute("SELECT * FROM medication_reminders")
    rows = cur.fetchall()

    inserted = 0
    with pg_conn.cursor() as pg:
        for r in rows:
            start_date = parse_date(r["start_date"]) or date.today()
            end_date = parse_date(r["end_date"]) if r["end_date"] else None
            reminder_times = json.loads(r["reminder_times"]) if r["reminder_times"] else []
            created_at = parse_ts(r["created_at"]) or datetime.utcnow()
            updated_at = parse_ts(r["updated_at"]) or created_at

            pg.execute(
                """
                INSERT INTO medication_reminders
                (user_id, medication_name, dosage, frequency, start_date, end_date,
                 reminder_times, notes, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    r["user_id"],
                    r["medication_name"],
                    r["dosage"],
                    r["frequency"],
                    start_date,
                    end_date,
                    Json(reminder_times),
                    r["notes"],
                    bool(r["is_active"]),
                    created_at,
                    updated_at,
                ),
            )
            inserted += 1
        pg_conn.commit()
    return inserted


def migrate_appointment_reminders(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()
    cur.execute("SELECT * FROM appointment_reminders")
    rows = cur.fetchall()

    inserted = 0
    with pg_conn.cursor() as pg:
        for r in rows:
            appt_date = parse_date(r["appointment_date"]) or date.today()
            # appointment_time stored as HH:MM in sqlite
            appt_time = None
            try:
                appt_time = datetime.strptime(r["appointment_time"], "%H:%M").time() if r["appointment_time"] else time(9, 0)
            except Exception:
                appt_time = time(9, 0)
            created_at = parse_ts(r["created_at"]) or datetime.utcnow()
            updated_at = parse_ts(r["updated_at"]) or created_at

            pg.execute(
                """
                INSERT INTO appointment_reminders
                (user_id, doctor_name, department, appointment_date, appointment_time,
                 hospital, notes, reminder_advance_days, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    r["user_id"],
                    r["doctor_name"],
                    r["department"],
                    appt_date,
                    appt_time,
                    r["hospital"],
                    r["notes"],
                    int(r["reminder_advance_days"]) if r["reminder_advance_days"] is not None else 1,
                    bool(r["is_active"]),
                    created_at,
                    updated_at,
                ),
            )
            inserted += 1
        pg_conn.commit()
    return inserted


def migrate_reminder_logs(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()
    cur.execute("SELECT * FROM reminder_logs")
    rows = cur.fetchall()

    inserted = 0
    with pg_conn.cursor() as pg:
        for r in rows:
            created_at = parse_ts(r["created_at"]) or datetime.utcnow()
            # scheduled_time is HH:MM; combine with created_at date for TIMESTAMPTZ
            scheduled_ts = None
            try:
                date_part = created_at.date()
                hh, mm = (r["scheduled_time"] or "00:00").split(":")
                scheduled_ts = datetime.combine(date_part, time(int(hh), int(mm)))
            except Exception:
                scheduled_ts = created_at

            actual_ts = None
            if r["actual_time"]:
                try:
                    hh, mm = r["actual_time"].split(":")
                    actual_ts = datetime.combine(created_at.date(), time(int(hh), int(mm)))
                except Exception:
                    actual_ts = None

            pg.execute(
                """
                INSERT INTO reminder_logs
                (reminder_id, scheduled_time, actual_time, status, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    r["reminder_id"],
                    scheduled_ts,
                    actual_ts,
                    r["status"],
                    r["notes"],
                    created_at,
                ),
            )
            inserted += 1
        pg_conn.commit()
    return inserted


def migrate_health_records(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()
    cur.execute("SELECT * FROM health_records")
    rows = cur.fetchall()

    inserted = 0
    with pg_conn.cursor() as pg:
        for r in rows:
            record_date = None
            if r["record_date"]:
                try:
                    record_date = datetime.strptime(r["record_date"], "%Y-%m-%d").date()
                except Exception:
                    record_date = None

            created_at = parse_ts(r["created_at"]) or datetime.utcnow()
            updated_at = parse_ts(r["updated_at"]) or created_at

            tags = []
            metadata = {}
            try:
                tags = json.loads(r["tags"]) if r["tags"] else []
            except Exception:
                tags = []
            try:
                metadata = json.loads(r["metadata"]) if r["metadata"] else {}
            except Exception:
                metadata = {}

            pg.execute(
                """
                INSERT INTO health_records
                (id, user_id, title, record_type, summary, content, importance, tags, metadata,
                 record_date, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    r["id"],
                    r.get("user_id"),
                    r["title"],
                    r["record_type"],
                    r["summary"],
                    r["content"],
                    r["importance"],
                    Json(tags),
                    Json(metadata),
                    record_date,
                    created_at,
                    updated_at,
                ),
            )
            inserted += 1
        pg_conn.commit()
    return inserted


def migrate_file_attachments(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()
    cur.execute("SELECT * FROM file_attachments")
    rows = cur.fetchall()

    inserted = 0
    with pg_conn.cursor() as pg:
        for r in rows:
            upload_time = parse_ts(r["upload_time"]) or datetime.utcnow()
            pg.execute(
                """
                INSERT INTO file_attachments
                (id, record_id, filename, original_filename, file_path, file_size, mime_type, upload_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    r["id"],
                    r["record_id"],
                    r["filename"],
                    r["original_filename"],
                    r["file_path"],
                    r["file_size"],
                    r["mime_type"],
                    upload_time,
                ),
            )
            inserted += 1
        pg_conn.commit()
    return inserted


def main() -> None:
    print("Connecting to PostgreSQL:", PG_DSN)
    with psycopg.connect(PG_DSN, row_factory=dict_row) as pg_conn:
        ensure_tables(pg_conn)

        # Migrate medication reminders domain
        if os.path.exists(SQLITE_MED_REM_PATH):
            with sqlite3.connect(SQLITE_MED_REM_PATH) as sqlite_conn:
                n1 = migrate_medication_reminders(sqlite_conn, pg_conn)
                n2 = migrate_appointment_reminders(sqlite_conn, pg_conn)
                n3 = migrate_reminder_logs(sqlite_conn, pg_conn)
                print(f"Medication: reminders={n1}, appointments={n2}, logs={n3}")
        else:
            print(f"SQLite medication_reminders.db not found at {SQLITE_MED_REC_PATH}")

        # Migrate health records domain
        if os.path.exists(SQLITE_HEALTH_REC_PATH):
            with sqlite3.connect(SQLITE_HEALTH_REC_PATH) as sqlite_conn:
                n4 = migrate_health_records(sqlite_conn, pg_conn)
                n5 = migrate_file_attachments(sqlite_conn, pg_conn)
                print(f"Health records: records={n4}, attachments={n5}")
        else:
            print(f"SQLite health_records.db not found at {SQLITE_HEALTH_REC_PATH}")


if __name__ == "__main__":
    main()