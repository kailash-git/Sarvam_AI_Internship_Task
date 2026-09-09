"""Echo ASR: for typed input. Simulates 'raw ASR' by lowercasing and dropping
terminal punctuation, so LEVEL 1 (raw) visibly differs from LEVEL 2 (formatted)."""
from __future__ import annotations

import re
import time

from kivi.asr.base import AsrResult


class EchoAsr:
    name = "echo"

    def transcribe_text(self, text: str) -> AsrResult:
        t0 = time.perf_counter()
        raw = (text or "").strip().lower()
        raw = re.sub(r"\s+", " ", raw)
        raw = raw.rstrip(".!?;:")
        return AsrResult(
            text=raw, provider=self.name, tokens=raw.split(),
            latency_ms=round((time.perf_counter() - t0) * 1000, 3),
        )

    def transcribe_audio(self, path) -> AsrResult:  # pragma: no cover
        raise RuntimeError(
            "Echo ASR cannot transcribe audio. Set asr_provider to 'whisper' (local) "
            "or 'fixture', or use text input."
        )
