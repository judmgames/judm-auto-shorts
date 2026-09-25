from __future__ import annotations

import math
import subprocess
from dataclasses import asdict, dataclass, replace
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


class SemanticUnavailable(RuntimeError):
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
    story_clarity: float
    contrast: float
    sync: float
    menu_risk: float
    pre_level: float
    post_level: float
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
    focus_start_x: float
    focus_x: float
    focus_y: float
    focus_confidence: float
    zoom_strength: float
    candidate_count: int
    alternates: tuple[str, ...]
    signature: str
    story_clarity: float
    hook_strategy: str
    replay: bool
    replay_duration: float
    reason: str = ""
    semantic_used: bool = False
    semantic_scene: str = "unknown"
    semantic_event: str = "unknown"
    semantic_outcome: str = "unknown"
    semantic_confidence: float = 0.0
    semantic_reason: str = ""

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


def _crop_roi(
    frame: np.ndarray,
    game_key: str,
    roi: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = roi or get_profile(game_key).roi
    a, b, c, d = int(w * x0), int(h * y0), int(w * x1), int(h * y1)
    crop = frame[max(0, b):max(b + 1, d), max(0, a):max(a + 1, c)]
    return crop if crop.size else frame


def _weighted_quantile(weights: np.ndarray, q: float) -> float:
    weights = np.maximum(weights.astype(np.float64), 0.0)
    total = float(weights.sum())
    if total <= 1e-9:
        return q
    cdf = np.cumsum(weights) / total
    return float(np.searchsorted(cdf, q) / max(len(weights) - 1, 1))


def _detect_generic_roi(path: str | Path) -> tuple[float, float, float, float]:
    """Estimate the active gameplay region without knowing the game.

    The detector samples the recording sparsely and accumulates persistent
    temporal change.  One-off full-screen transitions are suppressed by a
    median aggregation, so HUD/menu flashes are less likely to become the ROI.
    """
    fallback = get_profile("GENERIC").roi
    cap = cv2.VideoCapture(str(path))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frame_count < 12:
        cap.release()
        return fallback

    positions = np.linspace(0.08, 0.84, 14)
    diffs: list[np.ndarray] = []
    prev = None
    for ratio in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * float(ratio)))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(
            cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA),
            cv2.COLOR_BGR2GRAY,
        )
        if prev is not None:
            diff = cv2.GaussianBlur(cv2.absdiff(gray, prev), (0, 0), 2.0)
            diffs.append(diff.astype(np.float32))
        prev = gray
    cap.release()

    if len(diffs) < 4:
        return fallback
    stack = np.stack(diffs, axis=0)
    heat = np.percentile(stack, 65, axis=0)
    heat = np.maximum(heat - np.percentile(heat, 52), 0.0)
    if float(heat.mean()) < 1.2 or float(heat.max()) < 8.0:
        return fallback

    xw = heat.sum(axis=0)
    yw = heat.sum(axis=1)
    x0 = _weighted_quantile(xw, 0.06)
    x1 = _weighted_quantile(xw, 0.94)
    y0 = _weighted_quantile(yw, 0.06)
    y1 = _weighted_quantile(yw, 0.94)

    pad_x = 0.07
    pad_y = 0.07
    x0, x1 = max(0.02, x0 - pad_x), min(0.98, x1 + pad_x)
    y0, y1 = max(0.02, y0 - pad_y), min(0.98, y1 + pad_y)

    # Do not over-crop unfamiliar games.  A human editor keeps context when
    # the detector is uncertain.
    if x1 - x0 < 0.48:
        mid = (x0 + x1) * 0.5
        x0, x1 = max(0.02, mid - 0.24), min(0.98, mid + 0.24)
        if x1 - x0 < 0.48:
            if x1 >= 0.97:
                x0 = max(0.02, x1 - 0.48)
            else:
                x1 = min(0.98, x0 + 0.48)
    if y1 - y0 < 0.48:
        mid = (y0 + y1) * 0.5
        y0, y1 = max(0.02, mid - 0.24), min(0.98, mid + 0.24)
        if y1 - y0 < 0.48:
            if y1 >= 0.97:
                y0 = max(0.02, y1 - 0.48)
            else:
                y1 = min(0.98, y0 + 0.48)

    return (float(x0), float(y0), float(x1), float(y1))


