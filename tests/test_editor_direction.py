from types import SimpleNamespace

from judm_auto_shorts.editor import _editorial_zoom_window


def _plan(treatment: str, zoom: float):
    return SimpleNamespace(treatment=treatment, zoom_strength=zoom)


def test_build_has_longer_directorial_runup_than_punch():
    build = _editorial_zoom_window(_plan("BUILD", 0.12), 5.0, 9.0)
    punch = _editorial_zoom_window(_plan("PUNCH", 0.16), 5.0, 9.0)

    assert build[0] < punch[0]
    assert build[3] <= 0.12
    assert punch[3] >= 0.10


def test_rhythm_and_clean_do_not_over_direct():
    rhythm = _editorial_zoom_window(_plan("RHYTHM", 0.14), 5.0, 9.0)
    clean = _editorial_zoom_window(_plan("CLEAN", 0.14), 5.0, 9.0)

    assert rhythm[3] <= 0.045
    assert clean[3] <= 0.035
