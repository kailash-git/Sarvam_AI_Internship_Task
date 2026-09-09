"""Central configuration, read once from the environment.

Every value has a working default so the demo and the evaluation run with no
setup. A .env file, if present next to this repo root, is loaded first.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - dotenv is a declared dep
        return
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)


_load_dotenv()


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    llm_mode: str = os.environ.get("KIVI_LLM_MODE", "mock").strip().lower()
    llm_model: str = os.environ.get("KIVI_LLM_MODEL", "claude-sonnet-5")
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    db_path: str = os.environ.get("KIVI_DB_PATH", str(REPO_ROOT / "kivi.db"))
    apply_threshold: float = _float("KIVI_APPLY_THRESHOLD", 0.72)
    promote_after: int = _int("KIVI_PROMOTE_AFTER", 2)
    suppress_after: int = _int("KIVI_SUPPRESS_AFTER", 2)

    def resolved_db_path(self) -> str:
        p = Path(self.db_path)
        if not p.is_absolute():
            p = REPO_ROOT / p
        return str(p)


settings = Settings()
