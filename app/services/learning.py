"""Turn observations into memory state.

Evidence the product learns from (deliberately only these):

  correction   the user edited a formatted transcript. The formatted->edited
               diff yields (wrong form -> right form) pairs. One correction
               creates a *candidate*; ``KIVI_PROMOTE_AFTER`` corroborating
               corrections promote it to *active*.

  dictionary   the user explicitly added a word. Trusted immediately: *active*.

  rejection    the user undid an intervention Kivi made. ``KIVI_SUPPRESS_AFTER``
               rejections *suppress* the entry (kept, never applied).

  acceptance   the user kept an intervention. Small positive reinforcement.

Everything else (free typing elsewhere, telemetry, guessing from context) is out
of scope by design - the brief asks for the smallest system that works.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from app.config import settings
from app.services import repo
from app.services.phonetics import tokenize

_CANDIDATE_CONF = 0.35
_SUPPRESSED_CONF = 0.10
_DICT_CONF = 0.90


@dataclass
class LearnedChange:
    entry_id: int
    canonical: str
    category: str
    from_form: str
    status: str
    confidence: float
    promoted: bool


@dataclass
class LearnResult:
    changes: list[LearnedChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- helpers

def diff_pairs(before: str, after: str) -> list[tuple[str, str]]:
    """(before_phrase, after_phrase) for every substituted region."""
    b, a = tokenize(before), tokenize(after)
    pairs: list[tuple[str, str]] = []
    sm = difflib.SequenceMatcher(a=b, b=a, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace":
            pairs.append((" ".join(b[i1:i2]), " ".join(a[j1:j2])))
        elif op == "delete":
            pairs.append((" ".join(b[i1:i2]), ""))
        elif op == "insert":
            pairs.append(("", " ".join(a[j1:j2])))
    return [(x, y) for x, y in pairs if x != y]


def _confidence_for(entry_id: int) -> float:
    corr = repo.count_observations(entry_id, "correction")
    dic = repo.count_observations(entry_id, "dictionary")
    rej = repo.count_observations(entry_id, "rejection")
    if rej >= settings.suppress_after:
        return _SUPPRESSED_CONF
    if dic:
        return max(_DICT_CONF, min(0.97, 0.90 + 0.02 * corr))
    if corr >= settings.promote_after:
        return min(0.95, 0.60 + 0.12 * (corr - settings.promote_after))
    return _CANDIDATE_CONF


def _status_for(entry_id: int) -> str:
    corr = repo.count_observations(entry_id, "correction")
    dic = repo.count_observations(entry_id, "dictionary")
    rej = repo.count_observations(entry_id, "rejection")
    if rej >= settings.suppress_after:
        return "suppressed"
    if dic or corr >= settings.promote_after:
        return "active"
    return "candidate"


def _resync(entry_id: int) -> tuple[str, float]:
    status, conf = _status_for(entry_id), _confidence_for(entry_id)
    repo.update_entry(entry_id, status=status, confidence=round(conf, 3))
    return status, conf


# ------------------------------------------------------------------ public API

def learn_from_correction(
    *,
    asr_text: str = "",
    formatted_text: str,
    corrected_text: str,
    category: str = "other",
    note: str = "",
) -> LearnResult:
    result = LearnResult()
    if category not in repo.CATEGORIES:
        category = "other"

    pairs = diff_pairs(formatted_text, corrected_text)
    if not pairs:
        result.notes.append("no token-level change between formatted and corrected text")
        return result

    asr_tokens = tokenize(asr_text)

    for from_form, to_form in pairs:
        if not to_form:
            result.notes.append(f"skipped deletion-only change ({from_form!r} -> removed)")
            continue

        entry = repo.find_entry(to_form, category)
        before_status = entry["status"] if entry else None
        if entry is None:
            entry = repo.create_entry(
                canonical=to_form, category=category, source="correction",
                status="candidate", confidence=_CANDIDATE_CONF, note=note,
            )

        if from_form and from_form.lower() != to_form.lower():
            repo.add_alias(entry["id"], from_form)
        # The raw ASR often carries an even rougher form of the same word.
        for tok in asr_tokens:
            if tok.lower() != to_form.lower() and _looks_related(tok, to_form):
                repo.add_alias(entry["id"], tok)

        repo.add_observation(
            "correction",
            asr_text=asr_text, formatted_text=formatted_text,
            corrected_text=corrected_text, from_form=from_form, to_form=to_form,
            category=category, entry_id=entry["id"],
        )
        status, conf = _resync(entry["id"])
        result.changes.append(
            LearnedChange(
                entry_id=entry["id"], canonical=to_form, category=category,
                from_form=from_form, status=status, confidence=round(conf, 3),
                promoted=(before_status != "active" and status == "active"),
            )
        )
    return result


def learn_from_dictionary(
    *, canonical: str, category: str = "other",
    aliases: list[str] | None = None, note: str = "",
) -> LearnResult:
    result = LearnResult()
    if category not in repo.CATEGORIES:
        category = "other"
    entry = repo.find_entry(canonical, category) or repo.create_entry(
        canonical=canonical, category=category, source="dictionary",
        status="active", confidence=_DICT_CONF, note=note,
    )
    for alias in aliases or []:
        if alias.strip():
            repo.add_alias(entry["id"], alias.strip())
    repo.add_observation(
        "dictionary", corrected_text=canonical, to_form=canonical,
        category=category, entry_id=entry["id"],
        raw_payload={"aliases": aliases or [], "note": note},
    )
    status, conf = _resync(entry["id"])
    result.changes.append(
        LearnedChange(
            entry_id=entry["id"], canonical=canonical, category=category,
            from_form="", status=status, confidence=round(conf, 3),
            promoted=(status == "active"),
        )
    )
    return result


def learn_from_rejection(*, entry_id: int, note: str = "") -> LearnResult:
    result = LearnResult()
    entry = repo.get_entry(entry_id)
    if not entry:
        result.notes.append(f"no entry {entry_id}")
        return result
    repo.add_observation(
        "rejection", entry_id=entry_id, to_form=entry["canonical"],
        category=entry["category"], raw_payload={"note": note},
    )
    status, conf = _resync(entry_id)
    result.changes.append(
        LearnedChange(
            entry_id=entry_id, canonical=entry["canonical"],
            category=entry["category"], from_form="", status=status,
            confidence=round(conf, 3), promoted=False,
        )
    )
    if status == "suppressed":
        result.notes.append(f"entry {entry_id} ({entry['canonical']!r}) suppressed after repeated rejections")
    return result


def learn_from_acceptance(*, entry_id: int) -> LearnResult:
    result = LearnResult()
    entry = repo.get_entry(entry_id)
    if not entry:
        result.notes.append(f"no entry {entry_id}")
        return result
    repo.add_observation(
        "acceptance", entry_id=entry_id, to_form=entry["canonical"],
        category=entry["category"],
    )
    new_conf = min(0.98, entry["confidence"] + 0.02)
    repo.update_entry(entry_id, confidence=round(new_conf, 3))
    result.changes.append(
        LearnedChange(
            entry_id=entry_id, canonical=entry["canonical"],
            category=entry["category"], from_form="", status=entry["status"],
            confidence=round(new_conf, 3), promoted=False,
        )
    )
    return result


def _looks_related(a: str, b: str) -> bool:
    from app.services.phonetics import phonetic_similarity

    return phonetic_similarity(a, b) >= 0.6
