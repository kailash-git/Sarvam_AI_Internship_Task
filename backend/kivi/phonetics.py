"""Lightweight, deterministic phonetic key (stdlib only).

This is intentionally simple for the prototype. It collapses vowels and maps
consonant classes so that ASR confusions like kiwi/Kivi/kivy/civi share a key.
The roadmap's production choice is Double Metaphone; the interface here
(`phonetic_key`) is a drop-in replacement point.
"""
from __future__ import annotations

import re

_VOWELS = set("aeiou")

# Consonant classes: characters that ASR / accents frequently swap map to the same code.
_CLASS = {
    "b": "B", "p": "B", "f": "B", "v": "B", "w": "B",   # labials (v/w/b confusion)
    "c": "K", "g": "K", "j": "K", "k": "K", "q": "K", "s": "K", "x": "K", "z": "K",
    "d": "T", "t": "T",
    "l": "L",
    "m": "M", "n": "M",
    "r": "R",
}


def phonetic_key(word: str) -> str:
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w:
        return ""
    out: list[str] = []
    # leading vowel is significant; leading consonant goes through the class map
    if w[0] in _VOWELS:
        out.append("A")
    else:
        out.append(_CLASS.get(w[0], w[0].upper()))
    for ch in w[1:]:
        if ch in _VOWELS:
            continue
        code = _CLASS.get(ch, "")
        if code and (not out or out[-1] != code):
            out.append(code)
    return "".join(out)
