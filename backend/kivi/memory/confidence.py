"""Confidence is a pure, re-derivable function of a memory's evidence rows.

Two channels, kept separate on purpose:
  * global confidence  <- strong_positive, weak_positive, rejection, contradiction
  * contextual applicability (NOT here) <- negative_context  (see kivi/context.py)

`negative_context` evidence never enters this computation, so declining to apply a
memory in one context never weakens the memory itself.
"""
from __future__ import annotations

import math

from kivi.config import C as CFG


def compute_confidence(evidence_rows) -> float:
    strong = 0.0
    weak = 0.0
    neg = 0.0
    for e in evidence_rows:
        kind = e["kind"] if not isinstance(e, dict) else e["kind"]
        w = e["weight"] if not isinstance(e, dict) else e["weight"]
        if kind == "strong_positive":
            strong += w
        elif kind == "weak_positive":
            weak += w
        elif kind in ("rejection", "contradiction"):
            neg += abs(w)
        # negative_context is deliberately ignored here

    weak = min(CFG["weak_cap"], weak)
    if strong > 0:
        strong = CFG["strong_cap"] * (1.0 - math.exp(-strong / CFG["strong_cap"]))
    raw = strong + weak - neg
    conf = 1.0 / (1.0 + math.exp(-CFG["k"] * (raw - CFG["offset"])))
    return round(conf, 4)


def apply_authoritative_floor(confidence: float, *, user_authoritative: bool) -> float:
    """An explicit user correction/teach is authoritative - confidence should reflect
    that directly rather than being dragged down by the logistic offset (which is
    calibrated for slowly-accumulated weak evidence)."""
    if user_authoritative:
        return round(max(confidence, CFG.get("authoritative_floor", 0.7)), 4)
    return confidence


def derive_status(current_status: str, confidence: float, *,
                  user_authoritative: bool, contradiction: bool) -> str:
    """proposed | active | contested | inactive."""
    if current_status == "inactive":
        return "inactive"
    if contradiction:
        return "contested"
    if user_authoritative:
        return "active"
    from kivi.config import T
    if confidence >= T["active"]:
        return "active"
    return "proposed"
