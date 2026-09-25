from __future__ import annotations

import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .game_profiles import get_profile


BANNED_COPY = (
    "끝난 판인 줄 알았지",
    "3초 안에",
    "도파민",
    "인정",
    "레전드",
    "천재만",
    "99%",
    "이 맛에",
    "너라면",
)


class CreativeReject(RuntimeError):
    pass


@dataclass(frozen=True)
class EventCandidate:
    index: int
    time: float
    score: float
    style: str
    event: float
    buildup: float
    relief: float
    sustained: float
    locality: float
    focus_x: float
    focus_y: float
    focus_confidence: float
@dataclass(frozen=True)
class CreativePlan:
    game_key: str
    style: str
    start: float
    duration: float
    payoff_at: float
    confidence: float
    density_before: float
    density_after: float
    clear_drop: float
    lead_text: str
    payoff_text: str
    cold_open: bool
    cold_open_duration: float
    treatment: str
    focus_x: float
    focus_y: float
    focus_confidence: float
    zoom_strength: float
    candidate_count: int
    alternates: tuple[str, ...]
    signature: str
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(x: np.ndarray) -> np.ndarray:
    if not len(x):
        return x
    lo, hi = np.percentile(x, [10, 95])
    if hi <= lo + 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def _safe_copy(text: str) -> str:
    text = (text or "").strip()
    if any(bad in text for bad in BANNED_COPY):
        raise CreativeReject(f"banned copy generated: {text}")
    if len(text.replace(" ", "")) > 8:
        raise CreativeReject(f"copy too long: {text}")
    return text
def _audio_scores(path: str | Path, hz: float) -> tuple[np.ndarray, np.ndarray]:
    try:
        raw = subprocess.check_output(
            [
                "ffmpeg", "-v", "error", "-i", str(path), "-vn",
                "-ac", "1", "-ar", "8000", "-f", "f32le", "pipe:1",
            ]
        )
    except Exception:
        return np.array([], np.float32), np.array([], np.float32)
    x = np.frombuffer(raw, np.float32)
    win = max(int(8000 / hz), 1)
    vals = []
    for i in range(math.ceil(len(x) / win)):
        seg = x[i * win:(i + 1) * win]
        if seg.size:
            vals.append(float(np.sqrt(np.mean(seg * seg) + 1e-12)))
    rms = np.asarray(vals, np.float32)
    return np.arange(len(rms), dtype=np.float32) / hz, rms


def _crop_roi(frame: np.ndarray, game_key: str) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = get_profile(game_key).roi
    a, b, c, d = int(w * x0), int(h * y0), int(w * x1), int(h * y1)
    crop = frame[max(0, b):max(b + 1, d), max(0, a):max(a + 1, c)]
    return crop if crop.size else frame


def _focus_from_diff(diff: np.ndarray) -> tuple[float, float, float, float]:
    weights = np.maximum(diff.astype(np.float32) - 10.0, 0.0)
    total = float(weights.sum())
    spread = float((diff > 22).mean())
    if total <= 1e-6:
        return 0.5, 0.5, 0.0, 1.0 - min(1.0, spread * 2.0)
    yy, xx = np.indices(diff.shape, dtype=np.float32)
    fx = float((weights * xx).sum() / total / max(diff.shape[1] - 1, 1))
    fy = float((weights * yy).sum() / total / max(diff.shape[0] - 1, 1))
    confidence = float(np.clip(total / (diff.size * 24.0), 0, 1))
    locality = float(np.clip(1.0 - spread * 2.2, 0, 1))
    return fx, fy, confidence, locality
