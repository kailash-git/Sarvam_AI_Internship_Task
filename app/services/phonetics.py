"""Phonetic keys and phonetic similarity.

The whole system hinges on one question: *does this spoken span sound like a
term the user has taught us?* We answer it with a blend of:

  - Double Metaphone codes (primary + secondary)  -> coarse "sounds like" bucket
  - Soundex                                        -> a second, looser bucket
  - fuzzy ratio over the metaphone codes           -> near-miss phonetic distance
  - fuzzy ratio over the normalised letters        -> guards against metaphone
                                                     collapsing distinct words

Everything is deterministic and offline. No model, no network.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import jellyfish
from metaphone import doublemetaphone
from rapidfuzz.distance import Levenshtein
from rapidfuzz.fuzz import ratio

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")

# Fold letters that ASR and speakers routinely swap before comparing skeletons.
_FOLD = str.maketrans({"w": "v", "k": "c", "z": "s", "y": "i", "q": "c"})


def _phonetic_fold(s: str) -> str:
    return s.translate(_FOLD)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def tokenize(text: str) -> list[str]:
    """Word tokens, punctuation dropped, original casing preserved."""
    return _WORD_RE.findall(text)


@dataclass(frozen=True)
class PhoneticKey:
    primary: str
    secondary: str
    soundex: str

    def buckets(self) -> set[str]:
        return {b for b in (self.primary, self.secondary, self.soundex) if b}


@lru_cache(maxsize=4096)
def phonetic_key(term: str) -> PhoneticKey:
    norm = normalize(term).replace(" ", "")
    if not norm:
        return PhoneticKey("", "", "")
    primary, secondary = doublemetaphone(norm)
    try:
        sx = jellyfish.soundex(norm)
    except Exception:
        sx = ""
    return PhoneticKey(primary or "", secondary or primary or "", sx or "")


def _code_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return ratio(a, b) / 100.0


@lru_cache(maxsize=8192)
def phonetic_similarity(a: str, b: str) -> float:
    """Return a score in [0, 1]. 1.0 means "sounds the same"."""
    na, nb = normalize(a).replace(" ", ""), normalize(b).replace(" ", "")
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    ka, kb = phonetic_key(a), phonetic_key(b)

    exact_primary = ka.primary and ka.primary == kb.primary
    cross_match = bool(ka.buckets() & kb.buckets())

    primary_ratio = _code_ratio(ka.primary, kb.primary)
    secondary_ratio = max(
        _code_ratio(ka.primary, kb.secondary),
        _code_ratio(ka.secondary, kb.primary),
        _code_ratio(ka.secondary, kb.secondary),
    )
    # Letter similarity: the better of raw ratio, prefix-weighted Jaro-Winkler,
    # and a ratio over v/w/k/c-folded skeletons (metaphone drops semivowels like
    # the 'w' in "kiwi", so "kiwi"/"Kivi" needs this path).
    letter_ratio = max(
        ratio(na, nb) / 100.0,
        jellyfish.jaro_winkler_similarity(na, nb),
        ratio(_phonetic_fold(na), _phonetic_fold(nb)) / 100.0,
    )

    # Weighted blend, then nudged up when a metaphone bucket matches exactly.
    score = (
        0.35 * primary_ratio
        + 0.15 * secondary_ratio
        + 0.50 * letter_ratio
    )
    if exact_primary:
        score = max(score, 0.45 + 0.45 * letter_ratio)
    elif cross_match:
        score = max(score, 0.40 + 0.42 * letter_ratio)
    elif letter_ratio >= 0.88:
        score = max(score, letter_ratio)

    # A large raw-letter edit distance vetoes a metaphone/skeleton tie between
    # words that merely rhyme in code space (e.g. "service" vs "surface", which
    # metaphone collapses to the same key). Precision past this point is the
    # decision layer's job (common-word guard, context guard, confidence).
    max_len = max(len(na), len(nb))
    edit = Levenshtein.distance(na, nb)
    if max_len and edit / max_len > 0.5:
        score = min(score, 0.55)

    return round(min(score, 1.0), 4)


@lru_cache(maxsize=8192)
def surface_similarity(a: str, b: str) -> float:
    """Letter-level closeness in [0,1], ignoring phonetic codes. Used to catch
    'the metaphone codes rhyme but the spellings really do not' — e.g. a name in
    memory colliding with an unrelated proper noun ("Colin" vs "Cologne")."""
    na, nb = normalize(a).replace(" ", ""), normalize(b).replace(" ", "")
    if not na or not nb:
        return 0.0
    # Indel ratio on raw letters and on v/w/k/c-folded skeletons. Deliberately
    # NOT Jaro-Winkler: its shared-prefix bonus would rescue "Colin"/"Cologne".
    return round(max(
        ratio(na, nb) / 100.0,
        ratio(_phonetic_fold(na), _phonetic_fold(nb)) / 100.0,
    ), 4)


def ngram_spans(tokens: list[str], max_n: int = 3) -> list[tuple[int, int]]:
    """(start, end) index pairs for every 1..max_n gram, longest first."""
    spans: list[tuple[int, int]] = []
    n_tokens = len(tokens)
    for n in range(min(max_n, n_tokens), 0, -1):
        for i in range(0, n_tokens - n + 1):
            spans.append((i, i + n))
    return spans
