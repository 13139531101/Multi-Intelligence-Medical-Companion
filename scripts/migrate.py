#!/usr/bin/env python3
"""
PHA Database Migration Runner
用法:
  python scripts/migrate.py pending    # 查看待运行的迁移
  python scripts/migrate.py run        # 运行所有待运行的迁移
  python scripts/migrate.py status     # 查看迁移状态表
  python scripts/migrate.py create <name>  # 创建新迁移脚本
"""

import os
import sys
import re
import importlib.util
from pathlib import Path
from datetime import datetime

# 加载 database_config
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

try:
    from HealthRecordsManager.database_config import get_db_config
    config = get_db_config()
    DATABASE_URL = config["url"]
except Exception:
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://pha:pha_pass@localhost:5432/personal_health_assistant"
    )

MIGRATIONS_DIR = Path(__file__).parent.parent / "database" / "migrations"
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
MIGRATIONS_TABLE = "schema_migrations"


def get_connection():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def ensure_migrations_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            id          SERIAL PRIMARY KEY,
            version     VARCHAR(64) UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            checksum    VARCHAR(64) NOT NULL,
            rollback_sql TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def get_applied_migrations():
    ensure_migrations_table()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT version FROM {MIGRATIONS_TABLE} ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r[0] for r in rows}


def get_pending_migrations():
    applied = get_applied_migrations()
    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = f.stem
        if version not in applied:
            migrations.append((version, f))
    return migrations


def compute_checksum(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_migration(version: str, path: Path):
    """执行单个迁移"""
    conn = get_connection()
    cur = conn.cursor()
    sql = path.read_text(encoding="utf-8")

    # 提取 rollback SQL（-- rollback: ... 块）
    rollback_sql = ""
    rb_match = re.search(r"--\s*rollback:\s*\n(.*)", sql, re.DOTALL)
    if rb_match:
        rollback_sql = rb_match.group(1).strip()

    checksum = compute_checksum(path)

    print(f"  ▶ Applying {version} ...")
    try:
        cur.execute(sql)
        cur.execute(
            f"INSERT INTO {MIGRATIONS_TABLE} (version, name, checksum, rollback_sql) VALUES (%s,%s,%s,%s)",
            (version, path.stem, checksum, rollback_sql)
        )
        conn.commit()
        print(f"  ✓ {version} applied")
    except Exception as ex:
        conn.rollback()
        print(f"  ✗ {version} failed: {ex}")
        raise
    finally:
        cur.close()
        conn.close()


def cmd_pending():
    pending = get_pending_migrations()
    if not pending:
        print("No pending migrations.")
    else:
        print(f"Pending migrations ({len(pending)}):")
        for v, p in pending:
            print(f"  {v}  {p.name}")


def cmd_run():
    pending = get_pending_migrations()
    if not pending:
        print("Nothing to migrate.")
        return

    print(f"Running {len(pending)} migration(s)...")
    for version, path in pending:
        run_migration(version, path)
    print("All migrations applied.")


def cmd_status():
    ensure_migrations_table()
    applied = get_applied_migrations()
    if not applied:
        print("No migrations applied yet.")
        return
    print(f"Applied migrations ({len(applied)}):")
    for v in sorted(applied):
        print(f"  {v}")


def cmd_create(name: str):
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    version = f"V{ts}__{name}"
    path = MIGRATIONS_DIR / f"{version}.sql"
    content = (
        f"-- Migration: {name}\n"
        f"-- Version: {version}\n"
        f"-- Created: {datetime.now().isoformat()}\n"
        f"\n"
        f"BEGIN;\n"
        f"\n"
        f"-- TODO: write your migration SQL here\n"
        f"\n"
        f"COMMIT;\n"
        f"\n"
        f"-- rollback:\n"
        f"-- TODO: write rollback SQL here (optional)\n"
    )
    path.write_text(content, encoding="utf-8")
    print(f"Created: {path}")
    print(f"Edit the file and run: python scripts/migrate.py run")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "pending":
        cmd_pending()
    elif cmd == "run":
        cmd_run()
    elif cmd == "status":
        cmd_status()
    elif cmd == "create" and len(sys.argv) == 3:
        cmd_create(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
