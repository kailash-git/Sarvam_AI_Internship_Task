"""Apply REPLACE decisions to the formatted text. KEEP/DEFER never change text."""
from __future__ import annotations


def _match_case(original: str, replacement: str) -> str:
    if original[:1].isupper() and replacement[:1].islower():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_replacements(formatted_text: str, decisions) -> str:
    out = formatted_text
    # right-to-left so earlier char offsets stay valid
    for d in sorted(decisions, key=lambda d: d.span_start, reverse=True):
        if d.action != "REPLACE" or not d.replacement:
            continue
        repl = _match_case(d.span_text, d.replacement)
        out = out[: d.span_start] + repl + out[d.span_end :]
    return out
