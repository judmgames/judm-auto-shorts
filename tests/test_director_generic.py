import cv2
import numpy as np
import pytest

from judm_auto_shorts.creative import CreativeReject, plan_from_signals


def _signals(n=120):
    return {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.full(n, 0.06, np.float32),
        "scene": np.full(n, 0.04, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.52, np.float32),
        "audio": np.full(n, 0.05, np.float32),
        "focus_x": np.full(n, 0.72, np.float32),
        "focus_y": np.full(n, 0.42, np.float32),
        "focus_confidence": np.full(n, 0.55, np.float32),
        "locality": np.full(n, 0.75, np.float32),
    }


def test_unknown_game_can_direct_a_grounded_clear():
    s = _signals()
    i = 54
    s["motion"][i] = 0.95
    s["scene"][i] = 0.62
    s["audio"][i] = 0.86
    s["flash"][i] = 0.72
    s["density"][:i] = 0.76
    s["density"][i + 1:] = 0.43
    plan = plan_from_signals("GENERIC", s, duration=20.0)
    assert plan.style == "CLEAR"
    assert plan.treatment == "REVEAL"
    assert plan.clear_drop >= 0.20
    assert plan.payoff_text == "한 번에."
    assert plan.candidate_count >= 1


def test_unknown_game_impact_stays_semantically_safe():
    s = _signals()
    i = 48
    s["motion"][i] = 1.0
    s["scene"][i] = 0.72
    s["audio"][i] = 0.94
    s["flash"][i] = 0.84
    plan = plan_from_signals("GENERIC", s, duration=20.0)
    assert plan.style in {"IMPACT", "BUILDUP", "RHYTHM", "ASMR"}
    assert plan.lead_text == ""
    assert plan.payoff_text == ""
    assert 0.05 <= plan.focus_x <= 0.95
    assert 0.05 <= plan.focus_y <= 0.95


def test_story_candidate_beats_outro_transition():
    s = _signals()
    story_i = 48
    outro_i = 112
    s["motion"][story_i] = 0.88
    s["audio"][story_i] = 0.78
    s["density"][:story_i] = 0.70
    s["density"][story_i + 1:] = 0.48
    s["motion"][outro_i] = 1.0
    s["scene"][outro_i] = 1.0
    s["flash"][outro_i] = 1.0
    s["audio"][outro_i] = 1.0
    s["locality"][outro_i] = 0.05
    plan = plan_from_signals("GENERIC", s, duration=20.0)
    assert plan.start < 14.0
    assert plan.style == "CLEAR"


def test_dead_unknown_game_is_rejected():
    n = 90
    s = {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.zeros(n, np.float32),
        "scene": np.zeros(n, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.2, np.float32),
        "audio": np.zeros(n, np.float32),
    }
    with pytest.raises(CreativeReject):
        plan_from_signals("GENERIC", s, duration=15.0)


def test_unknown_game_auto_roi_follows_persistent_action(tmp_path):
    from judm_auto_shorts.director import _detect_generic_roi

    video = tmp_path / "roi_test.avi"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"MJPG"),
        15.0,
        (640, 360),
    )
    assert writer.isOpened()
    for i in range(90):
        frame = np.zeros((360, 640, 3), np.uint8)
        x = 390 + (i * 5) % 150
        cv2.rectangle(frame, (x, 90), (min(x + 55, 625), 285), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()

    x0, y0, x1, y1 = _detect_generic_roi(video)
    assert x1 > 0.70
    assert (x0 + x1) / 2 > 0.52
    assert x1 - x0 >= 0.47
    assert y1 - y0 >= 0.47
