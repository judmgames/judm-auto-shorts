from judm_auto_shorts.creative import BANNED_COPY
from judm_auto_shorts.metadata import detect_game, make_metadata


def test_detection():
    assert detect_game("SLIME_run.mp4") == "SLIME"
    assert detect_game("PN37_record.mp4") == "PN37"
    assert detect_game("BLINE_fail.mp4") == "BLINE"
    assert detect_game("FAMMER_battle.mp4") == "FAMMER"


def test_metadata_uses_creative_result_not_filename_random_hook():
    creative = {
        "style": "CLEAR",
        "clear_drop": 0.28,
        "lead_text": "이거다.",
    }
    meta = make_metadata("BLINE_run.mp4", creative)
    assert meta.hook == "이거다."
    assert "이건 좀 시원했다" in meta.youtube_title
    text = " ".join(
        [
            meta.youtube_title,
            meta.youtube_description,
            meta.instagram_caption,
            meta.tiktok_caption,
        ]
    )
    assert not any(bad in text for bad in BANNED_COPY)


def test_metadata_deterministic():
    creative = {"style": "MISTAKE", "lead_text": "아."}
    assert make_metadata("BLINE_run.mp4", creative) == make_metadata("BLINE_run.mp4", creative)
