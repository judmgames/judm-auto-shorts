from types import SimpleNamespace

from judm_auto_shorts.director import _choose_semantic_ranked


def test_verified_semantic_candidate_beats_unverified_higher_raw_score():
    unverified = SimpleNamespace(available=False)
    verified = SimpleNamespace(available=True)

    chosen = _choose_semantic_ranked([
        (0.95, "cv-only", unverified),
        (0.74, "semantic", verified),
    ])

    assert chosen[1] == "semantic"


def test_falls_back_to_raw_ranking_when_none_are_verified():
    a = SimpleNamespace(available=False)
    b = SimpleNamespace(available=False)

    chosen = _choose_semantic_ranked([
        (0.61, "a", a),
        (0.77, "b", b),
    ])

    assert chosen[1] == "b"
