"""Grammar-based homophone disambiguation.  Rule-based, stdlib, deterministic.

Surface match cannot tell `see` from `sea` - they share the alias.  The
keyword-context lists don't cover them, and a small embedding model is too weak
on 2-4 word utterances.  But the **grammatical slot** the word sits in is a
near-perfect tell:

    I  see  you            pronoun before + object after   -> verb    -> "see"
    let me see that         "let" ... + object after         -> verb    -> "see"
    the sea is huge         determiner before + "is" after   -> noun    -> "sea"
    waves crash on the sea  preposition + determiner before  -> noun    -> "sea"
    going to sea            "to" + end of clause             -> noun    -> "sea"

`role_of(sentence, span)` returns "noun" / "verb" / "unknown" from the function
words immediately around the span.  A memory whose canonical AND matched alias
are both ordinary English words (`data/common_words.json`) is treated as a
homophone pair: only grammar (or strong keyword/semantic context) may drive a
REPLACE - surface match and personal history alone cannot.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "common_words.json"

_DETERMINERS = {
    "the", "a", "an", "this", "that", "these", "those", "my", "your", "his", "her",
    "its", "our", "their", "no", "every", "some", "any", "another", "each", "which",
}
_PREPS = {
    "of", "in", "on", "at", "by", "for", "with", "from", "into", "onto", "near",
    "across", "over", "under", "upon", "toward", "towards", "beside", "between", "about",
}
_SUBJ_PRON = {"i", "you", "we", "they", "he", "she"}
_OBJ_PRON = {"me", "him", "her", "them", "us", "you", "it"}
_MODALS = {
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "do", "does", "did", "cannot", "wont", "dont", "doesnt", "didnt", "please",
}
_BE = {"is", "was", "are", "were", "am", "be", "been", "being"}
_POST_VERB_ADV = {
    "clearly", "again", "now", "around", "away", "ahead", "soon", "through", "off",
    "out", "back", "along", "over",
}

_WORD_RE = re.compile(r"[a-z0-9']+")


@lru_cache(maxsize=1)
def _data() -> tuple[frozenset, dict]:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    common = frozenset(w.lower() for w in raw.get("common", []))
    pos = {k.lower(): v for k, v in raw.get("pos", {}).items()}
    return common, pos


def is_common_word(word: str) -> bool:
    return word.strip().lower() in _data()[0]


def word_pos(word: str) -> str | None:
    """Dominant part of speech for a homophone-prone word, or None."""
    return _data()[1].get(word.strip().lower())


def homophone_roles(canonical: str, alias: str) -> tuple[str, str] | None:
    """If (canonical, alias) look like a common-word homophone pair, return
    (canonical_role, alias_role); else None.  Roles collapse to 'noun' / 'verb'
    / 'other' for matching against `role_of`."""
    c, a = canonical.strip().lower(), alias.strip().lower()
    if c == a:
        return None
    if not (is_common_word(c) and is_common_word(a)):
        return None
    cr = _collapse(word_pos(c))
    ar = _collapse(word_pos(a))
    if cr == "other" and ar == "other":
        return None
    return cr, ar


def _collapse(pos: str | None) -> str:
    if pos in ("verb", "modal"):
        return "verb"
    if pos in ("noun", "numeral"):
        return "noun"
    if pos in ("adjective",):
        return "adjective"
    if pos in ("adverb", "determiner", "preposition", "conjunction", "contraction",
               "interjection"):
        return pos
    return "other"


def _tokens_with_span(text: str, span: str, span_start: int | None):
    toks = [(m.group(0), m.start()) for m in _WORD_RE.finditer((text or "").lower())]
    target = (span or "").strip().lower()
    idx = -1
    if span_start is not None:
        best = None
        for i, (_, off) in enumerate(toks):
            d = abs(off - span_start)
            if best is None or d < best[0]:
                best, idx = (d, i), i
    if idx < 0 or (target and toks and toks[idx][0] != target):
        for i, (w, _) in enumerate(toks):
            if w == target:
                idx = i
                break
    return [w for w, _ in toks], idx


def role_of(sentence: str, span: str, span_start: int | None = None) -> str:
    """'noun' / 'verb' / 'unknown' for the span's grammatical slot."""
    toks, idx = _tokens_with_span(sentence, span, span_start)
    if idx < 0:
        return "unknown"
    prev = toks[idx - 1] if idx > 0 else ""
    prev2 = toks[idx - 2] if idx > 1 else ""
    nxt = toks[idx + 1] if idx + 1 < len(toks) else ""
    nxt2 = toks[idx + 2] if idx + 2 < len(toks) else ""

    noun = verb = 0

    if prev in _DETERMINERS:
        noun += 2
    if prev in _PREPS:
        noun += 2
    if prev == "to":
        # infinitive "to see you" vs place "go to sea"
        if nxt in _OBJ_PRON or nxt in _DETERMINERS or nxt in _POST_VERB_ADV:
            verb += 1
        elif nxt == "":
            noun += 2
        else:
            noun += 1
    if prev in _SUBJ_PRON:
        verb += 2
    if prev in _MODALS:
        verb += 2
    if prev == "let" or prev2 == "let":
        verb += 2
    if prev2 in _SUBJ_PRON and prev in _POST_VERB_ADV:
        verb += 1
    if prev in ("to", "and", "or", "") and prev2 in _SUBJ_PRON:
        verb += 1  # "I want to see", "you and see" (rare)

    if nxt in _BE:
        noun += 2                     # "sea is blue", "sea was calm"
    if nxt in _OBJ_PRON:
        verb += 2                     # "see you", "see me"
    if nxt in _DETERMINERS:
        verb += 1                     # "see the screen", "see a doctor"
    if nxt in _POST_VERB_ADV:
        verb += 1                     # "see clearly", "see around"
    if nxt == "" and prev in _SUBJ_PRON:
        verb += 1                     # "you see."
    if nxt in _PREPS and nxt not in ("of",) and prev in _DETERMINERS:
        noun += 1                     # "the sea near the coast"
    if nxt == "in" and nxt2 in ("colour", "color"):
        noun += 2                     # "... is <x> in colour"

    if noun > verb:
        return "noun"
    if verb > noun:
        return "verb"

    # Determiner slot: [X] + CONTENT-WORD, with nothing before it that wants a
    # verb. "no one came", "no idea", "their house" -> X is a determiner, not a
    # verb. Only claimed when no noun/verb evidence was found at all.
    if nxt and nxt not in _FUNCTION_WORDS and prev not in _SUBJ_PRON \
            and prev not in _MODALS and prev != "to":
        return "determiner"
    return "unknown"