def _analysis_roi(
    path: str | Path,
    game_key: str,
) -> tuple[float, float, float, float]:
    profile = get_profile(game_key)
    if game_key != "GENERIC":
        return profile.roi
    return _detect_generic_roi(path)


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
    roi_spec = _analysis_roi(path, game_key)
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
        roi = _crop_roi(frame, game_key, roi_spec)
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
        "roi": np.asarray(roi_spec, np.float32),
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
    profile = get_profile(game_key)
    step = float(np.median(np.diff(t))) if len(t) > 1 else 1 / 6
    radius = max(2, int(round(0.9 / max(step, 1e-3))))

    event = np.clip(
        0.32 * motion + 0.18 * scene + 0.22 * audio + 0.12 * flash
        + 0.16 * (motion * locality),
        0, 1,
    )
    if len(event) >= 5:
        event = 0.70 * event + 0.30 * np.convolve(
            event, np.ones(5) / 5, mode="same"
        )

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
        pre_near = _segment_mean(
            event, i - radius * 2, i, float(event[i])
        )
        pre_far = _segment_mean(
            event, i - radius * 5, i - radius * 2, pre_near
        )
        post = _segment_mean(
            event, i + 1, i + radius * 3, float(event[i])
        )
        before_d = _segment_mean(
            density, i - radius * 2, i, float(density[i])
        )
        after_d = _segment_mean(
            density, i + radius, i + radius * 4, float(density[i])
        )
        relief = max(0.0, before_d - after_d)
        buildup = max(0.0, pre_near - pre_far)
        sustained = _segment_mean(
            event, i - radius, i + radius + 1, float(event[i])
        )
        unwind = max(0.0, pre_near - post)
        sync = float(0.5 * audio[i] + 0.5 * flash[i])
        loc = float(locality[i])
        contrast = float(
            np.clip(
                max(
                    relief * 2.6,
                    buildup * 1.8,
                    unwind * 1.8,
                    abs(pre_near - post),
                ),
                0,
                1,
            )
        )
        continuity = float(np.clip(1.0 - 0.45 * scene[i], 0, 1))
        local_window = event[
            max(0, i - radius * 3):min(len(event), i + radius * 3 + 1)
        ]
        peak_count = (
            int(
                np.sum(
                    (local_window[1:-1] >= local_window[:-2])
                    & (local_window[1:-1] >= local_window[2:])
                    & (local_window[1:-1] >= 0.46)
                )
            )
            if len(local_window) >= 3
            else 0
        )
        rhythmic_strength = float(
            np.clip((peak_count / 4.0) * (sustained / 0.5), 0, 1)
        )
        arc_strength = float(
            np.clip(
                max(
                    relief / 0.20,
                    buildup / 0.24,
                    unwind / 0.24,
                    rhythmic_strength,
                ),
                0,
                1,
            )
        )

        menu_risk = 0.0
        if float(scene[i]) > 0.88 and loc < 0.22 and post < 0.10:
            menu_risk = 0.40
        elif float(scene[i]) > 0.80 and loc < 0.30 and post < 0.14:
            menu_risk = 0.18

        story_clarity = float(
            np.clip(
                0.24 * float(event[i])
                + 0.17 * sync
                + 0.18 * arc_strength
                + 0.13 * loc
                + 0.11 * sustained
                + 0.08 * continuity
                + 0.09 * contrast,
                0,
                1,
            )
        )

        style = "IMPACT"
        if relief >= 0.08 and float(event[i]) >= 0.40:
            style = "CLEAR"
        elif (
            pre_near >= 0.38
            and unwind >= 0.13
            and float(event[i]) >= 0.42
        ):
            style = "TURNAROUND"
        elif buildup >= 0.09 and float(event[i]) >= 0.42:
            style = "BUILDUP"
        elif (
            peak_count >= 3
            and sustained >= 0.32
            and float(scene[i]) < 0.78
        ):
            style = "RHYTHM"
        elif (
            float(event[i]) < 0.50
            and sustained >= 0.28
            and sync < 0.55
            and float(scene[i]) < 0.50
        ):
            style = "ASMR"
        # Optional game profiles may improve confidence, but the universal
        # story detector above remains the source of truth.
        profile_bonus = 0.0
        if (
            profile.semantic_hint == "grid_clear"
            and style in {"IMPACT", "BUILDUP", "RHYTHM"}
            and float(event[i]) >= 0.58
            and sync >= 0.52
            and sustained >= 0.38
        ):
            style = "CLEAR"
            profile_bonus = 0.06
        elif (
            profile.semantic_hint == "grid_clear"
            and style == "IMPACT"
            and relief < 0.08
            and sustained < 0.38
        ):
            # A single flash/audio spike is not proof of a board clear.
            style = "ASMR"
        elif (
            profile.semantic_hint == "merge_chain"
            and style in {"IMPACT", "BUILDUP", "RHYTHM"}
            and float(event[i]) >= 0.52
            and sync >= 0.50
        ):
            style = "FEVER"
            profile_bonus = 0.05
        elif (
            profile.semantic_hint == "runner"
            and style in {"IMPACT", "TURNAROUND"}
            and loc >= 0.45
        ):
            profile_bonus = 0.03
        elif (
            profile.semantic_hint == "battle"
            and style == "IMPACT"
            and sustained >= 0.34
        ):
            profile_bonus = 0.03

        story_clarity = float(
            np.clip(story_clarity + profile_bonus, 0, 1)
        )
        story = (
            0.58 * story_clarity
            + 0.30 * float(event[i])
            + 0.08 * sustained
            + 0.04 * loc
            - menu_risk
        )

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
                story_clarity=story_clarity,
                contrast=contrast,
                sync=sync,
                menu_risk=menu_risk,
                pre_level=float(pre_near),
                post_level=float(post),
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates, {
        "event": event,
        "safe_end": np.array([safe_end], np.float32),
    }


