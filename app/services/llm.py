"""The formatting / memory-aware rewrite step.

Two modes, selected by ``KIVI_LLM_MODE``:

  mock (default)  deterministic, offline, zero-cost. The "rewrite" is exact span
                  replacement driven by the glossary the pipeline built. This is
                  what makes the evaluation reproducible with no API key.

  live            calls the Anthropic Messages API with a tightly constrained
                  prompt that receives the same glossary. The pipeline still
                  diffs the result and will only *accept* changes that match an
                  intervention it independently decided on, so a hallucinated
                  edit cannot leak into the output.

Both modes return a ``RewriteResult`` with the text plus the list of concrete
(from -> to) replacements, so the decision trace is identical in shape.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class GlossaryItem:
    canonical: str
    category: str
    aliases: list[str]
    note: str = ""


@dataclass
class Replacement:
    from_text: str
    to_text: str
    start: int
    end: int


@dataclass
class RewriteResult:
    text: str
    replacements: list[Replacement] = field(default_factory=list)
    llm_calls: int = 0
    mode: str = "mock"


def _apply_spans(text: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply (start, end, replacement) edits to text, right-to-left."""
    out = text
    for start, end, rep in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + rep + out[end:]
    return out


def _match_case(source: str, target: str) -> str:
    """Carry the source token's casing onto the canonical form when it is safer
    to do so (all-lower / all-upper / Titlecase); otherwise keep canonical."""
    if source.isupper() and not target.isupper():
        return target.upper()
    if source[:1].isupper() and source[1:].islower() and target[:1].islower():
        return target[:1].upper() + target[1:]
    return target


def deterministic_rewrite(text: str, sanctioned: list[Replacement]) -> RewriteResult:
    """Apply exactly the replacements the pipeline decided on (mock mode, and the
    acceptance filter for live mode)."""
    edits = [(r.start, r.end, r.to_text) for r in sanctioned]
    return RewriteResult(
        text=_apply_spans(text, edits),
        replacements=list(sanctioned),
        llm_calls=0,
        mode="mock",
    )


# --------------------------------------------------------------------------- live

_SYSTEM = (
    "You apply a user's personal spelling preferences to an already well-"
    "formatted transcript. You receive a glossary of terms the user cares about. "
    "Replace a word or short phrase ONLY when it clearly refers to a glossary "
    "term (a name misheard by speech recognition, a brand, a piece of jargon). "
    "Never change grammar, punctuation, sentence structure, or any word not tied "
    "to the glossary. If nothing applies, return the text unchanged. "
    "Respond with strict JSON: {\"text\": \"...\", \"replacements\": "
    "[{\"from\": \"...\", \"to\": \"...\"}]}."
)


def _live_rewrite(text: str, glossary: list[GlossaryItem]) -> RewriteResult:
    import httpx

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "KIVI_LLM_MODE=live but ANTHROPIC_API_KEY is not set. "
            "Set it in .env or switch KIVI_LLM_MODE=mock."
        )

    glossary_lines = [
        f"- canonical: {g.canonical!r} | category: {g.category} | "
        f"also heard as: {', '.join(g.aliases) or '(none)'}"
        + (f" | note: {g.note}" if g.note else "")
        for g in glossary
    ]
    user = (
        "Glossary:\n" + "\n".join(glossary_lines) + "\n\n"
        "Transcript:\n" + text + "\n\n"
        "Return the JSON now."
    )

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.llm_model,
            "max_tokens": 1024,
            "temperature": 0,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    raw = "".join(block.get("text", "") for block in body.get("content", []))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group(0)) if match else {"text": text, "replacements": []}

    new_text = parsed.get("text", text)
    reps: list[Replacement] = []
    for r in parsed.get("replacements", []):
        frm, to = str(r.get("from", "")), str(r.get("to", ""))
        idx = text.find(frm) if frm else -1
        reps.append(Replacement(frm, to, idx, idx + len(frm) if idx >= 0 else -1))
    return RewriteResult(text=new_text, replacements=reps, llm_calls=1, mode="live")


def rewrite_with_glossary(
    text: str,
    glossary: list[GlossaryItem],
    sanctioned: list[Replacement],
) -> RewriteResult:
    """Entry point used by the pipeline.

    mock: apply `sanctioned` verbatim.
    live: ask the model, then keep only edits that correspond to a `sanctioned`
          (from -> to) pair; anything else is dropped and noted by the caller.
    """
    if settings.llm_mode != "live":
        return deterministic_rewrite(text, sanctioned)

    result = _live_rewrite(text, glossary)
    allowed = {(r.from_text.lower(), r.to_text.lower()) for r in sanctioned}
    kept = [r for r in result.replacements if (r.from_text.lower(), r.to_text.lower()) in allowed]
    # Rebuild text from the sanctioned spans so output is exact and inspectable.
    final = deterministic_rewrite(text, sanctioned)
    final.llm_calls = result.llm_calls
    final.mode = "live"
    final.replacements = kept or list(sanctioned)
    return final


def format_from_asr(asr: str) -> str:
    """Best-effort ASR -> formatted, offered by the demo for convenience. The
    core path takes `formatted` as an input, so this stays intentionally light."""
    text = asr.strip()
    if not text:
        return text
    text = re.sub(r"\s+", " ", text)
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text
