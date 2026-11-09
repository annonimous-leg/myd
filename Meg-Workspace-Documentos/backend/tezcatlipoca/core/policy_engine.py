from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

ROLE_MATRIX = {
    "restricted": {"read"},
    "full": {"read", "write", "export", "workflow"},
    "admin": {"read", "write", "export", "workflow", "admin"},
}

@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = "ok"
    risk_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

class PolicyEngine:
    def can(self, tier: str, action: str, *, metadata: dict[str, Any] | None = None) -> PolicyDecision:
        allowed = action in ROLE_MATRIX.get(tier, set())
        score = 0.0 if allowed else 1.0
        reason = "ok" if allowed else f"tier '{tier}' cannot perform '{action}'"
        return PolicyDecision(allowed=allowed, reason=reason, risk_score=score, metadata=metadata or {})

    def classify_indicator(self, score: float) -> str:
        if score >= 8.0:
            return "critical"
        if score >= 6.0:
            return "high"
        if score >= 4.0:
            return "medium"
        if score >= 2.0:
            return "low"
        return "none"
