"""Load deterministic seed data. Confidence/status are recomputed from evidence."""
from __future__ import annotations

import json

from kivi.config import SEED_FILE
from kivi.normalization import normalize_token
from kivi.phonetics import phonetic_key
from kivi.memory.confidence import compute_confidence, derive_status, apply_authoritative_floor
from kivi.memory.phonetic_profile import weight_for
from kivi.db.store import (
    txn, insert_memory, update_memory, upsert_alias, insert_observation,
    insert_evidence, list_evidence, now_iso,
)


def seed() -> dict:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    loaded = []
    with txn() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM memory").fetchone()["c"]
        if existing:
            return {"status": "skipped", "reason": f"{existing} memories already present"}

        ts = now_iso()
        for sp in data.get("sound_patterns", []):
            obs = int(sp.get("observations", 1))
            conn.execute(
                """INSERT INTO sound_pattern (position, src, dst, observations, weight,
                                              origin, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sp["position"], sp.get("src", ""), sp.get("dst", ""), obs,
                 weight_for(obs), sp.get("origin", "seed"), ts, ts),
            )

        for m in data["memories"]:
            norm = normalize_token(m["canonical_form"])
            mid = insert_memory(
                conn, canonical_form=m["canonical_form"], normalized_canonical=norm,
                entity_type=m.get("entity_type", "term"), status="proposed", confidence=0.0,
                positive_contexts=m.get("positive_contexts", {"keywords": [], "domains": []}),
                negative_contexts=m.get("negative_contexts", {"keywords": [], "domains": []}),
                source=m.get("source", "seed"), notes=m.get("notes"),
            )
            for a in m.get("aliases", []):
                nf = normalize_token(a["surface"])
                upsert_alias(conn, memory_id=mid, surface_form=a["surface"], normalized_form=nf,
                             phonetic_key=phonetic_key(nf), origin=a.get("origin", "seed"))
            authoritative = False
            for e in m.get("evidence", []):
                obs_id = insert_observation(
                    conn, type=e.get("obs_type", "manual_teach"),
                    chosen_form=m["canonical_form"],
                    context_snapshot={"keywords": [], "domain": e.get("context_key") or "general"},
                    memory_id=mid,
                )
                insert_evidence(conn, memory_id=mid, kind=e["kind"], weight=e["weight"],
                                context_key=e.get("context_key"), observation_id=obs_id)
                if e["kind"] == "strong_positive":
                    authoritative = True
            ev = list_evidence(conn, mid)
            conf = apply_authoritative_floor(compute_confidence(ev),
                                             user_authoritative=authoritative)
            status = derive_status("proposed", conf, user_authoritative=authoritative,
                                   contradiction=False)
            update_memory(conn, mid, confidence=conf, status=status)
            loaded.append({"canonical": m["canonical_form"], "confidence": conf, "status": status})

        sp_count = conn.execute("SELECT COUNT(*) AS c FROM sound_pattern").fetchone()["c"]

    return {"status": "ok", "memories": loaded, "sound_patterns": sp_count}


if __name__ == "__main__":
    import pprint
    pprint.pp(seed())