def _copy_for_candidate(game_key: str, c: EventCandidate) -> tuple[str, str]:
    profile = get_profile(game_key)
    if c.style == "CLEAR":
        if c.relief >= 0.20:
            return "", "한 번에."
        if (
            profile.semantic_hint == "grid_clear"
            and (c.relief >= 0.08 or c.sync >= 0.56)
        ):
            return "", "됐다."
    if profile.semantic_hint == "merge_chain" and c.style == "FEVER":
        return "", "왔다."
    return "", ""


def _candidate_signature(c: EventCandidate) -> str:
    zx = int(np.clip(c.focus_x * 3.0, 0, 2.999))
    zy = int(np.clip(c.focus_y * 3.0, 0, 2.999))
    strength = "H" if c.story_clarity >= 0.66 else "M"
    return f"{c.style}:{zx}:{zy}:{strength}"


def _treatment_for(
    c: EventCandidate,
) -> tuple[str, float, bool, float, bool, float, str]:
    if c.style in {"TURNAROUND", "CLEAR"}:
        cold = c.story_clarity >= 0.54 and c.score >= 0.50
        return (
            "REVEAL",
            0.17 if c.story_clarity >= 0.68 else 0.13,
            cold,
            0.50 if cold else 0.0,
            False,
            0.0,
            "PAYOFF_FIRST" if cold else "STORY_FIRST",
        )
    if c.style == "FEVER":
        return "PUNCH", 0.15, True, 0.46, False, 0.0, "PAYOFF_FIRST"
    if c.style == "BUILDUP":
        return "BUILD", 0.12, False, 0.0, False, 0.0, "BUILD_TO_PAYOFF"
    if c.style == "IMPACT":
        replay = (
            c.score >= 0.60
            and c.story_clarity >= 0.55
            and c.sync >= 0.55
        )
        cold = (not replay) and c.score >= 0.72
        return (
            "PUNCH",
            0.17 if c.story_clarity >= 0.66 else 0.13,
            cold,
            0.42 if cold else 0.0,
            replay,
            0.56 if replay else 0.0,
            "MICRO_REPLAY" if replay else ("PAYOFF_FIRST" if cold else "ACTION_FIRST"),
        )
    if c.style == "RHYTHM":
        return "RHYTHM", 0.08, False, 0.0, False, 0.0, "FLOW"
    return "CLEAN", 0.06, False, 0.0, False, 0.0, "CLEAN"


