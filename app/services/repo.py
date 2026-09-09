"""Data-access helpers over the SQLite schema. Plain functions, explicit SQL."""
from __future__ import annotations

import json
from typing import Any

from app.db.models import get_conn
from app.services.phonetics import phonetic_key

CATEGORIES = ("person", "org", "product", "term", "other")
STATUSES = ("candidate", "active", "suppressed")


# --------------------------------------------------------------------- entries

def _row_to_entry(row) -> dict[str, Any]:
    d = dict(row)
    with get_conn() as conn:
        aliases = [
            dict(a)
            for a in conn.execute(
                "SELECT surface_form, phonetic_key, observed_count, last_seen "
                "FROM aliases WHERE entry_id = ? ORDER BY observed_count DESC",
                (d["id"],),
            )
        ]
    d["aliases"] = aliases
    return d


def get_entry(entry_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
        ).fetchone()
    return _row_to_entry(row) if row else None


def find_entry(canonical: str, category: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM memory_entries WHERE lower(canonical) = lower(?) AND category = ?",
            (canonical, category),
        ).fetchone()
    return _row_to_entry(row) if row else None


def list_entries(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM memory_entries"
    params: tuple = ()
    if status:
        q += " WHERE status = ?"
        params = (status,)
    q += " ORDER BY updated_at DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_entry(r) for r in rows]


def create_entry(
    canonical: str,
    category: str,
    source: str,
    status: str = "candidate",
    confidence: float = 0.0,
    note: str = "",
) -> dict:
    key = phonetic_key(canonical)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO memory_entries
                (canonical, category, phonetic_primary, phonetic_secondary,
                 status, confidence, source, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (canonical, category, key.primary, key.secondary, status,
             confidence, source, note),
        )
        entry_id = cur.lastrowid
    return get_entry(entry_id)  # type: ignore[return-value]


def update_entry(entry_id: int, **fields) -> dict | None:
    if not fields:
        return get_entry(entry_id)
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE memory_entries SET {cols}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), entry_id),
        )
    return get_entry(entry_id)


def delete_entry(entry_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
    return cur.rowcount > 0


# --------------------------------------------------------------------- aliases

def add_alias(entry_id: int, surface_form: str) -> None:
    key = phonetic_key(surface_form)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO aliases (entry_id, surface_form, phonetic_key, observed_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT (entry_id, surface_form)
            DO UPDATE SET observed_count = observed_count + 1,
                          last_seen = datetime('now')
            """,
            (entry_id, surface_form, key.primary or key.soundex),
        )


def all_aliases() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT a.*, m.canonical, m.category, m.status, m.confidence "
            "FROM aliases a JOIN memory_entries m ON m.id = a.entry_id"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- observations

def add_observation(
    type: str,
    *,
    asr_text: str = "",
    formatted_text: str = "",
    corrected_text: str = "",
    from_form: str = "",
    to_form: str = "",
    category: str = "",
    entry_id: int | None = None,
    raw_payload: dict | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO observations
                (type, asr_text, formatted_text, corrected_text, from_form,
                 to_form, category, entry_id, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (type, asr_text, formatted_text, corrected_text, from_form, to_form,
             category, entry_id, json.dumps(raw_payload or {})),
        )
        return cur.lastrowid


def observations_for_entry(entry_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM observations WHERE entry_id = ? ORDER BY id", (entry_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def count_observations(entry_id: int, type: str) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM observations WHERE entry_id = ? AND type = ?",
            (entry_id, type),
        ).fetchone()[0]


# ----------------------------------------------------------------- utterances

def record_utterance(
    asr_text: str,
    formatted_text: str,
    memory_aware_text: str,
    intervened: bool,
    decision_trace: dict,
    latency_ms: float,
    llm_calls: int,
    llm_mode: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO utterances
                (asr_text, formatted_text, memory_aware_text, intervened,
                 decision_trace, latency_ms, llm_calls, llm_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asr_text, formatted_text, memory_aware_text, int(intervened),
             json.dumps(decision_trace), latency_ms, llm_calls, llm_mode),
        )
        return cur.lastrowid


def record_intervention(
    utterance_id: int,
    entry_id: int | None,
    span_text: str,
    from_text: str,
    to_text: str,
    applied: bool,
    score: float,
    threshold: float,
    reason_tag: str,
    detail: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO interventions
                (utterance_id, entry_id, span_text, from_text, to_text, applied,
                 score, threshold, reason_tag, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (utterance_id, entry_id, span_text, from_text, to_text, int(applied),
             score, threshold, reason_tag, detail),
        )


def recent_utterances(limit: int = 25) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM utterances ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["decision_trace"] = json.loads(d["decision_trace"])
        out.append(d)
    return out


# ---------------------------------------------------------------------- stats

def stats() -> dict:
    with get_conn() as conn:
        def one(q):
            return conn.execute(q).fetchone()[0]

        return {
            "entries_total": one("SELECT COUNT(*) FROM memory_entries"),
            "entries_active": one("SELECT COUNT(*) FROM memory_entries WHERE status='active'"),
            "entries_candidate": one("SELECT COUNT(*) FROM memory_entries WHERE status='candidate'"),
            "entries_suppressed": one("SELECT COUNT(*) FROM memory_entries WHERE status='suppressed'"),
            "aliases_total": one("SELECT COUNT(*) FROM aliases"),
            "observations_total": one("SELECT COUNT(*) FROM observations"),
            "utterances_total": one("SELECT COUNT(*) FROM utterances"),
            "interventions_applied": one("SELECT COUNT(*) FROM interventions WHERE applied=1"),
            "interventions_declined": one("SELECT COUNT(*) FROM interventions WHERE applied=0"),
        }
