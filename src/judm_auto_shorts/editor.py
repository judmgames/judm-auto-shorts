from __future__ import annotations

import json
import os
import subprocess

import cv2

from dataclasses import dataclass
from pathlib import Path

from .creative import CreativePlan, CreativeReject, analyze_creative
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
        f"fontsize={size}:fontcolor=white:borderw=3:bordercolor=black@.88:"
        f"shadowcolor=black@.45:shadowx=2:shadowy=3:"
        f"x=(w-text_w)/2:y={y}:enable='between(t,{start:.2f},{end:.2f})'[{out}]"
    )


def render(src: str | Path, dst: str | Path, plan: CreativePlan, label: str) -> str:
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    p = probe(src)
    hf, bf = font("hook"), font("body")

    payoff_abs = plan.start + plan.payoff_at
    cold = plan.cold_open_duration if plan.cold_open else 0.0
    replay = bool(plan.replay and plan.replay_duration > 0 and not cold)
    replay_len = 0.0
    replay_src_start = 0.0
    if replay:
        replay_src_start = max(plan.start, payoff_abs - plan.replay_duration * 0.42)
        replay_len = min(
            float(plan.replay_duration),
            max(0.0, p.duration - replay_src_start),
        )
        if replay_len < 0.25:
            replay = False
            replay_len = 0.0

    if cold:
        cold_start = max(0.0, min(payoff_abs - 0.14, max(0.0, p.duration - cold)))
        seq = (
            f"[0:v]trim=start={cold_start:.3f}:duration={cold:.3f},setpts=PTS-STARTPTS[coldv];"
            f"[0:v]trim=start={plan.start:.3f}:duration={plan.duration:.3f},setpts=PTS-STARTPTS[mainv];"
            f"[coldv][mainv]concat=n=2:v=1:a=0[seqv]"
        )
    elif replay:
        seq = (
            f"[0:v]trim=start={plan.start:.3f}:duration={plan.duration:.3f},setpts=PTS-STARTPTS[mainv];"
            f"[0:v]trim=start={replay_src_start:.3f}:duration={replay_len:.3f},setpts=PTS-STARTPTS[replayv];"
            f"[mainv][replayv]concat=n=2:v=1:a=0[seqv]"
        )
    else:
        seq = (
            f"[0:v]trim=start={plan.start:.3f}:duration={plan.duration:.3f},"
            f"setpts=PTS-STARTPTS[seqv]"
        )

    final_payoff = cold + plan.payoff_at
    final_duration = cold + plan.duration + replay_len
    zoom_start = max(0.0, final_payoff - 0.34)
    zoom_end = min(final_duration, final_payoff + 0.52)
    cold_expr = f"+0.06*between(t,0,{cold:.2f})" if cold else ""
    replay_expr = (
        f"+0.04*between(t,{plan.duration:.2f},{final_duration:.2f})"
        if replay
        else ""
    )
    punch = max(0.05, min(0.18, float(plan.zoom_strength)))
    factor = (
        f"1{cold_expr}"
        f"+{punch:.3f}*between(t,{zoom_start:.2f},{zoom_end:.2f})"
        f"{replay_expr}"
    )

    aspect = p.width / max(p.height, 1)
    if aspect >= 1.20:
        focus_height = int(760 + 170 * float(plan.focus_confidence))
        target_w = int(max(1280, min(2100, focus_height * aspect)))
        focus_start = float(plan.focus_start_x)
        focus_end = float(plan.focus_x)
        pan_distance = abs(focus_end - focus_start)
        if pan_distance < 0.035 or plan.focus_confidence < 0.15:
            focus_expr = f"{focus_end:.4f}"
        elif cold:
            pan_secs = max(float(plan.payoff_at), 0.2)
            progress = (
                f"min(1,max(0,(t-{cold:.3f})/{pan_secs:.3f}))"
            )
            focus_expr = (
                f"if(lt(t,{cold:.3f}),{focus_end:.4f},"
                f"{focus_start:.4f}+({focus_end-focus_start:.4f})*{progress})"
            )
        else:
            pan_secs = max(float(plan.payoff_at), 0.2)
            progress = f"min(1,max(0,t/{pan_secs:.3f}))"
            focus_expr = (
                f"{focus_start:.4f}+({focus_end-focus_start:.4f})*{progress}"
            )
        crop_x = f"max(0,min(iw-1080,iw*({focus_expr})-540))"
        foreground = (
            f"[fg0]scale={target_w}:-2[fgs];"
            f"[fgs]crop=1080:ih:x='{crop_x}':y=0[fg]"
        )
    else:
        foreground = (
            "[fg0]scale=1080:1920:force_original_aspect_ratio=decrease[fg]"
        )

    visual = (
        f";[seqv]split=2[bg0][fg0];"
        f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,gblur=sigma=42,"
        f"eq=brightness=-0.18:saturation=.56[bg];"
        f"{foreground};"
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

    caption_y = "220" if plan.focus_y >= 0.57 else "h-390"
    draw1 = _draw_text("zoom", "txt1", plan.lead_text, lead_start, lead_end, hf, caption_y)
    draw2 = _draw_text("txt1", "txt2", plan.payoff_text, payoff_start, payoff_end, hf, caption_y)
    watermark = (
        f";[txt2]drawtext=fontfile='{bf}':text='{esc(label)}':fontsize=30:"
        f"fontcolor=white@.72:borderw=2:bordercolor=black@.58:"
        f"x=42:y=h-92[vout]"
    )
    fc = seq + visual + ";" + draw1 + ";" + draw2 + watermark

    if p.has_audio:
        audio_boost = 1.12 if plan.treatment in {"REVEAL", "PUNCH", "BUILD"} else 1.06
        boost_start = max(0.0, final_payoff - 0.18)
        boost_end = min(final_duration, final_payoff + 0.42)
        if cold:
            cold_start = max(0.0, min(payoff_abs - 0.14, max(0.0, p.duration - cold)))
            fc += (
                f";[0:a]atrim=start={cold_start:.3f}:duration={cold:.3f},"
                f"asetpts=PTS-STARTPTS[colda];"
                f"[0:a]atrim=start={plan.start:.3f}:duration={plan.duration:.3f},"
                f"asetpts=PTS-STARTPTS[maina];"
                f"[colda][maina]concat=n=2:v=0:a=1,"
                f"volume={audio_boost:.2f}:enable='between(t,{boost_start:.2f},{boost_end:.2f})',"
                f"afade=t=in:st=0:d=0.04,"
                f"afade=t=out:st={max(0.0, final_duration - 0.18):.2f}:d=0.18[aout]"
            )
        elif replay:
            fc += (
                f";[0:a]atrim=start={plan.start:.3f}:duration={plan.duration:.3f},"
                f"asetpts=PTS-STARTPTS[maina];"
                f"[0:a]atrim=start={replay_src_start:.3f}:duration={replay_len:.3f},"
                f"asetpts=PTS-STARTPTS[replaya];"
                f"[maina][replaya]concat=n=2:v=0:a=1,"
                f"volume={audio_boost:.2f}:enable='between(t,{boost_start:.2f},{boost_end:.2f})',"
                f"afade=t=in:st=0:d=0.04,"
                f"afade=t=out:st={max(0.0, final_duration - 0.18):.2f}:d=0.18[aout]"
            )
        else:
            fc += (
                f";[0:a]atrim=start={plan.start:.3f}:duration={plan.duration:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"volume={audio_boost:.2f}:enable='between(t,{boost_start:.2f},{boost_end:.2f})',"
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


def validate_render_quality(
    path: str | Path,
    plan: CreativePlan | None = None,
) -> dict:
    path = Path(path)
    pr = probe(path)
    if pr.width != 1080 or pr.height != 1920:
        raise CreativeReject(f"render geometry invalid: {pr.width}x{pr.height}")
    if not (5.0 <= pr.duration <= 16.0):
        raise CreativeReject(f"render duration invalid: {pr.duration:.2f}s")
    if path.stat().st_size < 100_000:
        raise CreativeReject("render output unexpectedly small")

    cap = cv2.VideoCapture(str(path))
    times = [
        0.12,
        min(0.55, pr.duration * 0.18),
        min(1.00, pr.duration * 0.24),
        pr.duration * 0.50,
        max(0.2, pr.duration - 0.30),
    ]
    frames = []
    means = []
    for sec in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000.0)
        ok, frame = cap.read()
        if ok and frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (180, 320), interpolation=cv2.INTER_AREA)
            frames.append(small)
            means.append(float(small.mean()))
    cap.release()

    if len(frames) < 4:
        raise CreativeReject("render could not be sampled for final QC")
    if max(means) < 12.0:
        raise CreativeReject("render appears black or visually broken")

    diffs = [
        float(cv2.absdiff(frames[i], frames[i - 1]).mean())
        for i in range(1, len(frames))
    ]
    first_second_motion = max(diffs[:2]) if len(diffs) >= 2 else 0.0
    overall_motion = max(diffs) if diffs else 0.0

    if overall_motion < 0.65:
        raise CreativeReject("render appears frozen or visually static")
    if (
        plan is not None
        and plan.cold_open
        and first_second_motion < 0.45
    ):
        raise CreativeReject("cold open failed final hook-motion QC")

    return {
        "first_second_motion": round(first_second_motion, 3),
        "overall_motion": round(overall_motion, 3),
        "sample_brightness_max": round(max(means), 2),
    }


def auto_edit(
    src: str | Path,
    out_dir: str | Path,
    meta_or_game,
    avoid_styles: set[str] | None = None,
    avoid_signatures: set[str] | None = None,
) -> dict:
    p = probe(src)
    if p.duration < 2 or p.width < 240 or p.height < 240:
        raise ValueError(f"source video too small/short: {p}")
    game_key = getattr(meta_or_game, "game_key", str(meta_or_game))
    plan = analyze_creative(
        src,
        game_key,
        p.duration,
        avoid_styles=avoid_styles,
        avoid_signatures=avoid_signatures,
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    master = out / f"{Path(src).stem}_v4.mp4"
    render(src, master, plan, LABEL.get(game_key, LABEL["GENERIC"]))
    quality = validate_render_quality(master, plan)
    path = str(master)
    return {
        "youtube": path,
        "instagram": path,
        "tiktok": path,
        "creative": plan.to_dict(),
        "quality": quality,
        "highlight": {
            "start": plan.start,
            "duration": plan.duration,
            "peak_at": plan.payoff_at,
            "confidence": plan.confidence,
            "style": plan.style,
        },
    }