def _timing_limits(style: str) -> tuple[float, float, float, float]:
    if style in {"CLEAR", "TURNAROUND"}:
        return 6.0, 2.0, 1.4, 3.4
    if style == "BUILDUP":
        return 7.0, 2.4, 1.3, 3.0
    if style == "FEVER":
        return 5.2, 1.8, 1.2, 2.8
    if style == "IMPACT":
        return 4.6, 1.6, 1.0, 2.4
    if style == "RHYTHM":
        return 5.0, 1.8, 2.0, 4.2
    return 4.8, 1.8, 1.6, 3.6


def _smart_window(
    best: EventCandidate,
    t: np.ndarray,
    event: np.ndarray,
    safe_end: float,
) -> tuple[float, float, str]:
    pre_max, pre_min, post_min, post_max = _timing_limits(best.style)
    smooth = event
    if len(event) >= 3:
        smooth = np.convolve(event, np.ones(3) / 3, mode="same")

    pre_mask = (
        (t >= max(0.0, best.time - pre_max))
        & (t <= max(0.0, best.time - pre_min))
    )
    pre_idx = np.where(pre_mask)[0]
    cut_reason = "fixed_fallback"
    if len(pre_idx):
        progress = np.linspace(0.0, 1.0, len(pre_idx), dtype=np.float32)
        # Prefer a quiet beat, but among similar beats prefer the later cut.
        cost = smooth[pre_idx] - 0.08 * progress
        start_i = int(pre_idx[int(np.argmin(cost))])
        start = max(0.0, float(t[start_i]) - 0.12)
        cut_reason = "pre_event_valley"
    else:
        start = max(0.0, best.time - pre_max)

    post_lo = best.time + post_min
    post_hi = min(safe_end, best.time + post_max)
    post_idx = np.where((t >= post_lo) & (t <= post_hi))[0]
    end = post_hi
    if len(post_idx):
        settle_threshold = min(
            0.24, max(0.11, 0.75 * best.post_level)
        )
        for idx in post_idx:
            hi = min(len(smooth), idx + 3)
            if float(np.mean(smooth[idx:hi])) <= settle_threshold:
                end = min(safe_end, float(t[idx]) + 0.22)
                cut_reason += "+post_settle"
                break

    min_duration = 5.2
    max_duration = 13.0
    if end - start < min_duration:
        missing = min_duration - (end - start)
        start = max(0.0, start - missing * 0.65)
        end = min(safe_end, end + missing * 0.35)
    if end - start > max_duration:
        start = max(0.0, end - max_duration)
    if best.time - start < 1.55:
        start = max(0.0, best.time - 1.8)
    end = max(end, min(safe_end, best.time + 1.0))
    return start, max(0.0, end - start), cut_reason


