"""Find the memory entries that might apply to an utterance.

Given the formatted transcript, walk every 1..3-token span and score it against
every memory entry's canonical form and known aliases with the phonetic
similarity metric. A span is only compared against a form of *similar length*
(+/- one token), so a one-word canonical like "Sarvam" never matches the
two-word span "Sarvam Kiwi". Overlapping survivors are resolved in favour of the
*tightest strongest* match (higher phonetic score, then shorter span). This
layer is pure recall + scoring; whether to act is decided in ``pipeline.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import repo
from app.services.common_words import is_common
from app.services.phonetics import ngram_spans, phonetic_similarity, tokenize

# Below this phonetic similarity a span/entry pair is not even a candidate.
MATCH_FLOOR = 0.66

_CATEGORY_PRIOR = {"person": 0.05, "product": 0.04, "org": 0.03, "term": 0.0, "other": 0.0}


@dataclass
class Candidate:
    entry_id: int
    canonical: str
    category: str
    status: str
    confidence: float
    span_text: str
    start: int
    end: int
    matched_form: str          # the alias or canonical that matched
    matched_via: str           # "alias" | "canonical"
    phonetic_score: float
    combined_score: float
    span_is_common_word: bool
    already_canonical: bool
    context_tokens: list[str] = field(default_factory=list)
    rivals: list[dict] = field(default_factory=list)   # dropped matches on the same span

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _token_offsets(text: str) -> list[tuple[str, int, int]]:
    offsets, i = [], 0
    for tok in tokenize(text):
        idx = text.find(tok, i)
        offsets.append((tok, idx, idx + len(tok)))
        i = idx + len(tok)
    return offsets


def _comparison_forms(entry: dict) -> list[tuple[str, str, int]]:
    """(form_text, via, token_count) for the canonical and every alias."""
    forms = [(entry["canonical"], "canonical", len(entry["canonical"].split()))]
    for alias in entry.get("aliases", []):
        forms.append((alias["surface_form"], "alias", len(alias["surface_form"].split())))
    return forms


def retrieve(formatted_text: str, asr_text: str = "", max_n: int = 3) -> list[Candidate]:
    entries = [
        e for e in repo.list_entries()
        if e["status"] in ("active", "candidate", "suppressed")
    ]
    if not entries:
        return []

    tokens = _token_offsets(formatted_text)
    words = [t[0] for t in tokens]
    lower_ctx = [w.lower() for w in words]

    raw: list[Candidate] = []
    for i, j in ngram_spans(words, max_n):
        span_len = j - i
        span_text = " ".join(words[i:j])
        start, end = tokens[i][1], tokens[j - 1][2]
        span_common = span_len == 1 and is_common(span_text)

        for entry in entries:
            best_phon, best_form, best_via = 0.0, "", ""
            for form_text, via, form_len in _comparison_forms(entry):
                if form_len != span_len:
                    continue
                s = phonetic_similarity(span_text, form_text)
                if s > best_phon:
                    best_phon, best_form, best_via = s, form_text, via
            if best_phon < MATCH_FLOOR:
                continue

            already = span_text == entry["canonical"]   # exact; casing counts
            conf = entry["confidence"]
            combined = (
                0.62 * best_phon
                + 0.28 * conf
                + _CATEGORY_PRIOR.get(entry["category"], 0.0)
            )
            if best_via == "alias" and best_phon >= 0.9:
                combined += 0.06
            if span_common and not (best_via == "alias" and best_phon >= 0.95):
                combined -= 0.15
            if span_len > 1:
                combined += 0.02
            combined = round(max(0.0, min(1.0, combined)), 4)

            raw.append(
                Candidate(
                    entry_id=entry["id"], canonical=entry["canonical"],
                    category=entry["category"], status=entry["status"],
                    confidence=conf, span_text=span_text, start=start, end=end,
                    matched_form=best_form, matched_via=best_via,
                    phonetic_score=round(best_phon, 4), combined_score=combined,
                    span_is_common_word=span_common, already_canonical=already,
                    context_tokens=[w for k, w in enumerate(lower_ctx)
                                    if k < i or k >= j],
                )
            )

    return _resolve_overlaps(raw)


def _resolve_overlaps(cands: list[Candidate]) -> list[Candidate]:
    """Keep the tightest strongest candidate per character region. A dropped
    match on an overlapping span that targets a *different* entry is attached to
    the winner as a ``rival`` so the decision layer can spot a real phonetic
    ambiguity (e.g. "Jon" vs "John")."""
    ordered = sorted(
        cands,
        key=lambda c: (c.phonetic_score, c.combined_score, -(c.end - c.start)),
        reverse=True,
    )
    kept: list[Candidate] = []
    for c in ordered:
        overlap = next(
            (k for k in kept if not (c.end <= k.start or c.start >= k.end)), None
        )
        if overlap is None:
            kept.append(c)
        elif c.entry_id != overlap.entry_id and c.phonetic_score >= MATCH_FLOOR:
            overlap.rivals.append({
                "entry_id": c.entry_id, "canonical": c.canonical,
                "category": c.category, "status": c.status,
                "confidence": c.confidence,
                "phonetic_score": c.phonetic_score,
                "combined_score": c.combined_score,
            })
    return sorted(kept, key=lambda c: c.start)
