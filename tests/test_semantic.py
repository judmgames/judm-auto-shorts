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
    assert updated.style == "FAIL"
    assert updated.treatment == "PUNCH"
    assert updated.hook_strategy == "MICRO_REPLAY"
    assert updated.replay is True
    assert updated.payoff_text == ""


def test_semantic_alignment_penalizes_menu_and_rewards_story_match():
    from judm_auto_shorts.director import EventCandidate, _semantic_alignment_score

    candidate = EventCandidate(
        index=10, time=2.0, score=0.62, style="TURNAROUND",
        event=0.70, buildup=0.20, relief=0.05, sustained=0.45,
        locality=0.70, focus_x=0.5, focus_y=0.5, focus_confidence=0.5,
        story_clarity=0.60, contrast=0.30, sync=0.70, menu_risk=0.0,
        pre_level=0.50, post_level=0.20,
    )
    menu = SemanticHint(
        available=True, scene="menu", event="transition",
        outcome="unknown", confidence=0.85,
    )
    recovery = SemanticHint(
        available=True, scene="gameplay", event="danger",
        outcome="recovery", confidence=0.85,
    )

    assert _semantic_alignment_score(candidate, menu) < 0.0
    assert _semantic_alignment_score(candidate, recovery) > candidate.score


def test_semantic_parser_accepts_colon_and_quotes():
    hint = parse_semantic_response(
        '"SCENE": "gameplay"; "EVENT": "impact"; '
        '"OUTCOME": "success"; "CONFIDENCE": "medium"'
    )
    assert hint.available is True
    assert hint.scene == "gameplay"
    assert hint.event == "impact"
    assert hint.outcome == "success"
    assert hint.confidence == 0.60


def test_scene_only_semantic_is_not_enough_for_director_use():
    hint = parse_semantic_response(
        "SCENE=gameplay; EVENT=unknown; OUTCOME=unknown; CONFIDENCE=high"
    )
    assert hint.available is False
    assert hint.scene == "gameplay"


def test_semantic_single_label_is_preferred_for_small_model():
    hint = parse_semantic_response("gameplay_danger_recovery")
    assert hint.available is True
    assert hint.scene == "gameplay"
    assert hint.event == "danger"
    assert hint.outcome == "recovery"
    assert hint.confidence >= 0.80
    assert hint.reason == "label_exact"
