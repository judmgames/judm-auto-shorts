import numpy as np
import pytest

from judm_auto_shorts.creative import BANNED_COPY, CreativeReject, plan_from_signals


def _signals(n=72):
    return {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.full(n, 0.08, np.float32),
        "scene": np.full(n, 0.05, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.68, np.float32),
        "audio": np.full(n, 0.06, np.float32),
    }


def test_bline_clear_or_rescue_is_scene_grounded():
    s = _signals()
    i = 36
    s["motion"][i] = 1.0
    s["scene"][i] = 0.9
    s["audio"][i] = 0.8
    s["density"][:i] = 0.76
    s["density"][i + 1:] = 0.34
    plan = plan_from_signals("BLINE", s, duration=12.0)
    assert plan.style in {"RESCUE", "CLEAR"}
    assert plan.clear_drop >= 0.10
    assert plan.cold_open is True
    assert len(plan.lead_text.replace(" ", "")) <= 8
    assert len(plan.payoff_text.replace(" ", "")) <= 8
    assert not any(x in plan.lead_text + plan.payoff_text for x in BANNED_COPY)


def test_pn37_flash_audio_becomes_fever():
    s = _signals()
    i = 34
    s["motion"][i] = 0.95
    s["scene"][i] = 0.85
    s["flash"][i] = 1.0
    s["audio"][i] = 1.0
    s["density"][:] = 0.42
    plan = plan_from_signals("PN37", s, duration=12.0)
    assert plan.style == "FEVER"
    assert plan.lead_text == "하나만 더."
    assert plan.payoff_text == "됐다."


def test_dead_video_rejected():
    n = 72
    s = {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.zeros(n, np.float32),
        "scene": np.zeros(n, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.2, np.float32),
        "audio": np.zeros(n, np.float32),
    }
    with pytest.raises(CreativeReject):
        plan_from_signals("BLINE", s, duration=12.0)
