import numpy as np
import pytest

from judm_auto_shorts.director import (
    CreativeReject,
    _apply_semantic_hint,
    plan_from_signals,
)
from judm_auto_shorts.semantic import SemanticHint, parse_semantic_response


def _signals(n=120):
    return {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.full(n, 0.08, np.float32),
        "scene": np.full(n, 0.04, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.58, np.float32),
        "audio": np.full(n, 0.06, np.float32),
        "focus_x": np.full(n, 0.5, np.float32),
        "focus_y": np.full(n, 0.5, np.float32),
        "focus_confidence": np.full(n, 0.50, np.float32),
        "locality": np.full(n, 0.75, np.float32),
    }
def test_semantic_parser_accepts_only_structured_whitelist():
    hint = parse_semantic_response(
        "SCENE=gameplay; EVENT=clear; OUTCOME=success; CONFIDENCE=high"
    )
    assert hint.available is True
    assert hint.scene == "gameplay"
    assert hint.event == "clear"
    assert hint.outcome == "success"
    assert hint.confidence == 0.85

    bad = parse_semantic_response(
        "SCENE=gameplay; EVENT=new_record; OUTCOME=amazing; CONFIDENCE=high"
    )
    assert bad.event == "unknown"
    assert bad.outcome == "unknown"


def test_high_confidence_menu_is_rejected():
    s = _signals()
    i = 54
    s["motion"][i] = 1.0
    s["scene"][i] = 0.65
    s["flash"][i] = 0.85
    s["audio"][i] = 1.0
    plan = plan_from_signals("GENERIC", s, duration=20.0)

    hint = SemanticHint(
        available=True,
        scene="menu",
        event="transition",
        outcome="unknown",
        confidence=0.85,
        reason="parsed",
    )
    with pytest.raises(CreativeReject):
        _apply_semantic_hint(plan, hint)
def test_generic_semantic_clear_can_upgrade_treatment_without_copy():
    s = _signals()
    i = 54
    s["motion"][i] = 1.0
    s["scene"][i] = 0.60
    s["audio"][i] = 0.9
    s["flash"][i] = 0.75
    plan = plan_from_signals("GENERIC", s, duration=20.0)

    hint = SemanticHint(
        available=True,
        scene="gameplay",
        event="clear",
        outcome="success",
        confidence=0.85,
        reason="parsed",
    )
    updated = _apply_semantic_hint(plan, hint)
    assert updated.style == "CLEAR"
    assert updated.treatment == "REVEAL"
    assert updated.semantic_used is True
    assert updated.semantic_event == "clear"
    assert updated.lead_text == ""
    assert updated.payoff_text == ""
    assert updated.cold_open is True


def test_semantic_failure_never_keeps_generic_clear_claim():
    s = _signals()
    i = 60
    s["motion"][i] = 0.95
    s["audio"][i] = 0.85
    s["density"][:i] = 0.80
    s["density"][i + 1:] = 0.42
    plan = plan_from_signals("GENERIC", s, duration=20.0)
    assert plan.style == "CLEAR"

    hint = SemanticHint(
        available=True,
        scene="gameplay",
        event="impact",
        outcome="failure",
        confidence=0.85,
        reason="parsed",
    )
    updated = _apply_semantic_hint(plan, hint)
    assert updated.style == "IMPACT"
    assert updated.payoff_text == ""
