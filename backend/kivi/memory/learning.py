"""Learning pipeline: the ONLY path that mutates memory.

observation (immutable)  ->  evidence (weighted)  ->  confidence (re-derived)  ->  status

Positive observations resolve/create the memory by `chosen_form`.
Negative observations (rejection) resolve the memory being rejected by `rejected_form`
(or explicit `memory_id`) and NEVER create a memory.

Observation types:
  explicit_correction   strong_positive (+1.0), scoped to the utterance domain, authoritative
  manual_teach          strong_positive (+1.0), global, authoritative
  confirmation          strong_positive (+0.8), scoped, authoritative
  asr_pair              weak_positive  (+0.15), scoped
  rejection             negative_context (-1.0), scoped  -> does NOT touch global confidence
  rejection_global      negative_context (-1.0) + rejection (-1.0, global)
"""
from __future__ import annotations

from kivi.config import CONTEXT_LIST_MAX
from kivi.normalization import normalize_token, normalize, content_tokens
from kivi.phonetics import phonetic_key
from kivi.context import guess_domain
from kivi.memory.confidence import compute_confidence, derive_status, apply_authoritative_floor
from kivi.memory.phonetic_profile import record_pair
from kivi.db.store import (
    txn, get_memory, get_memory_by_norm, insert_memory, update_memory,
    upsert_alias, insert_observation, insert_evidence, list_evidence,
    load_json, observation_exists_for_decision, get_decision,
)

_WEIGHTS = {
    "explicit_correction": ("strong_positive", 1.0),
    "manual_teach": ("strong_positive", 1.0),
    "confirmation": ("strong_positive", 0.8),
    "asr_pair": ("weak_positive", 0.15),
    "rejection": ("negative_context", -1.0),
    "rejection_global": ("negative_context", -1.0),
    "context_flag": ("negative_context", -1.0),
}
_AUTHORITATIVE = {"explicit_correction", "manual_teach", "confirmation"}
_NEGATIVE = {"rejection", "rejection_global", "context_flag"}
# Types that represent a real ASR mishearing (something was heard, then corrected).
# `manual_teach` is the user typing a term with no ASR involved -> no accent signal.
_ASR_ERROR_TYPES = {"asr_pair", "explicit_correction", "confirmation"}


def _merge_context_list(existing: dict, keywords: list[str], domain: str) -> dict:
    kw = list(dict.fromkeys([*keywords, *existing.get("keywords", [])]))[:CONTEXT_LIST_MAX]
    doms = list(existing.get("domains", []))
    if domain and domain != "general" and domain not in doms:
        doms.append(domain)
    return {"keywords": kw, "domains": doms}


def _recompute(conn, memory_id: int, *, authoritative: bool, contradiction: bool):
    ev = list_evidence(conn, memory_id)
    conf = apply_authoritative_floor(compute_confidence(ev), user_authoritative=authoritative)
    mem = get_memory(conn, memory_id)
    status = derive_status(mem["status"], conf, user_authoritative=authoritative,
                           contradiction=contradiction)
    update_memory(conn, memory_id, confidence=conf, status=status)
    return conf, status