def plan_from_signals(
    game_key: str,
    signals: dict[str, np.ndarray],
    duration: float,
    avoid_styles: set[str] | None = None,
    avoid_signatures: set[str] | None = None,
    preferred_signature: str | None = None,
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

    avoid_styles = set(avoid_styles or ())
    avoid_signatures = set(avoid_signatures or ())
    best = candidates[0]
    if preferred_signature:
        for candidate in candidates:
            if (
                _candidate_signature(candidate) == preferred_signature
                and candidate.score >= candidates[0].score * 0.68
            ):
                best = candidate
                break
    if (
        best.style in avoid_styles
        or _candidate_signature(best) in avoid_signatures
    ):
        for alternate in candidates[1:]:
            if (
                alternate.style not in avoid_styles
                and _candidate_signature(alternate) not in avoid_signatures
                and alternate.score >= best.score * 0.78
            ):
                best = alternate
                break

    if (
        best.score < 0.44
        or best.event < 0.32
        or best.story_clarity < 0.34
        or best.menu_risk >= 0.38
    ):
        raise CreativeReject(
            "no director-worthy event: "
            f"score={best.score:.3f}, event={best.event:.3f}, "
            f"clarity={best.story_clarity:.3f}, menu={best.menu_risk:.3f}"
        )

    event = extra["event"]
    safe_end = float(extra["safe_end"][0])
    start, clip_duration, cut_reason = _smart_window(
        best, t, event, safe_end
    )
    if clip_duration < 4.5:
        raise CreativeReject("selected event too close to protected outro")
    payoff_at = best.time - start

    (
        treatment,
        zoom,
        cold_open,
        cold_len,
        replay,
        replay_duration,
        hook_strategy,
    ) = _treatment_for(best)

    if replay and clip_duration + replay_duration > 15.2:
        replay = False
        replay_duration = 0.0
        hook_strategy = "ACTION_FIRST"

    clip_end = start + clip_duration
    open_mask = (t >= start) & (t <= start + 1.2)
    open_activity = (
        float(np.mean(event[open_mask])) if np.any(open_mask) else 0.0
    )

    if not cold_open and open_activity < 0.085:
        # A human editor would not keep a dead establishing beat just because
        # it is technically a clean cut. Tighten to the first visible rise
        # close to the story, while preserving enough setup before payoff.
        rise_mask = (
            (t >= max(start, best.time - 3.2))
            & (t <= max(start, best.time - 1.0))
            & (event >= 0.10)
        )
        rise_idx = np.where(rise_mask)[0]
        if len(rise_idx):
            start = max(start, float(t[int(rise_idx[0])]) - 0.22)
            if clip_end - start < 5.2:
                clip_end = min(safe_end, start + 5.2)
            clip_duration = max(0.0, clip_end - start)
            payoff_at = best.time - start
            open_mask = (t >= start) & (t <= start + 1.2)
            open_activity = (
                float(np.mean(event[open_mask])) if np.any(open_mask) else 0.0
            )

    if not cold_open and open_activity < 0.085:
        # If the setup has no hook, promote a clearly verified payoff or a
        # strong audiovisual impact. This is preferable to a dead opening,
        # while still rejecting weak/ambiguous footage.
        payoff_is_verified = (
            best.style in {"CLEAR", "TURNAROUND"}
            and (best.relief >= 0.08 or best.contrast >= 0.18)
        )
        impact_is_strong = best.event >= 0.55 and best.sync >= 0.48
        if (
            payoff_is_verified
            or impact_is_strong
            or (best.story_clarity >= 0.46 and best.score >= 0.48)
        ):
            cold_open = True
            cold_len = 0.42
            replay = False
            replay_duration = 0.0
            hook_strategy = "PAYOFF_FIRST"
        else:
            raise CreativeReject("first 1.2s would be visually dead")

    lead, payoff = _copy_for_candidate(game_key, best)
    lead, payoff = _safe_copy(lead), _safe_copy(payoff)
    density = signals["density"]
    step = float(np.median(np.diff(t))) if len(t) > 1 else 1 / 6
    radius = max(2, int(round(0.9 / max(step, 1e-3))))
    db = _segment_mean(
        density,
        best.index - radius * 2,
        best.index,
        float(density[best.index]),
    )
    da = _segment_mean(
        density,
        best.index + radius,
        best.index + radius * 4,
        float(density[best.index]),
    )
    clear_drop = max(0.0, db - da)

    profile = get_profile(game_key)
    roi_arr = signals.get("roi")
    if roi_arr is not None and len(roi_arr) == 4:
        x0, y0, x1, y1 = [float(v) for v in roi_arr]
    else:
        x0, y0, x1, y1 = profile.roi
    full_focus_x = x0 + best.focus_x * (x1 - x0)
    full_focus_y = y0 + best.focus_y * (y1 - y0)

    start_idx = int(np.searchsorted(t, min(best.time, start + 0.8)))
    start_idx = max(0, min(len(t) - 1, start_idx))
    start_fx_roi, _, start_fc = _weighted_focus(
        signals, start_idx, radius
    )
    if start_fc < 0.10:
        start_fx_roi = best.focus_x
    full_focus_start_x = x0 + start_fx_roi * (x1 - x0)

    focus_conf = max(best.focus_confidence, profile.min_focus_scale)
    alt = tuple(
        f"{c.style}:{c.score:.2f}:{c.story_clarity:.2f}@{c.time:.1f}"
        for c in candidates[1:4]
    )
    signature = _candidate_signature(best)
    semantic_clear = bool(
        profile.semantic_hint == "grid_clear"
        and best.style == "CLEAR"
        and best.relief < 0.08
    )

    return CreativePlan(
        game_key=game_key,
        style=best.style,
        start=round(float(start), 3),
        duration=round(float(clip_duration), 3),
        payoff_at=round(float(payoff_at), 3),
        confidence=round(float(np.clip(best.score / 1.0, 0, 1)), 3),
        density_before=round(db, 3),
        density_after=round(da, 3),
        clear_drop=round(clear_drop, 3),
        lead_text=lead,
        payoff_text=payoff,
        cold_open=cold_open,
        cold_open_duration=cold_len,
        treatment=treatment,
        focus_start_x=round(
            float(np.clip(full_focus_start_x, 0.05, 0.95)), 3
        ),
        focus_x=round(float(np.clip(full_focus_x, 0.05, 0.95)), 3),
        focus_y=round(float(np.clip(full_focus_y, 0.05, 0.95)), 3),
        focus_confidence=round(float(np.clip(focus_conf, 0, 1)), 3),
        zoom_strength=round(float(zoom), 3),
        candidate_count=len(candidates),
        alternates=alt,
        signature=signature,
        story_clarity=round(float(best.story_clarity), 3),
        hook_strategy=hook_strategy,
        replay=replay,
        replay_duration=round(float(replay_duration), 3),
        reason=(
            f"director={best.style}, treatment={treatment}, "
            f"hook={hook_strategy}, score={best.score:.3f}, "
            f"clarity={best.story_clarity:.3f}, event={best.event:.3f}, "
            f"contrast={best.contrast:.3f}, sync={best.sync:.3f}, "
            f"buildup={best.buildup:.3f}, relief={best.relief:.3f}, "
            f"sustain={best.sustained:.3f}, locality={best.locality:.3f}, "
            f"cut={cut_reason}, semantic_clear={int(semantic_clear)}"
        ),
    )


def _apply_semantic_hint(plan: CreativePlan, hint) -> CreativePlan:
    reason = getattr(hint, "reason", "") or "unknown"
    available = bool(getattr(hint, "available", False))
    scene = getattr(hint, "scene", "unknown")
    event = getattr(hint, "event", "unknown")
    outcome = getattr(hint, "outcome", "unknown")
    confidence = float(getattr(hint, "confidence", 0.0) or 0.0)

    base = replace(
        plan,
        semantic_used=available,
        semantic_scene=scene,
        semantic_event=event,
        semantic_outcome=outcome,
        semantic_confidence=round(confidence, 3),
        semantic_reason=reason,
    )
    if not available:
        return base

    if confidence >= 0.80 and scene in {"menu", "loading"}:
        raise CreativeReject(
            f"semantic gate rejected non-gameplay scene: {scene}"
        )

    if confidence < 0.60:
        return replace(
            base,
            reason=plan.reason + f", semantic=observe:{scene}/{event}/{outcome}",
        )

    new_style = plan.style
    new_treatment = plan.treatment
    new_hook = plan.hook_strategy
    new_zoom = plan.zoom_strength
    new_cold = plan.cold_open
    new_cold_len = plan.cold_open_duration
    new_replay = plan.replay
    new_replay_duration = plan.replay_duration
    lead_text = plan.lead_text
    payoff_text = plan.payoff_text
    clarity = plan.story_clarity
    # Semantic story evidence is the director-level source of truth for every
    # game. Profiles may improve detection/framing, but must never override a
    # clearly observed story just because the game is registered.
    if scene == "gameplay":
        if event == "clear" and outcome in {"success", "recovery"}:
            new_style = "CLEAR"
            new_treatment = "REVEAL"
            new_zoom = max(new_zoom, 0.13)
            new_cold = True
            new_cold_len = max(new_cold_len, 0.44)
            new_replay = False
            new_replay_duration = 0.0
            new_hook = "PAYOFF_FIRST"
            clarity = min(1.0, clarity + 0.08)
        elif event == "danger" and outcome == "recovery":
            new_style = "TURNAROUND"
            new_treatment = "REVEAL"
            new_zoom = max(new_zoom, 0.13)
            new_cold = True
            new_cold_len = max(new_cold_len, 0.42)
            new_replay = False
            new_replay_duration = 0.0
            new_hook = "PAYOFF_FIRST"
            clarity = min(1.0, clarity + 0.07)
        elif event == "danger" and outcome == "failure":
            new_style = "NEAR_FAIL"
            new_treatment = "PUNCH"
            new_zoom = max(new_zoom, 0.14)
            new_cold = False
            new_cold_len = 0.0
            new_replay = confidence >= 0.80
            new_replay_duration = 0.52 if new_replay else 0.0
            new_hook = "MICRO_REPLAY" if new_replay else "ACTION_FIRST"
            lead_text = ""
            payoff_text = ""
            clarity = min(1.0, clarity + 0.06)
        elif event == "impact" and outcome == "failure":
            new_style = "FAIL"
            new_treatment = "PUNCH"
            new_zoom = max(new_zoom, 0.15)
            new_cold = False
            new_cold_len = 0.0
            new_replay = confidence >= 0.80
            new_replay_duration = 0.50 if new_replay else 0.0
            new_hook = "MICRO_REPLAY" if new_replay else "ACTION_FIRST"
            lead_text = ""
            payoff_text = ""
            clarity = min(1.0, clarity + 0.05)
        elif event == "chain":
            if new_style not in {"CLEAR", "TURNAROUND"}:
                new_style = "RHYTHM"
                new_treatment = "RHYTHM"
                new_hook = "FLOW"
                new_cold = False
                new_cold_len = 0.0
                new_replay = False
                new_replay_duration = 0.0
                clarity = min(1.0, clarity + 0.05)
        elif event == "impact" and new_style in {"ASMR", "BUILDUP"}:
            new_style = "IMPACT"
            new_treatment = "PUNCH"
            new_zoom = max(new_zoom, 0.12)
            new_hook = "ACTION_FIRST"
            clarity = min(1.0, clarity + 0.04)

        if outcome == "failure" and new_style == "CLEAR":
            new_style = "IMPACT"
            new_treatment = "PUNCH"
            lead_text = ""
            payoff_text = ""
            new_hook = "ACTION_FIRST"
            new_cold = False
            new_cold_len = 0.0
            new_replay = False
            new_replay_duration = 0.0

    signature = plan.signature
    if new_style != plan.style and ":" in signature:
        signature = new_style + ":" + signature.split(":", 1)[1]

    semantic_note = (
        f"{scene}/{event}/{outcome}:{confidence:.2f}"
    )
    return replace(
        base,
        style=new_style,
        treatment=new_treatment,
        hook_strategy=new_hook,
        zoom_strength=round(float(new_zoom), 3),
        cold_open=new_cold,
        cold_open_duration=round(float(new_cold_len), 3),
        replay=new_replay,
        replay_duration=round(float(new_replay_duration), 3),
        lead_text=lead_text,
        payoff_text=payoff_text,
        story_clarity=round(float(clarity), 3),
        signature=signature,
        reason=plan.reason + f", semantic={semantic_note}",
    )


def _semantic_alignment_score(candidate: EventCandidate, hint) -> float:
    score = float(candidate.score)
    if not bool(getattr(hint, "available", False)):
        return score

    confidence = float(getattr(hint, "confidence", 0.0) or 0.0)
    scene = getattr(hint, "scene", "unknown")
    event = getattr(hint, "event", "unknown")
    outcome = getattr(hint, "outcome", "unknown")

    if scene in {"menu", "loading"}:
        return score - 1.20 * confidence
    if scene == "gameplay":
        score += 0.06 * confidence
    elif scene == "result":
        score -= 0.08 * confidence

    event_match = {
        "clear": {"CLEAR", "TURNAROUND"},
        "impact": {"IMPACT", "TURNAROUND"},
        "danger": {"TURNAROUND", "BUILDUP", "IMPACT"},
        "chain": {"RHYTHM", "BUILDUP", "FEVER", "CLEAR"},
        "movement": {"RHYTHM", "BUILDUP", "IMPACT"},
    }
    if event in event_match:
        score += (0.16 if candidate.style in event_match[event] else 0.07) * confidence
    elif event == "transition":
        score -= 0.16 * confidence

    if outcome == "success":
        score += 0.10 * confidence
    elif outcome == "recovery":
        score += 0.14 * confidence
    elif outcome == "failure":
        if candidate.style == "CLEAR":
            score -= 0.28 * confidence
        elif candidate.style in {"IMPACT", "TURNAROUND"}:
            score += 0.05 * confidence

    return score


def analyze_creative(
    path: str | Path,
    game_key: str,
    duration: float,
    avoid_styles: set[str] | None = None,
    avoid_signatures: set[str] | None = None,
) -> CreativePlan:
    signals = sample_signals(path, game_key)
    preferred_signature = None
    preferred_hint = None

    try:
        from .semantic import analyze_semantic, semantic_enabled, semantic_required

        if semantic_enabled():
            candidates, _ = _build_candidates(game_key, signals, duration)
            ranked = []
            for candidate in candidates[:3]:
                signature = _candidate_signature(candidate)
                if (
                    signature in set(avoid_signatures or ())
                    and candidate.score < candidates[0].score * 0.92
                ):
                    continue
                hint = analyze_semantic(path, candidate.time)
                ranked.append(
                    (_semantic_alignment_score(candidate, hint), candidate, hint)
                )
            if ranked:
                ranked.sort(key=lambda item: item[0], reverse=True)
                _, winner, preferred_hint = ranked[0]
                preferred_signature = _candidate_signature(winner)
    except Exception:
        preferred_signature = None
        preferred_hint = None

    plan = plan_from_signals(
        game_key,
        signals,
        duration,
        avoid_styles=avoid_styles,
        avoid_signatures=avoid_signatures,
        preferred_signature=preferred_signature,
    )

    try:
        from .semantic import analyze_semantic, semantic_enabled, semantic_required

        if not semantic_enabled():
            return plan
        if preferred_hint is None or (
            preferred_signature is not None
            and plan.signature != preferred_signature
        ):
            preferred_hint = analyze_semantic(
                path,
                plan.start + plan.payoff_at,
            )
        if semantic_required() and not bool(
            getattr(preferred_hint, "available", False)
        ):
            reason = getattr(preferred_hint, "reason", "unavailable")
            raise SemanticUnavailable(
                f"semantic director required but unavailable: {reason}"
            )
        return _apply_semantic_hint(plan, preferred_hint)
    except SemanticUnavailable:
        raise
    except CreativeReject:
        raise
    except Exception as exc:
        return replace(
            plan,
            semantic_reason=f"fallback:{type(exc).__name__}",
            reason=plan.reason + f", semantic_fallback={type(exc).__name__}",
        )
