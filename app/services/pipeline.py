"""The decision layer: candidates -> decisions -> memory-aware text -> trace.

For every retrieved candidate we emit exactly one Decision with a reason tag.
`REASONS` is the closed vocabulary; every "did nothing" is one of these and is
persisted, so the demo and the evaluation can always answer *why*.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from app.config import settings
from app.services import repo
from app.services.common_words import food_context_score
from app.services.llm import GlossaryItem, Replacement, rewrite_with_glossary, _match_case
from app.services.phonetics import surface_similarity
from app.services.retrieval import Candidate, retrieve

REASONS = {
    "applied": "memory entry applied to the span",
    "below_threshold": "combined score below the apply threshold",
    "not_active": "entry is still a candidate (insufficient evidence)",
    "suppressed": "entry was suppressed after repeated rejections",
    "already_canonical": "span already matches the canonical form",
    "common_word_guard": "span is an everyday word in ordinary context",
    "food_context_guard": "sentence is about food; refused to overwrite a homophone",
    "ambiguous_conflict": "two memory entries match this span equally well",
    "weak_surface_match": "phonetic codes rhyme but the spellings are too far apart for a canonical-only match",
    "low_confidence": "entry confidence below the minimum to act",
}

_MIN_CONFIDENCE_TO_ACT = 0.50
# For a canonical-only match (no distinct learned alias), the span and canonical
# must also be close at the letter level. Blocks name<->unrelated-proper-noun
# collisions like "Colin"/"Cologne" while leaving "kiwi"/"Kivi" (letters ~1.0)
# and any alias-backed match untouched.
_MIN_SURFACE_FOR_CANONICAL = 0.85


@dataclass
class Decision:
    entry_id: int
    canonical: str
    category: str
    span_text: str
    start: int
    end: int
    matched_form: str
    matched_via: str
    phonetic_score: float
    combined_score: float
    threshold: float
    action: str            # "apply" | "skip"
    reason_tag: str
    detail: str = ""
    rivals: list[dict] = field(default_factory=list)


@dataclass
class ProcessResult:
    asr_text: str
    formatted_text: str
    memory_aware_text: str
    intervened: bool
    decisions: list[Decision]
    trace: dict
    utterance_id: int | None = None


def _decide(c: Candidate) -> Decision:
    thr = settings.apply_threshold
    base = dict(
        entry_id=c.entry_id, canonical=c.canonical, category=c.category,
        span_text=c.span_text, start=c.start, end=c.end,
        matched_form=c.matched_form, matched_via=c.matched_via,
        phonetic_score=c.phonetic_score, combined_score=c.combined_score,
        threshold=thr, rivals=c.rivals,
    )

    def skip(tag: str, detail: str = "") -> Decision:
        return Decision(**base, action="skip", reason_tag=tag, detail=detail)

    if c.already_canonical:
        return skip("already_canonical")
    if c.status == "suppressed":
        return skip("suppressed")
    if c.status == "candidate":
        return skip("not_active", f"needs {settings.promote_after} corroborating corrections")

    # Homophone guards run before the ambiguity check: a more specific reason.
    # A lower-case span (common-noun position) that names a product/org, in a
    # sentence that is clearly about food, is left alone ("I ate a kiwi").
    if c.category in ("product", "org") and c.span_text[:1].islower() \
            and food_context_score(c.context_tokens) >= 1.0:
        return skip("food_context_guard", "food-context cues; span is a common-noun homophone")

    if c.span_is_common_word and not (c.matched_via == "alias" and c.phonetic_score >= 0.95) \
            and c.combined_score < thr + 0.10:
        return skip("common_word_guard")

    strong_rivals = [
        r for r in c.rivals
        if r["phonetic_score"] >= 0.80
        and abs(r["combined_score"] - c.combined_score) < 0.08
    ]
    if strong_rivals:
        competitors = [
            {"entry_id": c.entry_id, "canonical": c.canonical,
             "status": c.status, "confidence": c.confidence},
            *strong_rivals,
        ]
        ctx = set(c.context_tokens)
        in_ctx = [
            comp for comp in competitors
            if any(tok.lower() in ctx for tok in comp["canonical"].split())
            and comp["status"] == "active"
            and comp["confidence"] >= _MIN_CONFIDENCE_TO_ACT
        ]
        if len(in_ctx) == 1:
            winner = in_ctx[0]
            return Decision(
                **{**base, "entry_id": winner["entry_id"], "canonical": winner["canonical"]},
                action="apply", reason_tag="applied",
                detail=f"disambiguated by context (matched {winner['canonical']!r} used elsewhere)",
            )
        names = ", ".join(sorted({c.canonical, *[r["canonical"] for r in strong_rivals]}))
        return skip("ambiguous_conflict", f"competing entries: {names}")

    if c.matched_via == "canonical":
        surf = surface_similarity(c.span_text, c.canonical)
        if surf < _MIN_SURFACE_FOR_CANONICAL:
            return skip("weak_surface_match",
                        f"letter similarity {surf:.2f} < {_MIN_SURFACE_FOR_CANONICAL:.2f}; "
                        f"teach an explicit alias if this really is {c.canonical!r}")

    if c.confidence < _MIN_CONFIDENCE_TO_ACT:
        return skip("low_confidence", f"confidence {c.confidence:.2f} < {_MIN_CONFIDENCE_TO_ACT:.2f}")

    if c.combined_score < thr:
        return skip("below_threshold", f"{c.combined_score:.3f} < {thr:.3f}")

    return Decision(**base, action="apply", reason_tag="applied")


def process(asr_text: str, formatted_text: str, persist: bool = True) -> ProcessResult:
    t0 = time.perf_counter()
    candidates = retrieve(formatted_text, asr_text)
    decisions = [_decide(c) for c in candidates]

    sanctioned: list[Replacement] = []
    for d in decisions:
        if d.action != "apply":
            continue
        to_text = _match_case(d.span_text, d.canonical)
        sanctioned.append(Replacement(d.span_text, to_text, d.start, d.end))

    referenced_ids = {d.entry_id for d in decisions}
    glossary = [
        GlossaryItem(
            canonical=e["canonical"], category=e["category"],
            aliases=[a["surface_form"] for a in e["aliases"]], note=e["note"],
        )
        for e in (repo.get_entry(i) for i in referenced_ids) if e
    ]

    rewrite = rewrite_with_glossary(formatted_text, glossary, sanctioned)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    intervened = bool(sanctioned)

    trace = {
        "threshold": settings.apply_threshold,
        "llm_mode": rewrite.mode,
        "llm_calls": rewrite.llm_calls,
        "latency_ms": latency_ms,
        "candidates_found": len(candidates),
        "applied": [asdict(d) for d in decisions if d.action == "apply"],
        "skipped": [asdict(d) for d in decisions if d.action == "skip"],
        "replacements": [asdict(r) for r in rewrite.replacements],
        "reason_legend": REASONS,
    }

    result = ProcessResult(
        asr_text=asr_text, formatted_text=formatted_text,
        memory_aware_text=rewrite.text, intervened=intervened,
        decisions=decisions, trace=trace,
    )

    if persist:
        uid = repo.record_utterance(
            asr_text=asr_text, formatted_text=formatted_text,
            memory_aware_text=rewrite.text, intervened=intervened,
            decision_trace=trace, latency_ms=latency_ms,
            llm_calls=rewrite.llm_calls, llm_mode=rewrite.mode,
        )
        for d in decisions:
            repo.record_intervention(
                utterance_id=uid, entry_id=d.entry_id, span_text=d.span_text,
                from_text=d.span_text,
                to_text=_match_case(d.span_text, d.canonical),
                applied=(d.action == "apply"), score=d.combined_score,
                threshold=d.threshold, reason_tag=d.reason_tag, detail=d.detail,
            )
        result.utterance_id = uid

    return result
