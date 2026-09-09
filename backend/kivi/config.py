"""Central configuration. All thresholds/weights live here (loaded from repo-root config.json).

Values are provisional and are meant to be validated by the evaluation harness
(see evaluation/run.py and evaluation/results/report.md).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (D:/Sarvam_AI)
_CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

DB_PATH = ROOT / _CFG["db_path"]
MIGRATIONS_DIR = ROOT / "database" / "migrations"
SEED_FILE = ROOT / "database" / "seed" / "seed.json"
UPLOAD_DIR = ROOT / "backend" / "uploads"
FRONTEND_DIR = ROOT / "frontend"
EVAL_RESULTS_DIR = ROOT / "evaluation" / "results"

ASR_PROVIDER = _CFG.get("asr_provider", "echo")
FORMATTER_MODE = _CFG.get("formatter_mode", "rules")

T = _CFG["thresholds"]
C = _CFG["confidence"]
PP = _CFG.get("personal_phonetics", {
    "enabled": True, "min_observations": 2, "weight_k": 2.5, "weight_cap": 1.0,
    "max_chunk_len": 3, "match_floor": 0.85, "match_score_cap": 0.88,
    "combined_boost": 0.35, "prior_k": 3.0, "tiebreak_min_count": 3,
})
CONTEXT_LIST_MAX = int(_CFG.get("context_list_max", 12))
AUDIO = _CFG.get("audio", {"max_seconds": 60, "max_mb": 5})


def as_dict() -> dict:
    return {
        "db_path": str(DB_PATH),
        "asr_provider": ASR_PROVIDER,
        "formatter_mode": FORMATTER_MODE,
        "thresholds": T,
        "confidence": C,
        "personal_phonetics": PP,
        "context_list_max": CONTEXT_LIST_MAX,
    }