def observe(*, type: str, chosen_form: str | None = None, rejected_form: str | None = None,
            asr_original: str | None = None, raw_asr_text: str | None = None,
            formatted_text: str | None = None, context: dict | None = None,
            entity_type: str | None = None, decision_id: int | None = None,
            memory_id: int | None = None) -> dict:
    if type not in _WEIGHTS:
        raise ValueError(f"unknown observation type: {type}")

    is_negative = type in _NEGATIVE
    chosen_form = (chosen_form or "").strip()
    rejected_form = (rejected_form or "").strip() or None
    asr_original = (asr_original or "").strip() or None

    # derive context
    ctx = context or {}
    kws = ctx.get("keywords")
    if kws is None:
        kws = content_tokens(f"{raw_asr_text or ''} {formatted_text or ''}")
    domain = ctx.get("domain") or guess_domain(kws)

    with txn() as conn:
        # idempotency guard
        if decision_id is not None and observation_exists_for_decision(conn, decision_id, type):
            return {"status": "noop", "reason": "already recorded for this decision"}

        # ---------------- resolve target memory ----------------
        if is_negative:
            mem = get_memory(conn, memory_id) if memory_id else None
            if mem is None and decision_id is not None:
                dec = get_decision(conn, decision_id)
                if dec and dec["candidate_memory_id"]:
                    mem = get_memory(conn, dec["candidate_memory_id"])
            if mem is None and rejected_form:
                mem = get_memory_by_norm(conn, normalize_token(rejected_form))
            if mem is None:
                raise ValueError(
                    "rejection needs an existing target memory (rejected_form / memory_id / decision_id)"
                )
            created = False
        else:
            if not chosen_form:
                raise ValueError("chosen_form is required for positive observations")
            wrong_surface = rejected_form or asr_original
            norm_chosen = normalize_token(chosen_form) or normalize(chosen_form)
            if (wrong_surface and normalize_token(wrong_surface) == norm_chosen
                    and type != "manual_teach"):
                raise ValueError("chosen_form and rejected_form are the same after normalization")
            mem = get_memory_by_norm(conn, norm_chosen)
            created = mem is None
            if mem is None:
                mid = insert_memory(
                    conn, canonical_form=chosen_form, normalized_canonical=norm_chosen,
                    entity_type=entity_type or "term", status="proposed", confidence=0.0,
                    positive_contexts={"keywords": [], "domains": []},
                    negative_contexts={"keywords": [], "domains": []},
                    source="user_taught", notes=None,
                )
                mem = get_memory(conn, mid)

        memory_id = mem["id"]
        before = {"confidence": mem["confidence"], "status": mem["status"]}

        obs_id = insert_observation(
            conn, type=type, raw_asr_text=raw_asr_text, formatted_text=formatted_text,
            target_span=(rejected_form or asr_original), chosen_form=chosen_form or None,
            rejected_form=rejected_form, context_snapshot={"keywords": kws, "domain": domain},
            memory_id=memory_id, decision_id=decision_id,
        )

        changes: list[str] = []
        phonetic_rules_learned: list[str] = []

        # ---------------- aliases (positive only) ----------------
        if not is_negative:
            for surf in filter(None, {rejected_form, asr_original, chosen_form}):
                nf = normalize_token(surf)
                if not nf:
                    continue
                origin = "asr_observed" if surf != chosen_form else "user"
                upsert_alias(conn, memory_id=memory_id, surface_form=surf, normalized_form=nf,
                             phonetic_key=phonetic_key(nf), origin=origin)
            wrong = rejected_form or asr_original
            if wrong:
                changes.append(f"alias '{wrong}' -> {mem['canonical_form']}")
                # ---- accent profile: learn HOW this user's ASR mangled the word ----
                if type in _ASR_ERROR_TYPES and normalize_token(wrong) != normalize_token(chosen_form):
                    phonetic_rules_learned = record_pair(conn, wrong, chosen_form)
                    if phonetic_rules_learned:
                        changes.append(
                            "accent profile += " + ", ".join(phonetic_rules_learned)
                        )

        # ---------------- evidence + context ----------------
        kind, weight = _WEIGHTS[type]
        insert_evidence(conn, memory_id=memory_id, kind=kind, weight=weight,
                        context_key=domain, observation_id=obs_id)
        if type == "rejection_global":
            insert_evidence(conn, memory_id=memory_id, kind="rejection", weight=-1.0,
                            context_key=None, observation_id=obs_id)

        pos = load_json(mem["positive_contexts"], {"keywords": [], "domains": []})
        neg = load_json(mem["negative_contexts"], {"keywords": [], "domains": []})
        if is_negative:
            neg = _merge_context_list(neg, kws, domain)
            changes.append(f"negative context += {kws} (domain {domain})")
        else:
            pos = _merge_context_list(pos, kws, domain)
            changes.append(f"positive context += {kws} (domain {domain})")
        update_memory(conn, memory_id, positive_contexts=pos, negative_contexts=neg)

        authoritative = type in _AUTHORITATIVE
        after_conf, after_status = _recompute(conn, memory_id, authoritative=authoritative,
                                              contradiction=False)

        return {
            "status": "ok",
            "observation_id": obs_id,
            "memory_id": memory_id,
            "created": created,
            "canonical_form": mem["canonical_form"],
            "before": before,
            "after": {"confidence": after_conf, "status": after_status},
            "evidence_kind": kind,
            "scoped_to_context": domain if (is_negative and type == "rejection") else None,
            "global_confidence_touched": type in ("rejection_global",) or not is_negative,
            "phonetic_rules_learned": phonetic_rules_learned,
            "changes": changes,
        }
