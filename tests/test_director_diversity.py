import numpy as np

from judm_auto_shorts.creative import plan_from_signals


def test_repeated_style_can_use_near_equal_alternate():
    n = 120
    s = {
        "time": np.arange(n, dtype=np.float32) / 6.0,
        "motion": np.full(n, 0.05, np.float32),
        "scene": np.full(n, 0.04, np.float32),
        "flash": np.zeros(n, np.float32),
        "density": np.full(n, 0.66, np.float32),
        "audio": np.full(n, 0.05, np.float32),
        "focus_x": np.full(n, 0.5, np.float32),
        "focus_y": np.full(n, 0.5, np.float32),
        "focus_confidence": np.full(n, 0.55, np.float32),
        "locality": np.full(n, 0.78, np.float32),
    }

    impact_i = 30
    s["motion"][impact_i] = 1.0
    s["scene"][impact_i] = 0.85
    s["flash"][impact_i] = 0.90
    s["audio"][impact_i] = 1.0

    clear_i = 66
    s["motion"][clear_i] = 0.95
    s["scene"][clear_i] = 0.72
    s["flash"][clear_i] = 0.80
    s["audio"][clear_i] = 0.90
    s["density"][clear_i + 1:] = 0.51

    normal = plan_from_signals("GENERIC", s, duration=20.0)
    varied = plan_from_signals(
        "GENERIC", s, duration=20.0, avoid_styles={normal.style}
    )

    assert normal.candidate_count >= 2
    assert varied.style != normal.style
    assert varied.confidence >= normal.confidence * 0.75
