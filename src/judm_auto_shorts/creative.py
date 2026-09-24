from __future__ import annotations

import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


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

ROI = {
    "BLINE": (0.23, 0.08, 0.77, 0.94),
    "PN37": (0.06, 0.20, 0.94, 0.84),
    "SLIME": (0.08, 0.10, 0.92, 0.90),
    "FAMMER": (0.08, 0.08, 0.92, 0.92),
    "GENERIC": (0.12, 0.10, 0.88, 0.90),
}


class CreativeReject(RuntimeError):
    pass


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
    x0, y0, x1, y1 = ROI.get(game_key, ROI["GENERIC"])
    a, b, c, d = int(w * x0), int(h * y0), int(w * x1), int(h * y1)
    crop = frame[max(0, b):max(b + 1, d), max(0, a):max(a + 1, c)]
    return crop if crop.size else frame


def sample_signals(path: str | Path, game_key: str, hz: float = 6.0) -> dict[str, np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(round(fps / hz)), 1)
    times, motion, scene, flash, density = [], [], [], [], []
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
        else:
            mot = float(cv2.absdiff(gray, prev_gray).mean()) / 255.0
            scn = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
            mean_v = float(val.mean()) / 255.0
            fl = max(0.0, mean_v - float(prev_value))
        times.append(i / fps)
        motion.append(mot)
        scene.append(scn)
        flash.append(fl)
        density.append(occ)
        prev_gray, prev_hist, prev_value = gray, hist, float(val.mean()) / 255.0
        i += 1
    cap.release()
    t = np.asarray(times, np.float32)
    m = _norm(np.asarray(motion, np.float32))
    s = _norm(np.asarray(scene, np.float32))
    f = _norm(np.asarray(flash, np.float32))
    d = np.asarray(density, np.float32)
    at, av = _audio_scores(path, hz)
    a = np.interp(t, at, _norm(av), left=0, right=0).astype(np.float32) if len(at) else np.zeros_like(t)
    return {"time": t, "motion": m, "scene": s, "flash": f, "density": d, "audio": a}


def _window_mean(x: np.ndarray, center: int, radius: int, before: bool) -> float:
    if before:
        seg = x[max(0, center - radius):center]
    else:
        seg = x[center + 1:min(len(x), center + 1 + radius)]
    return float(np.mean(seg)) if len(seg) else float(x[center])


