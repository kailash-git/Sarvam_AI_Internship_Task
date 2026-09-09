from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AsrResult:
    text: str
    provider: str
    tokens: list[str] = field(default_factory=list)
    token_confidences: list[float] | None = None
    latency_ms: float = 0.0
    model_calls: int = 0
    est_cost_usd: float = 0.0
