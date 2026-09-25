import os
import subprocess
from pathlib import Path

import pytest

from judm_auto_shorts.editor import auto_edit, probe
from judm_auto_shorts.metadata import make_metadata


@pytest.mark.parametrize("filename", ["BLINE_test.mp4", "unknown_game.mp4"])
def test_editor_smoke(tmp_path, filename):
    if os.name == "nt":
        pytest.skip("FFmpeg render smoke is validated on Ubuntu GitHub Actions")
    src = tmp_path / filename
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=700:sample_rate=48000",
            "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(src),
        ],
        check=True,
    )
    if os.name == "nt":
        os.environ["JUDM_HOOK_FONT"] = r"C:\Windows\Fonts\malgunbd.ttf"
        os.environ["JUDM_BODY_FONT"] = r"C:\Windows\Fonts\malgun.ttf"
    else:
        os.environ["JUDM_HOOK_FONT"] = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        os.environ["JUDM_BODY_FONT"] = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

    out = auto_edit(src, tmp_path / "out", make_metadata(src.name))
    assert out["creative"]["style"] in {"CLEAR", "TURNAROUND", "BUILDUP", "IMPACT", "RHYTHM", "FEVER", "ASMR"}
    for key in ("youtube", "instagram", "tiktok"):
        p = Path(out[key])
        assert p.exists() and p.stat().st_size > 1000
        pr = probe(p)
        assert pr.width == 1080 and pr.height == 1920
