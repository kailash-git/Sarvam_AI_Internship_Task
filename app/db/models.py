"""SQLite connection management and thin row helpers.

No ORM: the schema is small and the queries are explicit. `get_conn()` yields a
connection with foreign keys enforced and `row_factory` set to `sqlite3.Row`.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings

_DB_PATH_OVERRIDE: str | None = None


def set_db_path(path: str | None) -> None:
    """Point the whole app at a different database file (used by tests/eval)."""
    global _DB_PATH_OVERRIDE
    _DB_PATH_OVERRIDE = path


def current_db_path() -> str:
    return _DB_PATH_OVERRIDE or settings.resolved_db_path()


def connect() -> sqlite3.Connection:
    path = current_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_file_size_bytes() -> int:
    p = Path(current_db_path())
    return p.stat().st_size if p.exists() else 0
