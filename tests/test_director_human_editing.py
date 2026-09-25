import numpy as np

from judm_auto_shorts.creative import plan_from_signals


def _base(n=144):
    return {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.full(n, 0.12, np.float32),
        "scene": np.full(n, 0.04, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.52, np.float32),
        "audio": np.full(n, 0.08, np.float32),
        "focus_x": np.full(n, 0.5, np.float32),
        "focus_y": np.full(n, 0.5, np.float32),
        "focus_confidence": np.full(n, 0.55, np.float32),
        "locality": np.full(n, 0.78, np.float32),
    }


def test_unknown_game_gets_director_fields_without_invented_copy():
    s = _base()
    i = 60
    s["motion"][i] = 1.0
    s["scene"][i] = 0.68
    s["flash"][i] = 0.92
    s["audio"][i] = 1.0

    plan = plan_from_signals("GENERIC", s, duration=24.0)

    assert plan.story_clarity >= 0.34
    assert plan.hook_strategy in {
        "PAYOFF_FIRST", "MICRO_REPLAY", "ACTION_FIRST",
        "BUILD_TO_PAYOFF", "FLOW", "CLEAN", "STORY_FIRST",
    }
    assert plan.lead_text == ""
    assert plan.payoff_text == ""
    assert 5.0 <= plan.duration <= 13.0
    assert plan.payoff_at >= 1.5



def test_single_primary_treatment_no_cold_open_plus_replay():
    s = _base()
    i = 66
    s["motion"][i] = 1.0
    s["scene"][i] = 0.72
    s["flash"][i] = 1.0
    s["audio"][i] = 1.0

    plan = plan_from_signals("GENERIC", s, duration=24.0)

    assert not (plan.cold_open and plan.replay)
    if plan.replay:
        assert plan.hook_strategy == "MICRO_REPLAY"
        assert plan.replay_duration >= 0.25
    if plan.cold_open:
        assert plan.hook_strategy == "PAYOFF_FIRST"


def test_verified_clear_uses_story_window_not_fixed_length():
    s = _base()
    i = 72
    s["motion"][i] = 0.96
    s["scene"][i] = 0.62
    s["audio"][i] = 0.86
    s["flash"][i] = 0.72
    s["density"][:i] = 0.76
    s["density"][i + 1:] = 0.42

    plan = plan_from_signals("GENERIC", s, duration=24.0)

    assert plan.style == "CLEAR"
    assert plan.clear_drop >= 0.20
    assert plan.hook_strategy in {"PAYOFF_FIRST", "STORY_FIRST"}
    assert 1.5 <= plan.payoff_at <= 7.0
    assert 5.0 <= plan.duration <= 13.0



def test_recent_signature_can_select_near_equal_alternate():
    s = _base()
    first = 42
    second = 84

    s["motion"][first] = 1.0
    s["scene"][first] = 0.76
    s["flash"][first] = 0.92
    s["audio"][first] = 0.96
    s["focus_x"][first - 2:first + 3] = 0.22

    s["motion"][second] = 0.98
    s["scene"][second] = 0.70
    s["flash"][second] = 0.88
    s["audio"][second] = 0.94
    s["focus_x"][second - 2:second + 3] = 0.82

    normal = plan_from_signals("GENERIC", s, duration=24.0)
    varied = plan_from_signals(
        "GENERIC",
        s,
        duration=24.0,
        avoid_signatures={normal.signature},
    )

    assert normal.candidate_count >= 2
    assert varied.signature != normal.signature
    assert varied.confidence >= normal.confidence * 0.70
