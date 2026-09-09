"""Forward-only migration runner. Applies database/migrations/*.sql once each."""
from __future__ import annotations

from kivi.config import MIGRATIONS_DIR
from kivi.db.store import connect, now_iso


def _applied(conn) -> set[str]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not row:
        return set()
    return {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}


def migrate() -> list[str]:
    conn = connect()
    applied = _applied(conn)
    ran: list[str] = []
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?,?)",
                (version, now_iso()),
            )
            conn.commit()
            ran.append(version)
    finally:
        conn.close()
    return ran


if __name__ == "__main__":
    print("applied:", migrate() or "(nothing new)")
