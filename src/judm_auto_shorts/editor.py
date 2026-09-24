from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .creative import CreativePlan, analyze_creative
from .metadata import LABEL


@dataclass
class Probe:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


def run(cmd: list[str]):
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


def probe(path: str | Path) -> Probe:
    data = json.loads(
        run([
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ]).stdout
    )
    video = next(s for s in data["streams"] if s.get("codec_type") == "video")
    fr = video.get("avg_frame_rate") or "30/1"
    a, b = fr.split("/")
    fps = float(a) / max(float(b), 1)
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
    return Probe(
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        has_audio=any(s.get("codec_type") == "audio" for s in data["streams"]),
    )


def font(role: str = "body") -> str:
    if role == "hook":
        candidates = [
            os.getenv("JUDM_HOOK_FONT", ""),
            str(Path.home() / ".local/share/fonts/DoHyeon-Regular.ttf"),
            "/usr/local/share/fonts/judm/DoHyeon-Regular.ttf",
        ]
    else:
        candidates = [
            os.getenv("JUDM_BODY_FONT", ""),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    family = "Do Hyeon" if role == "hook" else "Noto Sans CJK KR"
    match = subprocess.run(
        ["fc-match", "-f", "%{file}", family],
        text=True, capture_output=True,
    )
    found = match.stdout.strip()
    if found and Path(found).exists():
        return found
    raise FileNotFoundError(f"font missing: {role}")


def esc(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
        .replace(",", r"\,")
    )


def _draw_text(stream: str, out: str, text: str, start: float, end: float, font_path: str, y: str) -> str:
    if not text or end <= start:
        return f"[{stream}]null[{out}]"
    size = 70 if len(text.replace(" ", "")) <= 4 else 62
    return (
        f"[{stream}]drawtext=fontfile='{font_path}':text='{esc(text)}':"
        f"fontsize={size}:fontcolor=white:borderw=4:bordercolor=black@.88:"
        f"box=1:boxcolor=black@.34:boxborderw=18:"
        f"x=(w-text_w)/2:y={y}:enable='between(t,{start:.2f},{end:.2f})'[{out}]"
    )


def render(src: str | Path, dst: str | Path, plan: CreativePlan, label: str) -> str:
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    p = probe(src)
    hf, bf = font("hook"), font("body")

    payoff_abs = plan.start + plan.payoff_at
    cold = plan.cold_open_duration if plan.cold_open else 0.0
    if cold:
        cold_start = max(0.0, min(payoff_abs - 0.14, max(0.0, p.duration - cold)))
        seq = (
            f"[0:v]trim=start={cold_start:.3f}:duration={cold:.3f},setpts=PTS-STARTPTS[coldv];"
            f"[0:v]trim=start={plan.start:.3f}:duration={plan.duration:.3f},setpts=PTS-STARTPTS[mainv];"
            f"[coldv][mainv]concat=n=2:v=1:a=0[seqv]"
        )
    else:
        seq = (
            f"[0:v]trim=start={plan.start:.3f}:duration={plan.duration:.3f},"
            f"setpts=PTS-STARTPTS[seqv]"
        )

    final_payoff = cold + plan.payoff_at
    final_duration = cold + plan.duration
    zoom_start = max(0.0, final_payoff - 0.34)
    zoom_end = min(final_duration, final_payoff + 0.48)
    cold_expr = f"+0.08*between(t,0,{cold:.2f})" if cold else ""
    factor = f"1{cold_expr}+0.13*between(t,{zoom_start:.2f},{zoom_end:.2f})"

    visual = (
        f";[seqv]split=2[bg0][fg0];"
        f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,gblur=sigma=34,eq=brightness=-0.12:saturation=.84[bg];"
        f"[fg0]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]scale=w='trunc(1080*({factor})/2)*2':"
        f"h='trunc(1920*({factor})/2)*2':eval=frame,"
        f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2[zoom]"
    )

    lead_start = max(cold + 0.10, final_payoff - 1.55)
    lead_end = max(lead_start + 0.35, final_payoff - 0.55)
    payoff_start = min(final_duration - 0.2, final_payoff + 0.06)
    payoff_end = min(final_duration, payoff_start + 0.82)
    if plan.style == "MISTAKE" and cold:
        lead_start, lead_end = 0.06, min(cold, 0.48)

    draw1 = _draw_text("zoom", "txt1", plan.lead_text, lead_start, lead_end, hf, "h-360")
    draw2 = _draw_text("txt1", "txt2", plan.payoff_text, payoff_start, payoff_end, hf, "h-360")
    watermark = (
        f";[txt2]drawtext=fontfile='{bf}':text='{esc(label)}':fontsize=30:"
        f"fontcolor=white@.72:borderw=2:bordercolor=black@.58:"
        f"x=42:y=h-92[vout]"
    )
    fc = seq + visual + ";" + draw1 + ";" + draw2 + watermark

    if p.has_audio:
        if cold:
            cold_start = max(0.0, min(payoff_abs - 0.14, max(0.0, p.duration - cold)))
            fc += (
                f";[0:a]atrim=start={cold_start:.3f}:duration={cold:.3f},"
                f"asetpts=PTS-STARTPTS[colda];"
                f"[0:a]atrim=start={plan.start:.3f}:duration={plan.duration:.3f},"
                f"asetpts=PTS-STARTPTS[maina];"
                f"[colda][maina]concat=n=2:v=0:a=1,"
                f"afade=t=in:st=0:d=0.04,"
                f"afade=t=out:st={max(0.0, final_duration - 0.18):.2f}:d=0.18[aout]"
            )
        else:
            fc += (
                f";[0:a]atrim=start={plan.start:.3f}:duration={plan.duration:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d=0.04,"
                f"afade=t=out:st={max(0.0, final_duration - 0.18):.2f}:d=0.18[aout]"
            )

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", fc, "-map", "[vout]"]
    if p.has_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    else:
        cmd += ["-an"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
        "-maxrate", "8M", "-bufsize", "16M", str(dst),
    ]
    run(cmd)
    return str(dst)


def auto_edit(src: str | Path, out_dir: str | Path, meta_or_game) -> dict:
    p = probe(src)
    if p.duration < 2 or p.width < 240 or p.height < 240:
        raise ValueError(f"source video too small/short: {p}")
    game_key = getattr(meta_or_game, "game_key", str(meta_or_game))
    plan = analyze_creative(src, game_key, p.duration)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    master = out / f"{Path(src).stem}_v3.mp4"
    render(src, master, plan, LABEL.get(game_key, LABEL["GENERIC"]))
    path = str(master)
    return {
        "youtube": path,
        "instagram": path,
        "tiktok": path,
        "creative": plan.to_dict(),
        "highlight": {
            "start": plan.start,
            "duration": plan.duration,
            "peak_at": plan.payoff_at,
            "confidence": plan.confidence,
            "style": plan.style,
        },
    }
