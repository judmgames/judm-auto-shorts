from __future__ import annotations

# Backward-compatible imports for tests and existing callers.
# V4's actual decision engine lives in director.py.
from .director import (
    BANNED_COPY,
    CreativePlan,
    CreativeReject,
    SemanticUnavailable,
    EventCandidate,
    analyze_creative,
    plan_from_signals,
    sample_signals,
)

__all__ = [
    "BANNED_COPY",
    "CreativePlan",
    "CreativeReject",
    "SemanticUnavailable",
    "EventCandidate",
    "analyze_creative",
    "plan_from_signals",
    "sample_signals",
]