def sample_signals(
    path: str | Path,
    game_key: str,
    hz: float = 6.0,
) -> dict[str, np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(round(fps / hz)), 1)
    times, motion, scene, flash, density = [], [], [], [], []
    focus_x, focus_y, focus_conf, locality = [], [], [], []
    prev_gray = prev_hist = None
    prev_value = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step:
            i += 1
            continue
        roi = _crop_roi(frame, game_key)
        small = cv2.resize(roi, (256, 256), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        sat, val = hsv[:, :, 1], hsv[:, :, 2]
        colored = ((sat > 52) & (val > 48)).astype(np.float32)
        edge = (cv2.Canny(gray, 70, 150) > 0).astype(np.float32)
        occ = float(np.clip(0.78 * colored.mean() + 0.22 * edge.mean() * 2.5, 0, 1))
        if prev_gray is None:
            mot = scn = fl = 0.0
            fx, fy, fc, loc = 0.5, 0.5, 0.0, 1.0
        else:
            diff = cv2.absdiff(gray, prev_gray)
            mot = float(diff.mean()) / 255.0
            scn = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
            mean_v = float(val.mean()) / 255.0
            fl = max(0.0, mean_v - float(prev_value))
            fx, fy, fc, loc = _focus_from_diff(diff)
        times.append(i / fps)
        motion.append(mot)
        scene.append(scn)
        flash.append(fl)
        density.append(occ)
        focus_x.append(fx)
        focus_y.append(fy)
        focus_conf.append(fc)
        locality.append(loc)
        prev_gray, prev_hist = gray, hist
        prev_value = float(val.mean()) / 255.0
        i += 1
    cap.release()

    t = np.asarray(times, np.float32)
    m = _norm(np.asarray(motion, np.float32))
    s = _norm(np.asarray(scene, np.float32))
    f = _norm(np.asarray(flash, np.float32))
    d = np.asarray(density, np.float32)
    fx = np.asarray(focus_x, np.float32)
    fy = np.asarray(focus_y, np.float32)
    fc = np.asarray(focus_conf, np.float32)
    loc = np.asarray(locality, np.float32)
    at, av = _audio_scores(path, hz)
    a = np.interp(t, at, _norm(av), left=0, right=0).astype(np.float32) if len(at) else np.zeros_like(t)
    return {
        "time": t,
        "motion": m,
        "scene": s,
        "flash": f,
        "density": d,
        "audio": a,
        "focus_x": fx,
        "focus_y": fy,
        "focus_confidence": fc,
        "locality": loc,
    }


def _segment_mean(x: np.ndarray, lo: int, hi: int, fallback: float) -> float:
    seg = x[max(0, lo):min(len(x), hi)]
    return float(np.mean(seg)) if len(seg) else fallback


def _candidate_indexes(event: np.ndarray, valid: np.ndarray, min_gap: int) -> list[int]:
    idxs = []
    for i in range(1, len(event) - 1):
        if not valid[i]:
            continue
        if event[i] >= event[i - 1] and event[i] >= event[i + 1]:
            idxs.append(i)
    idxs.sort(key=lambda i: float(event[i]), reverse=True)
    chosen = []
    for i in idxs:
        if all(abs(i - j) >= min_gap for j in chosen):
            chosen.append(i)
        if len(chosen) >= 12:
            break
    return chosen


def _weighted_focus(signals: dict[str, np.ndarray], idx: int, radius: int) -> tuple[float, float, float]:
    lo, hi = max(0, idx - radius), min(len(signals["time"]), idx + radius + 1)
    w = signals["motion"][lo:hi] + 0.35 * signals["audio"][lo:hi] + 0.1
    conf = signals["focus_confidence"][lo:hi]
    if not len(w):
        return 0.5, 0.5, 0.0
    w = w * (0.35 + conf)
    den = float(np.sum(w))
    if den <= 1e-6:
        return 0.5, 0.5, 0.0
    fx = float(np.sum(signals["focus_x"][lo:hi] * w) / den)
    fy = float(np.sum(signals["focus_y"][lo:hi] * w) / den)
    fc = float(np.clip(np.mean(conf) * 1.6, 0, 1))
    return fx, fy, fc
def _build_candidates(
    game_key: str,
    signals: dict[str, np.ndarray],
    duration: float,
) -> tuple[list[EventCandidate], dict[str, np.ndarray]]:
    t = signals["time"]
    motion = signals["motion"]
    scene = signals["scene"]
    flash = signals["flash"]
    density = signals["density"]
    audio = signals["audio"]
    locality = signals["locality"]
    step = float(np.median(np.diff(t))) if len(t) > 1 else 1 / 6
    radius = max(2, int(round(0.9 / max(step, 1e-3))))

    event = np.clip(
        0.34 * motion + 0.20 * scene + 0.22 * audio + 0.12 * flash
        + 0.12 * (motion * locality),
        0, 1,
    )
    if len(event) >= 5:
        event = 0.72 * event + 0.28 * np.convolve(event, np.ones(5) / 5, mode="same")

    if duration >= 60:
        end_guard = 8.0
    elif duration >= 20:
        end_guard = 4.0
    else:
        end_guard = 1.5
    safe_end = max(3.0, duration - end_guard)
    valid = (t >= 1.5) & (t <= max(1.5, safe_end - 0.9))
    if not np.any(valid):
        valid = (t >= 0.4) & (t <= max(0.4, duration - 0.6))

    min_gap = max(2, int(round(2.2 / max(step, 1e-3))))
    indexes = _candidate_indexes(event, valid, min_gap)
    candidates: list[EventCandidate] = []
    for i in indexes:
        pre_near = _segment_mean(event, i - radius * 2, i, float(event[i]))
        pre_far = _segment_mean(event, i - radius * 5, i - radius * 2, pre_near)
        post = _segment_mean(event, i + 1, i + radius * 3, float(event[i]))
        before_d = _segment_mean(density, i - radius * 2, i, float(density[i]))
        after_d = _segment_mean(density, i + radius, i + radius * 4, float(density[i]))
        relief = max(0.0, before_d - after_d)
        buildup = max(0.0, pre_near - pre_far)
        sustained = _segment_mean(event, i - radius, i + radius + 1, float(event[i]))
        unwind = max(0.0, pre_near - post)
        sync = float(0.5 * audio[i] + 0.5 * flash[i])
        loc = float(locality[i])
        local_window = event[max(0, i - radius * 3):min(len(event), i + radius * 3 + 1)]
        peak_count = int(np.sum(
            (local_window[1:-1] >= local_window[:-2])
            & (local_window[1:-1] >= local_window[2:])
            & (local_window[1:-1] >= 0.48)
        )) if len(local_window) >= 3 else 0

        style = "IMPACT"
        story = 0.46 * float(event[i]) + 0.22 * sync + 0.16 * sustained + 0.16 * loc
        if relief >= 0.08:
            style = "CLEAR"
            story += min(relief / 0.22, 1.0) * 0.32
        elif pre_near >= 0.44 and unwind >= 0.16 and float(event[i]) >= 0.52:
            style = "TURNAROUND"
            story += 0.18 * pre_near + 0.20 * unwind
        elif buildup >= 0.10 and float(event[i]) >= 0.48:
            style = "BUILDUP"
            story += 0.24 * min(buildup / 0.28, 1.0)
        elif peak_count >= 3 and sustained >= 0.34 and float(scene[i]) < 0.72:
            style = "RHYTHM"
            story += 0.12 * min(peak_count / 5.0, 1.0)
        elif float(event[i]) < 0.50 and sustained >= 0.30 and float(scene[i]) < 0.48:
            style = "ASMR"
            story += 0.08
        if game_key == "BLINE":
            fx_support = _segment_mean(
                0.5 * flash + 0.5 * audio,
                i - radius,
                i + radius + 1,
                0.0,
            )
            if relief >= 0.08 or (
                float(event[i]) >= 0.62
                and float(flash[i]) >= 0.60
                and float(audio[i]) >= 0.50
                and fx_support >= 0.42
            ):
                style = "CLEAR"
                story += 0.16
            elif style == "IMPACT":
                # A single bright/audio spike is not enough to call a clear.
                # Keep uncertain B.Line moments captionless.
                style = "ASMR"
        elif game_key == "PN37":
            if float(event[i]) >= 0.52 and max(float(flash[i]), float(audio[i])) >= 0.50:
                style = "FEVER"
                story += 0.12

        menu_penalty = 0.0
        if float(scene[i]) > 0.88 and loc < 0.22 and post < 0.08:
            menu_penalty = 0.34
        story -= menu_penalty
        fx, fy, fc = _weighted_focus(signals, i, radius)
        candidates.append(
            EventCandidate(
                index=i,
                time=float(t[i]),
                score=float(np.clip(story, 0, 1.6)),
                style=style,
                event=float(event[i]),
                buildup=float(buildup),
                relief=float(relief),
                sustained=float(sustained),
                locality=loc,
                focus_x=fx,
                focus_y=fy,
                focus_confidence=fc,
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates, {"event": event, "safe_end": np.array([safe_end], np.float32)}
def _copy_for_candidate(game_key: str, c: EventCandidate) -> tuple[str, str]:
    if game_key == "BLINE":
        if c.style == "CLEAR":
            if c.relief >= 0.18:
                return "", "한 번에."
            return "", "됐다."
        if c.style == "TURNAROUND":
            return "여기.", "살았다."
    if game_key == "PN37" and c.style == "FEVER":
        return "", "왔다."
    if c.style == "CLEAR" and c.relief >= 0.20:
        return "", "한 번에."
    return "", ""


def _treatment_for(style: str, score: float) -> tuple[str, float, bool, float]:
    if style in {"TURNAROUND", "CLEAR"}:
        return "REVEAL", 0.16 if score >= 0.72 else 0.13, True, 0.52
    if style == "FEVER":
        return "PUNCH", 0.15, True, 0.46
    if style == "BUILDUP":
        return "BUILD", 0.12, False, 0.0
    if style == "IMPACT":
        return "PUNCH", 0.15 if score >= 0.70 else 0.12, score >= 0.72, 0.42
    if style == "RHYTHM":
        return "RHYTHM", 0.08, False, 0.0
    return "CLEAN", 0.07, False, 0.0


def _timing_for(style: str) -> tuple[float, float]:
    if style in {"CLEAR", "TURNAROUND"}:
        return 5.2, 3.0
    if style == "BUILDUP":
        return 5.8, 2.7
    if style == "FEVER":
        return 4.8, 2.6
    if style == "IMPACT":
        return 3.8, 2.8
    if style == "RHYTHM":
        return 4.2, 4.0
    return 4.0, 4.0
def plan_from_signals(
    game_key: str,
    signals: dict[str, np.ndarray],
    duration: float,
    avoid_styles: set[str] | None = None,
) -> CreativePlan:
    signals = dict(signals)
    t = signals["time"]
    if len(t) < 6:
        raise CreativeReject("not enough analyzable frames")

    n = len(t)
    signals.setdefault("focus_x", np.full(n, 0.5, np.float32))
    signals.setdefault("focus_y", np.full(n, 0.5, np.float32))
    signals.setdefault("focus_confidence", np.zeros(n, np.float32))
    signals.setdefault("locality", np.full(n, 0.5, np.float32))

    candidates, extra = _build_candidates(game_key, signals, duration)
    if not candidates:
        raise CreativeReject("no candidate event")
    best = candidates[0]
    avoid_styles = set(avoid_styles or ())
    if best.style in avoid_styles:
        for alternate in candidates[1:]:
            if (
                alternate.style not in avoid_styles
                and alternate.score >= best.score * 0.80
            ):
                best = alternate
                break
    if best.score < 0.46 or best.event < 0.34:
        raise CreativeReject(
            f"no director-worthy event: score={best.score:.3f}, event={best.event:.3f}"
        )

    pre, post = _timing_for(best.style)
    safe_end = float(extra["safe_end"][0])
    start = max(0.0, best.time - pre)
    target = min(12.5, max(7.0, pre + post))
    clip_duration = min(target, max(0.0, safe_end - start))
    if clip_duration < 4.5:
        raise CreativeReject("selected event too close to protected outro")
    payoff_at = best.time - start
    if payoff_at < 1.8:
        start = max(0.0, best.time - 2.6)
        clip_duration = min(target, max(0.0, safe_end - start))
        payoff_at = best.time - start

    event = extra["event"]
    open_mask = (t >= start) & (t <= start + 1.2)
    open_activity = float(np.mean(event[open_mask])) if np.any(open_mask) else 0.0

    treatment, zoom, cold_open, cold_len = _treatment_for(best.style, best.score)
    if not cold_open and open_activity < 0.10 and best.score < 0.62:
        raise CreativeReject("first 1.2s would be visually dead")

    lead, payoff = _copy_for_candidate(game_key, best)
    lead, payoff = _safe_copy(lead), _safe_copy(payoff)
    density = signals["density"]
    step = float(np.median(np.diff(t))) if len(t) > 1 else 1 / 6
    radius = max(2, int(round(0.9 / max(step, 1e-3))))
    db = _segment_mean(density, best.index - radius * 2, best.index, float(density[best.index]))
    da = _segment_mean(density, best.index + radius, best.index + radius * 4, float(density[best.index]))
    clear_drop = max(0.0, db - da)

    profile = get_profile(game_key)
    x0, y0, x1, y1 = profile.roi
    full_focus_x = x0 + best.focus_x * (x1 - x0)
    full_focus_y = y0 + best.focus_y * (y1 - y0)
    focus_conf = max(best.focus_confidence, profile.min_focus_scale)
    alt = tuple(f"{c.style}:{c.score:.2f}@{c.time:.1f}" for c in candidates[1:4])
    signature = (
        f"{best.style}:{round(best.time / 3.0)}:"
        f"{round(best.focus_x, 1)}:{round(best.focus_y, 1)}"
    )

    bline_pop = bool(
        game_key == "BLINE" and best.style == "CLEAR" and best.relief < 0.08
    )

    return CreativePlan(
        game_key=game_key,
        style=best.style,
        start=round(float(start), 3),
        duration=round(float(clip_duration), 3),
        payoff_at=round(float(payoff_at), 3),
        confidence=round(float(np.clip(best.score / 1.2, 0, 1)), 3),
        density_before=round(db, 3),
        density_after=round(da, 3),
        clear_drop=round(clear_drop, 3),
        lead_text=lead,
        payoff_text=payoff,
        cold_open=cold_open,
        cold_open_duration=cold_len,
        treatment=treatment,
        focus_x=round(float(np.clip(full_focus_x, 0.05, 0.95)), 3),
        focus_y=round(float(np.clip(full_focus_y, 0.05, 0.95)), 3),
        focus_confidence=round(float(np.clip(focus_conf, 0, 1)), 3),
        zoom_strength=round(float(zoom), 3),
        candidate_count=len(candidates),
        alternates=alt,
        signature=signature,
        reason=(
            f"director={best.style}, score={best.score:.3f}, event={best.event:.3f}, "
            f"buildup={best.buildup:.3f}, relief={best.relief:.3f}, "
            f"sustain={best.sustained:.3f}, locality={best.locality:.3f}, "
            f"bline_pop={int(bline_pop)}"
        ),
    )


def analyze_creative(
    path: str | Path,
    game_key: str,
    duration: float,
    avoid_styles: set[str] | None = None,
) -> CreativePlan:
    signals = sample_signals(path, game_key)
    return plan_from_signals(
        game_key, signals, duration, avoid_styles=avoid_styles
    )
