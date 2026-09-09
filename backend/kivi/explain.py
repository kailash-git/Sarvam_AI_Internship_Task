"""Assemble the per-span decision trace the reviewer inspects."""
from __future__ import annotations

from kivi.db.store import list_evidence


def _evidence_summary(conn, memory_id: int) -> dict:
    rows = list_evidence(conn, memory_id)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return counts


def build_trace(conn, decisions) -> list[dict]:
    trace = []
    for d in decisions:
        entry = {
            "span": d.span_text,
            "asr_original": d.asr_original,
            "action": d.action,
            "reason_code": d.reason_code,
            "reason": d.reason_text,
            "matched_memory": d.candidate_canonical,
            "match_method": d.match_method,
            "scores": {
                "s_surf": round(d.s_surf, 3),
                "s_ctx_pos": round(d.s_ctx_pos, 3),
                "s_ctx_neg": round(d.s_ctx_neg, 3),
                "s_ctx": round(d.s_ctx, 3),
                "confidence": round(d.mem_confidence, 3),
                "combined": round(d.combined_score, 3),
            },
            "ambiguity": d.ambiguity_flag,
            "contradiction": d.contradiction_flag,
            "alternatives": d.alternatives,
            "replacement": d.replacement,
            "personal": {
                "method_personal": d.match_method == "personal",
                "s_personal": round(d.s_personal, 3),
                "misheard_count": d.personal_prior_n,
                "rules": d.personal_rules,
                "note": d.personal_note or None,
            },
        }
        if d.candidate_memory_id:
            entry["evidence"] = _evidence_summary(conn, d.candidate_memory_id)
        trace.append(entry)
    return trace


def summarize(decisions) -> dict:
    return {
        "replaced": [d.span_text for d in decisions if d.action == "REPLACE"],
        "deferred": [d.span_text for d in decisions if d.action == "DEFER"],
        "kept_with_candidate": [
            d.span_text for d in decisions
            if d.action == "KEEP" and d.candidate_memory_id
        ],
    }
