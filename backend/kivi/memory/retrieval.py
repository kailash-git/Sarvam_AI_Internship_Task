"""Candidate retrieval. A match here is a NOMINATION, never a replacement.

Techniques (all deterministic, no ML):
  exact -> normalized -> fuzzy (Levenshtein ratio) -> phonetic (shared key + fuzzy floor)
  -> personal (this user's learned accent substitutions land the span on a memory)
Run against every alias of every non-inactive memory, plus the canonical form.

The `personal` method is what makes this a *personal* phonetic memory: it only
fires on mishearings that match how THIS user's ASR has been observed to mangle
sounds (see kivi.memory.phonetic_profile).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kivi.config import T, PP
from kivi.normalization import normalize_token
from kivi.phonetics import phonetic_key
from kivi.textmatch import ratio
from kivi.db.store import list_memories, list_aliases
from kivi.memory.phonetic_profile import (
    load_profile, apply_profile, asr_error_prior, derive_rules, rule_label,
)


@dataclass
class Candidate:
    memory_id: int
    canonical: str
    status: str
    confidence: float
    alias_surface: str
    match_method: str          # exact | normalized | fuzzy | phonetic | personal
    s_surf: float
    contradiction: bool = False
    s_personal: float = 0.0            # disambiguation prior: how often ASR mangles this memory
    personal_prior_n: int = 0          # raw count behind s_personal
    personal_rules: list = field(default_factory=list)  # rule labels that produced a personal hit


def _score_pair(span_norm: str, span_phon: str, alias_norm: str, alias_phon: str):
    """Return (method, s_surf) or None."""
    if span_norm == alias_norm:
        return ("exact", 1.0)
    r = ratio(span_norm, alias_norm)
    if r >= T["fuzzy_candidate"]:
        return ("fuzzy", round(r, 4))
    if span_phon and span_phon == alias_phon and r >= T["phonetic_fuzzy_floor"]:
        # phonetic nomination, scored below an exact/normalized hit
        return ("phonetic", round(max(0.85, r), 4))
    return None


def _personal_hit(variants_by_src: dict[str, set[str]], alias_norm: str):
    """Return (s_surf, [rule_labels]) for the best personal-accent match, or None."""
    if not variants_by_src:
        return None
    floor = float(PP.get("match_floor", 0.72))
    cap = float(PP.get("match_score_cap", 0.88))
    best = None
    for src, variants in variants_by_src.items():
        for v in variants:
            if v == alias_norm:
                score = cap
            else:
                r = ratio(v, alias_norm)
                if r < floor:
                    continue
                score = round(min(cap, r), 4)
            if best is None or score > best[0]:
                labels = [rule_label(x) for x in derive_rules(src, v)] or ["accent match"]
                best = (score, labels)
    return best


def find_candidates(conn, span_text: str, asr_original: str = "") -> list[Candidate]:
    span_norm = normalize_token(span_text)
    asr_norm = normalize_token(asr_original)
    if not span_norm and not asr_norm:
        return []
    span_phon = phonetic_key(span_norm)
    asr_phon = phonetic_key(asr_norm)

    memories = {m["id"]: m for m in list_memories(conn, include_inactive=False)}
    aliases = list_aliases(conn)

    # personal accent profile: transform the span the way this user's ASR does
    profile = load_profile(conn) if PP.get("enabled", True) else []
    variants_by_src: dict[str, set[str]] = {}
    if profile:
        for src in filter(None, {span_norm, asr_norm}):
            v = apply_profile(profile, src)
            if v:
                variants_by_src[src] = v

    # contradiction: a normalized surface owned by more than one memory
    owners: dict[str, set[int]] = {}
    for a in aliases:
        owners.setdefault(a["normalized_form"], set()).add(a["memory_id"])

    priors: dict[int, tuple[float, int]] = {}

    best_per_memory: dict[int, Candidate] = {}
    for a in aliases:
        mem = memories.get(a["memory_id"])
        if not mem:
            continue
        hit = None
        for sn, sp in ((span_norm, span_phon), (asr_norm, asr_phon)):
            if not sn:
                continue
            res = _score_pair(sn, sp, a["normalized_form"], a["phonetic_key"])
            if res and (hit is None or res[1] > hit[1]):
                hit = res
        personal_labels: list = []
        if hit is None:
            ph = _personal_hit(variants_by_src, a["normalized_form"])
            if ph:
                hit = ("personal", ph[0])
                personal_labels = ph[1]
        if not hit:
            continue
        method, s_surf = hit
        contradiction = (
            len(owners.get(a["normalized_form"], set())) > 1 or mem["status"] == "contested"
        )
        if mem["id"] not in priors:
            priors[mem["id"]] = asr_error_prior(conn, mem["id"])
        prior, prior_n = priors[mem["id"]]
        cand = Candidate(
            memory_id=mem["id"], canonical=mem["canonical_form"], status=mem["status"],
            confidence=mem["confidence"], alias_surface=a["surface_form"],
            match_method=method, s_surf=s_surf, contradiction=contradiction,
            s_personal=prior, personal_prior_n=prior_n, personal_rules=personal_labels,
        )
        cur = best_per_memory.get(mem["id"])
        if cur is None or cand.s_surf > cur.s_surf:
            best_per_memory[mem["id"]] = cand

    return sorted(best_per_memory.values(), key=lambda c: c.s_surf, reverse=True)
