"""Reset helpers for the demo and the evaluation."""
from __future__ import annotations

from app.db.migrate import migrate
from app.db.models import get_conn

_DATA_TABLES = (
    "interventions", "utterances", "observations", "aliases", "memory_entries",
)


def reset(seed: bool = True) -> dict:
    """Wipe all learned state; keep the schema. Optionally re-seed."""
    migrate()  # ensure schema exists
    with get_conn() as conn:
        for table in _DATA_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('interventions','utterances','observations','aliases','memory_entries')"
        )
    result = {"reset": True, "seeded": False}
    if seed:
        from app.db.seed import seed as run_seed

        result["seeded"] = True
        result["seed"] = run_seed()
    return result
