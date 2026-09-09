"""ASR adapters. Swappable via config.asr_provider."""
from __future__ import annotations

from kivi.config import ASR_PROVIDER
from kivi.asr.base import AsrResult
from kivi.asr.echo import EchoAsr
from kivi.asr.fixture import FixtureAsr


def get_asr(provider: str | None = None):
    name = (provider or ASR_PROVIDER or "echo").lower()
    if name == "echo":
        return EchoAsr()
    if name == "fixture":
        return FixtureAsr()
    if name == "whisper":
        try:
            from kivi.asr.whisper_asr import WhisperAsr  # optional, heavy
            return WhisperAsr()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "ASR provider 'whisper' unavailable - install faster-whisper + ffmpeg, "
                "or set asr_provider to 'echo'/'fixture'. (%s)" % exc
            )
    raise RuntimeError(f"Unknown ASR provider: {name}")