def plan_from_signals(game_key: str, signals: dict[str, np.ndarray], duration: float) -> CreativePlan:
    t = signals["time"]
    if len(t) < 6:
        raise CreativeReject("not enough analyzable frames")
    motion = signals["motion"]
    scene = signals["scene"]
    flash = signals["flash"]
    density = signals["density"]
    audio = signals["audio"]
    step = float(np.median(np.diff(t))) if len(t) > 1 else 1 / 6
    radius = max(2, int(round(0.9 / max(step, 1e-3))))
    event = np.clip(0.43 * motion + 0.25 * scene + 0.18 * audio + 0.14 * flash, 0, 1)
    if len(event) >= 5:
        event = 0.75 * event + 0.25 * np.convolve(event, np.ones(5) / 5, mode="same")

    drops = np.zeros_like(event)
    before_d = np.zeros_like(event)
    after_d = np.zeros_like(event)
    late_after_d = np.zeros_like(event)
    for i in range(len(event)):
        before_d[i] = _window_mean(density, i, radius, True)
        after_d[i] = _window_mean(density, i, radius, False)

        # Clear effects can temporarily fill the board ROI with bright particles
        # and make the immediate post-event frame look just as "occupied".
        # Compare again after the effect has had time to disappear.
        late_start = min(len(density), i + 1 + radius)
        late_end = min(len(density), i + 1 + radius * 3)
        late_seg = density[late_start:late_end]
        late_after_d[i] = float(np.mean(late_seg)) if len(late_seg) else after_d[i]

        effective_after = min(float(after_d[i]), float(late_after_d[i]))
        drops[i] = max(0.0, float(before_d[i]) - effective_after)
    drop_score = np.clip(drops / 0.22, 0, 1)
    payoff = np.clip(0.58 * event + 0.30 * drop_score + 0.12 * np.maximum(audio, flash), 0, 1)

    # Long screen recordings commonly end on retry/lobby/result UI. Keep a
    # generous tail guard and rank gameplay-shaped events above raw flashes.
    if duration >= 60:
        end_guard = 8.0
    elif duration >= 20:
        end_guard = 4.0
    else:
        end_guard = 1.5
    safe_end = max(3.0, duration - end_guard)
    valid = (t >= 2.0) & (t <= max(2.0, safe_end - 1.2))
    if not np.any(valid):
        valid = (t >= 0.5) & (t <= max(0.5, duration - 0.8))

    post_activity = np.zeros_like(event)
    for i in range(len(event)):
        seg = event[i + 1:min(len(event), i + 1 + radius * 2)]
        post_activity[i] = float(np.mean(seg)) if len(seg) else 0.0

    story_bonus = np.zeros_like(event)
    story_bonus += np.where(drops >= 0.16, 0.34, np.where(drops >= 0.10, 0.22, 0.0))
    if game_key == "PN37":
        fever_like = (event >= 0.48) & (np.maximum(flash, audio) >= 0.45)
        story_bonus += np.where(fever_like, 0.18, 0.0)
    menu_penalty = np.where((post_activity < 0.045) & (drops < 0.08), 0.30, 0.0)
    ranked = payoff + story_bonus - menu_penalty
    masked = np.where(valid, ranked, -1)
    idx = int(np.argmax(masked))

    confidence = float(payoff[idx])
    clear_drop = float(drops[idx])
    db = float(before_d[idx])
    da = min(float(after_d[idx]), float(late_after_d[idx]))
    peak_event = float(event[idx])
    peak_flash = float(flash[idx])
    peak_audio = float(audio[idx])

    if confidence < 0.34 and peak_event < 0.42:
        raise CreativeReject(f"no strong payoff: confidence={confidence:.3f}")

    # Only attach semantic copy when the visual evidence supports it.
    # A bright success effect used to be mislabeled as a mistake, so B.Line
    # now defaults to a clear or captionless satisfying clip.
    if clear_drop >= 0.08:
        style = "CLEAR"
        if clear_drop >= 0.20:
            lead, payoff_text = "이거다.", "한 번에."
        else:
            lead, payoff_text = "여기.", "됐다."
        pre, target = 5.8, 9.0
    elif game_key == "PN37" and peak_event >= 0.48 and max(peak_flash, peak_audio) >= 0.45:
        style = "FEVER"
        lead, payoff_text = "하나만 더.", "됐다."
        pre, target = 5.2, 8.5
    elif peak_event >= 0.43:
        style = "ASMR"
        lead = payoff_text = ""
        pre, target = 4.8, 10.0
    else:
        raise CreativeReject("activity exists but no story-worthy event")

    payoff_time = float(t[idx])
    start = max(0.0, payoff_time - pre)
    remaining = max(0.0, safe_end - start)
    clip_duration = min(target, remaining)
    if clip_duration < 3.0:
        raise CreativeReject("selected event is too close to the protected outro")
    payoff_at = payoff_time - start
    if payoff_at < 2.0:
        start = max(0.0, payoff_time - 2.8)
        clip_duration = min(target, max(0.0, safe_end - start))
        payoff_at = payoff_time - start

    cold_open = style in {"RESCUE", "CLEAR", "FEVER", "MISTAKE"} and duration >= 5.0
    cold_len = 0.58 if cold_open else 0.0
    lead = _safe_copy(lead)
    payoff_text = _safe_copy(payoff_text)

    if not cold_open:
        open_mask = (t >= start) & (t <= start + 1.2)
        open_activity = float(np.mean(event[open_mask])) if np.any(open_mask) else 0.0
        if open_activity < 0.10 and confidence < 0.48:
            raise CreativeReject("first 1.2s would be visually dead")

    return CreativePlan(
        game_key=game_key,
        style=style,
        start=round(float(start), 3),
        duration=round(float(clip_duration), 3),
        payoff_at=round(float(payoff_at), 3),
        confidence=round(confidence, 3),
        density_before=round(db, 3),
        density_after=round(da, 3),
        clear_drop=round(clear_drop, 3),
        lead_text=lead,
        payoff_text=payoff_text,
        cold_open=cold_open,
        cold_open_duration=cold_len,
        reason=f"event={peak_event:.3f}, flash={peak_flash:.3f}, audio={peak_audio:.3f}",
    )


def analyze_creative(path: str | Path, game_key: str, duration: float) -> CreativePlan:
    signals = sample_signals(path, game_key)
    return plan_from_signals(game_key, signals, duration)

