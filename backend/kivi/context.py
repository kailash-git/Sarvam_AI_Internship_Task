"""Rule-based context / entity understanding. No ML.

Produces, per (utterance, candidate memory):
  s_ctx_pos  - how well the utterance matches where this memory DOES apply
  s_ctx_neg  - how well it matches where this memory must NOT apply
  s_ctx      - s_ctx_pos - s_ctx_neg   (clipped to [-1, 1])
"""
from __future__ import annotations

from kivi.normalization import content_tokens
from kivi.db.store import load_json

# Coarse domain lexicons. Small and hand-built on purpose.
_DOMAIN_KEYWORDS = {
    "software": {
        "open", "close", "service", "deploy", "deployment", "app", "application", "build",
        "backend", "frontend", "server", "api", "run", "start", "restart", "stop", "code",
        "prod", "production", "staging", "database", "db", "login", "logout", "process",
        "endpoint", "repo", "commit", "branch", "release", "pipeline", "cluster", "container",
        "dashboard", "console", "module", "package", "script", "config",
    },
    "food": {
        "ate", "eat", "eating", "eaten", "fruit", "juice", "salad", "tree", "grocery",
        "groceries", "breakfast", "lunch", "dinner", "snack", "tasty", "delicious", "peel",
        "seeds", "ripe", "sweet", "sour", "kitchen", "recipe", "meal", "cut", "slice",
    },
    "people": {
        "said", "told", "asked", "meeting", "colleague", "teammate", "call", "review",
        "sync", "spoke", "talked", "mentioned", "emailed", "messaged", "manager", "lead",
    },
}


def guess_domain(tokens: list[str]) -> str:
    scores = {d: sum(1 for t in tokens if t in kw) for d, kw in _DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def utterance_context(text: str, exclude: str = "") -> dict:
    ex = exclude.casefold().strip()
    toks = [t for t in content_tokens(text) if t != ex]
    return {"keywords": toks, "domain": guess_domain(toks)}


def _overlap_score(utter_kw: list[str], mem_kw: list[str], domain_match: bool) -> float:
    hits = sum(1 for t in set(utter_kw) if t in set(mem_kw))
    score = min(0.8, 0.35 * hits)
    if domain_match:
        score = min(1.0, score + 0.3)
    return round(score, 4)


def assess(memory_row, ctx: dict) -> dict:
    pos = load_json(memory_row["positive_contexts"], {"keywords": [], "domains": []})
    neg = load_json(memory_row["negative_contexts"], {"keywords": [], "domains": []})

    s_pos = _overlap_score(
        ctx["keywords"], pos.get("keywords", []),
        ctx["domain"] in pos.get("domains", []) and ctx["domain"] != "general",
    )
    s_neg = _overlap_score(
        ctx["keywords"], neg.get("keywords", []),
        ctx["domain"] in neg.get("domains", []) and ctx["domain"] != "general",
    )
    s_ctx = max(-1.0, min(1.0, s_pos - s_neg))
    return {"s_ctx_pos": s_pos, "s_ctx_neg": s_neg, "s_ctx": round(s_ctx, 4)}
