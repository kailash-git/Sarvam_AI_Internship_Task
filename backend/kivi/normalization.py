"""Deterministic text normalisation. No ML."""
from __future__ import annotations

import re
import unicodedata

_STOPWORDS = {
    "a", "an", "the", "this", "that", "these", "those", "is", "are", "was", "were",
    "be", "been", "being", "to", "of", "in", "on", "at", "for", "and", "or", "but",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your", "our", "their",
    "please", "just", "then", "so", "with", "from", "as", "by", "into", "about",
    "today", "tomorrow", "yesterday", "now", "here", "there",
}

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def normalize(text: str) -> str:
    """casefold + NFKC + strip surrounding punctuation + collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.casefold()
    text = re.sub(r"[^\w\s'-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_token(token: str) -> str:
    token = unicodedata.normalize("NFKC", token or "").casefold()
    token = re.sub(r"[^a-z0-9']", "", token)
    return token


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(normalize(text))


def content_tokens(text: str) -> list[str]:
    """Tokens with stopwords removed - used for context matching."""
    return [t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 1]
