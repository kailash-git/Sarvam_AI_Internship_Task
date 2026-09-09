"""Rule-based formatter: punctuation, capitalization, filler removal, dedupe.
Deliberately GENERIC - it must not capitalize or rewrite personal entities."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

_FILLERS = {"um", "uh", "erm", "uhh", "mm", "mmm", "hmm", "ah", "er"}
_QUESTION_STARTS = {
    "what", "why", "how", "when", "where", "who", "which", "whose",
    "is", "are", "do", "does", "did", "can", "could", "would", "should", "will",
}
_GENERIC_CAPS = {
    "i": "I", "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
    "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday", "sunday": "Sunday",
    "january": "January", "february": "February", "march": "March", "april": "April",
    "may": "May", "june": "June", "july": "July", "august": "August",
    "september": "September", "october": "October", "november": "November",
    "december": "December", "iphone": "iPhone",
}


@dataclass
class FormatResult:
    text: str
    provider: str = "rules"
    latency_ms: float = 0.0
    model_calls: int = 0
    est_cost_usd: float = 0.0


class RulesFormatter:
    name = "rules"

    def format(self, raw: str) -> FormatResult:
        t0 = time.perf_counter()
        text = re.sub(r"\s+", " ", (raw or "").strip())

        # split into rough sentences on existing terminal punctuation
        chunks = re.split(r"(?<=[.!?])\s+", text) if text else []
        if not chunks:
            chunks = [text]

        out_sentences = []
        for chunk in chunks:
            words = [w for w in chunk.split(" ") if w]
            words = [w for w in words if w.strip(".,!?").lower() not in _FILLERS]
            # collapse immediate duplicates ("the the")
            deduped = []
            for w in words:
                if deduped and w.lower().strip(".,!?") == deduped[-1].lower().strip(".,!?"):
                    continue
                deduped.append(w)
            words = deduped
            if not words:
                continue
            words = [_GENERIC_CAPS.get(w.lower(), w) for w in words]
            sentence = " ".join(words)
            sentence = sentence[:1].upper() + sentence[1:]
            first = re.sub(r"[^a-z]", "", words[0].lower())
            if not re.search(r"[.!?]$", sentence):
                sentence += "?" if first in _QUESTION_STARTS else "."
            out_sentences.append(sentence)

        formatted = " ".join(out_sentences) if out_sentences else text
        return FormatResult(
            text=formatted, provider=self.name,
            latency_ms=round((time.perf_counter() - t0) * 1000, 3),
        )
