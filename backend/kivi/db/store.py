"""Thin repository layer over SQLite. One inspectable file: database/kivi.db."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from kivi.config import DB_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def txn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- JSON helpers ----------

def load_json(value, default):
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# ---------- memory ----------

def get_memory(conn, memory_id: int):
    return conn.execute("SELECT * FROM memory WHERE id = ?", (memory_id,)).fetchone()


def get_memory_by_norm(conn, normalized_canonical: str):
    return conn.execute(
        "SELECT * FROM memory WHERE normalized_canonical = ?", (normalized_canonical,)
    ).fetchone()


def list_memories(conn, include_inactive: bool = True):
    q = "SELECT * FROM memory"
    if not include_inactive:
        q += " WHERE status != 'inactive'"
    q += " ORDER BY confidence DESC, id ASC"
    return conn.execute(q).fetchall()


def insert_memory(conn, *, canonical_form, normalized_canonical, entity_type,
                  status, confidence, positive_contexts, negative_contexts,
                  source, notes) -> int:
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO memory (canonical_form, normalized_canonical, entity_type, status,
                               confidence, positive_contexts, negative_contexts, source,
                               notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (canonical_form, normalized_canonical, entity_type, status, confidence,
         dump_json(positive_contexts), dump_json(negative_contexts), source, notes, ts, ts),
    )
    return cur.lastrowid


def update_memory(conn, memory_id: int, **fields):
    if not fields:
        return
    fields["updated_at"] = now_iso()
    for k in ("positive_contexts", "negative_contexts"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = dump_json(fields[k])
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE memory SET {cols} WHERE id = ?", (*fields.values(), memory_id))


# ---------- alias ----------

def list_aliases(conn, memory_id: int | None = None):
    if memory_id is None:
        return conn.execute("SELECT * FROM alias").fetchall()
    return conn.execute("SELECT * FROM alias WHERE memory_id = ?", (memory_id,)).fetchall()


def get_alias(conn, memory_id: int, normalized_form: str):
    return conn.execute(
        "SELECT * FROM alias WHERE memory_id = ? AND normalized_form = ?",
        (memory_id, normalized_form),
    ).fetchone()


def upsert_alias(conn, *, memory_id, surface_form, normalized_form, phonetic_key, origin):
    ts = now_iso()
    existing = get_alias(conn, memory_id, normalized_form)
    if existing:
        conn.execute(
            "UPDATE alias SET observation_count = observation_count + 1, last_seen = ? WHERE id = ?",
            (ts, existing["id"]),
        )
        return existing["id"]
    cur = conn.execute(
        """INSERT INTO alias (memory_id, surface_form, normalized_form, phonetic_key,
                              origin, observation_count, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?)""",
        (memory_id, surface_form, normalized_form, phonetic_key, origin, 1, ts, ts),
    )
    return cur.lastrowid


# ---------- observation ----------

def insert_observation(conn, *, type, raw_asr_text=None, formatted_text=None,
                       target_span=None, chosen_form=None, rejected_form=None,
                       context_snapshot=None, memory_id=None, decision_id=None) -> int:
    cur = conn.execute(
        """INSERT INTO observation (ts, type, raw_asr_text, formatted_text, target_span,
                                    chosen_form, rejected_form, context_snapshot, memory_id, decision_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (now_iso(), type, raw_asr_text, formatted_text, target_span, chosen_form,
         rejected_form, dump_json(context_snapshot) if context_snapshot is not None else None,
         memory_id, decision_id),
    )
    return cur.lastrowid


def list_observations(conn, memory_id: int | None = None):
    if memory_id is None:
        return conn.execute("SELECT * FROM observation ORDER BY id DESC").fetchall()
    return conn.execute(
        "SELECT * FROM observation WHERE memory_id = ? ORDER BY id DESC", (memory_id,)
    ).fetchall()


def observation_exists_for_decision(conn, decision_id: int, type: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM observation WHERE decision_id = ? AND type = ? LIMIT 1",
        (decision_id, type),
    ).fetchone()
    return row is not None


# ---------- evidence ----------

def insert_evidence(conn, *, memory_id, kind, weight, context_key=None, observation_id=None) -> int:
    cur = conn.execute(
        """INSERT INTO evidence (memory_id, kind, weight, context_key, observation_id, created_at)
           VALUES (?,?,?,?,?,?)""",
        (memory_id, kind, weight, context_key, observation_id, now_iso()),
    )
    return cur.lastrowid


def list_evidence(conn, memory_id: int):
    return conn.execute(
        "SELECT * FROM evidence WHERE memory_id = ? ORDER BY id ASC", (memory_id,)
    ).fetchall()


# ---------- request / decision ----------

def insert_request(conn, **fields) -> int:
    fields.setdefault("ts", now_iso())
    cols = ", ".join(fields)
    ph = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO request ({cols}) VALUES ({ph})", tuple(fields.values()))
    return cur.lastrowid


def get_request(conn, request_id: int):
    return conn.execute("SELECT * FROM request WHERE id = ?", (request_id,)).fetchone()


def insert_decision(conn, **fields) -> int:
    fields.setdefault("created_at", now_iso())
    cols = ", ".join(fields)
    ph = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO decision ({cols}) VALUES ({ph})", tuple(fields.values()))
    return cur.lastrowid


def get_decision(conn, decision_id: int):
    return conn.execute("SELECT * FROM decision WHERE id = ?", (decision_id,)).fetchone()


def list_decisions(conn, request_id: int | None = None):
    if request_id is None:
        return conn.execute("SELECT * FROM decision ORDER BY id DESC LIMIT 200").fetchall()
    return conn.execute(
        "SELECT * FROM decision WHERE request_id = ? ORDER BY id ASC", (request_id,)
    ).fetchall()


def list_sound_patterns(conn):
    return conn.execute(
        "SELECT * FROM sound_pattern ORDER BY weight DESC, observations DESC, id ASC"
    ).fetchall()


def table_counts(conn) -> dict:
    out = {}
    for t in ("memory", "alias", "observation", "evidence", "request", "decision",
              "sound_pattern"):
        out[t] = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
    return out