# Everything that cannot head a noun phrase - used to spot a determiner slot.
_FUNCTION_WORDS = (_DETERMINERS | _PREPS | _SUBJ_PRON | _OBJ_PRON | _MODALS | _BE
                   | _POST_VERB_ADV | {"to", "and", "or", "but", "not", "no", "if",
                                       "that", "than", "as", "so", "very", "just"})


def is_function_word(word: str) -> bool:
    """A word whose job is grammatical (determiner, preposition, pronoun, ...).
    Blanket-replacing one of these because it was corrected once is destructive,
    so the decision engine requires real grammatical evidence for them."""
    w = (word or "").strip().lower()
    if w in _FUNCTION_WORDS:
        return True
    return word_pos(w) in ("determiner", "preposition", "conjunction", "adverb",
                           "numeral", "contraction", "modal", "interjection")


def assess_homophone(canonical: str, alias: str, sentence: str, span: str,
                     span_start: int | None = None) -> dict | None:
    """Verdict for a homophone candidate, or None if it isn't one.

    { 'is_homophone': True,
      'role': 'noun'|'verb'|'unknown',        # grammatical slot of the span
      'canonical_role': ...,                   # what the canonical wants
      'verdict': 'favors_canonical' | 'favors_alias' | 'unclear',
      'note': '<plain english>' }
    """
    roles = homophone_roles(canonical, alias)
    if roles is None:
        return None
    canonical_role, alias_role = roles
    role = role_of(sentence, span, span_start)

    # Same part of speech on both sides (son/sun, flour/flower, peace/piece):
    # the grammatical slot carries NO signal - it can't confirm one over the
    # other. Hand off to context/semantics; never claim 'favors_canonical'.
    if canonical_role == alias_role:
        return {"is_homophone": True, "role": role, "canonical_role": canonical_role,
                "alias_is_function_word": is_function_word(alias),
                "verdict": "unclear",
                "note": (f"Grammar: '{canonical}' and '{alias}' are both {canonical_role}s - "
                         f"the sentence structure can't tell them apart here.")}

    if role != "unknown" and role == canonical_role:
        verdict = "favors_canonical"
        note = (f"Grammar: '{span}' is in a {role} slot here, which is '{canonical}' "
                f"(not '{alias}').")
    elif role != "unknown" and role == alias_role:
        verdict = "favors_alias"
        note = (f"Grammar: '{span}' is in a {role} slot here, which is '{alias}'. "
                f"'{canonical}' left as written.")
    elif role != "unknown" and canonical_role in ("noun", "verb") and role != canonical_role:
        verdict = "favors_alias"
        note = (f"Grammar: '{span}' is in a {role} slot here, not the {canonical_role} "
                f"slot '{canonical}' needs. Left as written.")
    else:
        verdict = "unclear"
        note = (f"Grammar: '{span}' could be '{canonical}' or '{alias}' here "
                f"(no clear syntactic signal). Left as written.")
    return {"is_homophone": True, "role": role, "canonical_role": canonical_role,
            "alias_is_function_word": is_function_word(alias),
            "verdict": verdict, "note": note}
