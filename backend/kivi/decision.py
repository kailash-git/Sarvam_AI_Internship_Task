"""Deterministic, explainable decision engine: REPLACE / KEEP / DEFER.

combined = s_surf * confidence * context_gate * personal_boost
  (multiplicative: any weak factor vetoes; personal_boost in [1, 1+PP.combined_boost])

`personal_boost` reflects how often THIS user's ASR has mangled this exact memory
before - a small, capped lift, never a veto, and always applied AFTER the safety
gates so it can never override a deliberate KEEP or a not-yet-active memory.

Hard gates, checked in order:
  1. no candidate            -> KEEP
  2. s_ctx_neg >= ctx_neg    -> KEEP  (deliberate non-intervention)
  3. ambiguous / contradiction -> DEFER   (unless the user's correction history
                                           clearly favours one side -> tiebreak)
  4. candidate not 'active'  -> DEFER if combined>=defer else KEEP
Then bands: combined >= replace -> REPLACE ; >= defer -> DEFER ; else KEEP
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kivi.config import T, PP


@dataclass
class SpanDecision:
    span_text: str
    span_start: int
    span_end: int
    asr_original: str
    action: str = "KEEP"
    reason_code: str = "no_memory"
    reason_text: str = ""
    candidate_memory_id: int | None = None
    candidate_canonical: str | None = None
    match_method: str | None = None
    s_surf: float = 0.0
    s_ctx_pos: float = 0.0
    s_ctx_neg: float = 0.0
    s_ctx: float = 0.0
    mem_confidence: float = 0.0
    combined_score: float = 0.0
    ambiguity_flag: bool = False
    contradiction_flag: bool = False
    replacement: str | None = None
    runner_up: dict | None = None
    alternatives: list = field(default_factory=list)
    s_personal: float = 0.0
    personal_prior_n: int = 0
    personal_rules: list = field(default_factory=list)
    personal_note: str = ""


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _context_gate(s_ctx: float) -> float:
    if s_ctx >= T["ctx_pos"]:
        return 1.0
    return round(_clamp01((s_ctx - T["ctx_low"]) / (T["ctx_pos"] - T["ctx_low"])), 4)


def _personal_clause(d, cand, top) -> str:
    """Human sentence for the personal-phonetics contribution, or ''."""
    bits: list[str] = []
    if cand.match_method == "personal" and cand.personal_rules:
        bits.append(
            "Nominated by your accent profile (learned rule "
            + ", ".join(cand.personal_rules) + ")."
        )
    if top.get("boost", 1.0) > 1.0 and cand.personal_prior_n > 0:
        bits.append(
            f"Your ASR has mis-spelled '{cand.canonical}' {cand.personal_prior_n}x before, "
            f"so its score was lifted x{top['boost']:.2f}."
        )
    if d.personal_note:
        bits.append(d.personal_note)
    return (" " + " ".join(bits)) if bits else ""


def decide(span_text, span_start, span_end, asr_original, scored) -> SpanDecision:
    """`scored` = list of dicts: {cand, s_ctx_pos, s_ctx_neg, s_ctx} sorted by s_surf desc."""
    d = SpanDecision(span_text, span_start, span_end, asr_original)

    if not scored:
        d.reason_text = f"No memory matched '{span_text}'."
        return d

    # combined score for every candidate.
    # `base` = s_surf * confidence * context_gate (the original multiplicative score).
    # `combined` additionally applies the personal-history boost.
    boost_max = float(PP.get("combined_boost", 0.35))
    for s in scored:
        c = s["cand"]
        gate = _context_gate(s["s_ctx"])
        # First-recall of the user's own correction: an EXACT match to a stored
        # alias, on an active memory this user has already corrected before, is
        # not a guess - so a not-yet-established positive context should not hold
        # it back. The negative-context KEEP gate (checked later) still protects
        # cases like "I ate a kiwi".
        s["gate_forced"] = (
            gate < 1.0
            and s["s_ctx"] >= 0.0          # only when context is neutral/positive,
            and c.status == "active"       # never when the surrounding words lean away
            and c.match_method == "exact"
            and c.s_surf >= 0.99
            and c.personal_prior_n >= 1
            and any(ch.isupper() for ch in c.canonical)  # proper nouns only - an
            # everyday-word homophone (sea/see, to/too) has no grammar signal here
            # and must earn REPLACE through context on both sides, not one correction
        )
        if s["gate_forced"]:
            gate = 1.0
        s["gate"] = gate
        s["base"] = round(c.s_surf * c.confidence * gate, 4)
        s["boost"] = round(1.0 + boost_max * max(0.0, min(1.0, c.s_personal)), 4)
        s["combined"] = round(min(1.0, s["base"] * s["boost"]), 4)
    scored.sort(key=lambda s: s["combined"], reverse=True)

    top = scored[0]
    cand = top["cand"]
    d.candidate_memory_id = cand.memory_id
    d.candidate_canonical = cand.canonical
    d.match_method = cand.match_method
    d.s_surf = cand.s_surf
    d.s_ctx_pos = top["s_ctx_pos"]
    d.s_ctx_neg = top["s_ctx_neg"]
    d.s_ctx = top["s_ctx"]
    d.mem_confidence = cand.confidence
    d.combined_score = top["combined"]
    d.contradiction_flag = bool(cand.contradiction)
    d.s_personal = cand.s_personal
    d.personal_prior_n = cand.personal_prior_n
    d.personal_rules = list(cand.personal_rules)
    d.alternatives = [
        {"canonical": s["cand"].canonical, "combined": s["combined"],
         "s_surf": s["cand"].s_surf, "method": s["cand"].match_method,
         "misheard_count": s["cand"].personal_prior_n}
        for s in scored[:3]
    ]

    # ambiguity: two different memories, both non-trivial, close in score.
    # The personal-history prior can resolve it two ways:
    #   (a) it separated a pre-boost near-tie   -> REPLACE, with a note saying so
    #   (b) they are STILL tied after the boost -> tiebreak to the more-misheard one,
    #       else DEFER as a genuine ambiguity.
    if len(scored) >= 2:
        second = scored[1]
        min_n = int(PP.get("tiebreak_min_count", 3))
        gap_n = cand.personal_prior_n - second["cand"].personal_prior_n
        history_favours_top = gap_n >= min_n and cand.personal_prior_n > second["cand"].personal_prior_n
        if (second["cand"].memory_id != cand.memory_id
                and top["combined"] >= T["defer"] * 0.6):
            post_close = (top["combined"] - second["combined"]) < T["ambiguity_margin"]
            pre_close = (top["base"] - second["base"]) < T["ambiguity_margin"]
            if post_close and history_favours_top:
                d.personal_note = (
                    f"Ambiguity broken by your correction history: '{cand.canonical}' has been "
                    f"misheard {cand.personal_prior_n}x vs {second['cand'].personal_prior_n}x "
                    f"for '{second['cand'].canonical}'."
                )
            elif post_close:
                d.ambiguity_flag = True
                d.runner_up = {"canonical": second["cand"].canonical,
                               "combined": second["combined"]}
            elif pre_close and history_favours_top:
                d.personal_note = (
                    f"Your correction history separated a near-tie: '{cand.canonical}' has been "
                    f"misheard {cand.personal_prior_n}x vs {second['cand'].personal_prior_n}x "
                    f"for '{second['cand'].canonical}'."
                )

    # ---- gates ----
    if d.s_ctx_neg >= T["ctx_neg"]:
        d.action = "KEEP"
        d.reason_code = "negative_context"
        d.reason_text = (
            f"Kept '{span_text}' unchanged. Memory '{cand.canonical}' matches "
            f"({cand.match_method}, {cand.s_surf:.2f}), but the surrounding words match this "
            f"memory's do-not-apply context (negative-context score {d.s_ctx_neg:.2f}). "
            f"'{cand.canonical}' is unaffected."
        )
        return d

    if d.ambiguity_flag or d.contradiction_flag:
        d.action = "DEFER"
        d.reason_code = "ambiguous" if d.ambiguity_flag else "contradiction"
        if d.ambiguity_flag:
            d.reason_text = (
                f"Deferred on '{span_text}'. It matches '{cand.canonical}' "
                f"({top['combined']:.2f}) and '{d.runner_up['canonical']}' "
                f"({d.runner_up['combined']:.2f}); scores are too close to choose."
            )
        else:
            d.reason_text = (
                f"Deferred on '{span_text}'. The surface form is claimed by more than one "
                f"memory (or '{cand.canonical}' is contested). Awaiting your confirmation."
            )
        return d

    if cand.status != "active":
        if top["combined"] >= T["defer"]:
            d.action = "DEFER"
            d.reason_code = "memory_not_active"
            d.reason_text = (
                f"Suggested '{cand.canonical}' for '{span_text}' but memory is "
                f"'{cand.status}' (confidence {cand.confidence:.2f}); needs your confirmation "
                f"before it will auto-replace."
            )
        else:
            d.action = "KEEP"
            d.reason_code = "weak_below_defer"
            d.reason_text = (
                f"Kept '{span_text}'. Only a weak, '{cand.status}' memory "
                f"'{cand.canonical}' matched (combined {top['combined']:.2f})."
            )
        d.reason_text += _personal_clause(d, cand, top)
        return d

    if top["combined"] >= T["replace"]:
        d.action = "REPLACE"
        d.reason_code = "replace_confident"
        d.replacement = cand.canonical
        d.reason_text = (
            f"Replaced '{span_text}' with '{cand.canonical}': {cand.match_method} match "
            f"(surface {cand.s_surf:.2f}) to an active memory (confidence "
            f"{cand.confidence:.2f}); context score {d.s_ctx:+.2f}. Combined {top['combined']:.2f}."
        )
        if top.get("gate_forced"):
            d.reason_text += (
                " Applied on the first recall: you have corrected this exact mishearing "
                "before, so the surrounding context was not required."
            )
        d.reason_text += _personal_clause(d, cand, top)
    elif top["combined"] >= T["defer"]:
        d.action = "DEFER"
        d.reason_code = "borderline"
        d.reason_text = (
            f"Deferred on '{span_text}'. '{cand.canonical}' is plausible "
            f"(combined {top['combined']:.2f}) but below the replace threshold "
            f"({T['replace']:.2f}). Shown as a suggestion."
        )
        d.reason_text += _personal_clause(d, cand, top)
    else:
        d.action = "KEEP"
        d.reason_code = "below_threshold"
        d.reason_text = (
            f"Kept '{span_text}'. '{cand.canonical}' matched but the combined score "
            f"({top['combined']:.2f}) is below the defer threshold ({T['defer']:.2f})."
        )
    return d
