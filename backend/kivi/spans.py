"""Build candidate spans from the formatted text and align them to ASR tokens.

The memory-aware transform operates on FORMATTED-text spans (so punctuation/casing
survive), but carries each span's ASR original as evidence for retrieval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from kivi.normalization import normalize_token

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_SKIP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "is",
    "are", "was", "were", "be", "please", "i", "we", "you", "it", "this", "that",
}


@dataclass
class Span:
    text: str
    start: int
    end: int
    asr_original: str


def _asr_tokens(asr_text: str) -> list[str]:
    return _TOKEN_RE.findall(asr_text or "")


def build_spans(formatted_text: str, asr_text: str) -> list[Span]:
    asr_toks = _asr_tokens(asr_text)
    asr_norms = [normalize_token(t) for t in asr_toks]

    spans: list[Span] = []
    for i, m in enumerate(_TOKEN_RE.finditer(formatted_text)):
        tok = m.group(0)
        norm = normalize_token(tok)
        if not norm or norm in _SKIP or len(norm) <= 2:
            continue
        # align: same normalized token in ASR, preferring the nearest index
        asr_original = tok
        if norm in asr_norms:
            asr_original = asr_toks[asr_norms.index(norm)]
        elif i < len(asr_toks):
            asr_original = asr_toks[i]
        spans.append(Span(text=tok, start=m.start(), end=m.end(), asr_original=asr_original))
    return spans
