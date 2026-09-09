"""Minimal forward-only migration runner.

Applies every `NNNN_*.sql` file in `migrations/` that has not yet been recorded
in `schema_migrations`, in filename order, each in its own transaction.

Usage:
    python -m app.db.migrate            # apply pending migrations
    python -m app.db.migrate --status   # show applied / pending
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.db.models import connect, current_db_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _applied(conn) -> set[str]:
    _ensure_table(conn)
    return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}


def pending() -> list[Path]:
    with connect() as conn:
        done = _applied(conn)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.stem not in done]


def migrate() -> list[str]:
    applied_now: list[str] = []
    conn = connect()
    try:
        done = _applied(conn)
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.stem in done:
                continue
            sql = f.read_text(encoding="utf-8")
            conn.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (f.stem,)
            )
            conn.commit()
            applied_now.append(f.stem)
    finally:
        conn.close()
    return applied_now


def status() -> None:
    with connect() as conn:
        done = sorted(_applied(conn))
    all_files = sorted(f.stem for f in MIGRATIONS_DIR.glob("*.sql"))
    print(f"database: {current_db_path()}")
    for v in all_files:
        print(f"  [{'x' if v in done else ' '}] {v}")


if __name__ == "__main__":
    if "--status" in sys.argv:
        status()
    else:
        done = migrate()
        if done:
            print("applied:", ", ".join(done))
        else:
            print("nothing to apply; schema up to date")
