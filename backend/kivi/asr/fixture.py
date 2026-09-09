"""Fixture ASR: maps an audio file (by name or sha1) to a stored transcript.
Deterministic and offline - used by the evaluation harness and demos without a real ASR.
"""
from __future__ import annotations

import hashlib
import json
import time

from kivi.config import ROOT
from kivi.asr.base import AsrResult

_MANIFEST = ROOT / "evaluation" / "fixtures" / "manifest.json"


class FixtureAsr:
    name = "fixture"

    def _manifest(self) -> dict:
        if _MANIFEST.exists():
            return json.loads(_MANIFEST.read_text(encoding="utf-8"))
        return {}

    def transcribe_text(self, text: str) -> AsrResult:
        # allow fixture provider to still handle typed input gracefully
        from kivi.asr.echo import EchoAsr
        return EchoAsr().transcribe_text(text)

    def transcribe_audio(self, path) -> AsrResult:
        t0 = time.perf_counter()
        path = str(path)
        man = self._manifest()
        key = path.replace("\\", "/").split("/")[-1]
        transcript = man.get(key)
        if transcript is None:
            digest = hashlib.sha1(open(path, "rb").read()).hexdigest()
            transcript = man.get(digest)
        if transcript is None:
            raise RuntimeError(f"No fixture transcript for '{key}'. Add it to {_MANIFEST}.")
        return AsrResult(
            text=transcript, provider=self.name, tokens=transcript.split(),
            latency_ms=round((time.perf_counter() - t0) * 1000, 3),
        )
