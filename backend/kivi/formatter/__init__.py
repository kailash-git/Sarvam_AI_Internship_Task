"""Formatter adapters. Converts raw ASR text -> generic formatted transcript.
Knows nothing personal; personal memory is injected downstream (LEVEL 3)."""
from __future__ import annotations

from kivi.config import FORMATTER_MODE
from kivi.formatter.rules import RulesFormatter


def get_formatter(mode: str | None = None):
    name = (mode or FORMATTER_MODE or "rules").lower()
    if name == "rules":
        return RulesFormatter()
    raise RuntimeError(f"Unknown formatter mode: {name}")
