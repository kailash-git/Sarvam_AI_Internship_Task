"""Reset: delete the SQLite file, re-run migrations, reload seed. The reset/repeat workflow."""
from __future__ import annotations

from kivi.config import DB_PATH
from kivi.db.migrate import migrate
from kivi.db.seed import seed
from kivi.db.store import connect, table_counts


def reset() -> dict:
    for suffix in ("", "-wal", "-shm"):
        p = DB_PATH.parent / (DB_PATH.name + suffix)
        if p.exists():
            p.unlink()
    applied = migrate()
    seed_result = seed()
    conn = connect()
    try:
        counts = table_counts(conn)
    finally:
        conn.close()
    return {"status": "ok", "migrations_applied": applied, "seed": seed_result, "counts": counts}


if __name__ == "__main__":
    import pprint
    pprint.pp(reset())
