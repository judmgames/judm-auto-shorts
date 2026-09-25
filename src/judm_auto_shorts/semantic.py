from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2


MODEL_ID = os.getenv(
    "JUDM_SEMANTIC_MODEL",
    "HuggingFaceTB/SmolVLM2-256M-Video-Instruct",
)

SCENES = {"gameplay", "menu", "result", "loading", "unknown"}
EVENTS = {
    "clear", "impact", "danger", "chain", "movement", "transition", "unknown"
}
OUTCOMES = {"success", "failure", "recovery", "unknown"}
CONFIDENCE = {"low": 0.35, "medium": 0.60, "high": 0.85}
PROMPT = """Review these three frames in chronological order.
Choose exactly ONE word for each field. Do not explain. Do not copy the option
lists and never output the | character.

SCENE allowed words: gameplay, menu, result, loading, unknown
EVENT allowed words: clear, impact, danger, chain, movement, transition, unknown
OUTCOME allowed words: success, failure, recovery, unknown
CONFIDENCE allowed words: low, medium, high

Return exactly one line in this format:
SCENE=<word>; EVENT=<word>; OUTCOME=<word>; CONFIDENCE=<word>

Use only what the frames visibly support. If unsure, use unknown.
"""


@dataclass(frozen=True)
class SemanticHint:
    available: bool = False
    scene: str = "unknown"
    event: str = "unknown"
    outcome: str = "unknown"
    confidence: float = 0.0
    raw: str = ""
    reason: str = ""
    load_seconds: float = 0.0
    infer_seconds: float = 0.0
def semantic_enabled() -> bool:
    return os.getenv("JUDM_SEMANTIC_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def semantic_required() -> bool:
    return os.getenv("JUDM_SEMANTIC_REQUIRED", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _pick(text: str, key: str, allowed: set[str]) -> str:
    cleaned = (
        (text or "")
        .replace("**", "")
        .replace(chr(96), "")
        .replace('"', "")
        .replace("'", "")
    )
    match = re.search(
        rf"\b{re.escape(key)}\s*[:=]\s*([A-Za-z_]+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    value = match.group(1).lower() if match else "unknown"
    return value if value in allowed else "unknown"


def parse_semantic_response(text: str) -> SemanticHint:
    scene = _pick(text, "SCENE", SCENES)
    event = _pick(text, "EVENT", EVENTS)
    outcome = _pick(text, "OUTCOME", OUTCOMES)
    conf_name = _pick(text, "CONFIDENCE", set(CONFIDENCE))
    confidence = CONFIDENCE.get(conf_name, 0.0)
    meaningful = event != "unknown" or outcome != "unknown"
    return SemanticHint(
        available=meaningful and confidence > 0,
        scene=scene,
        event=event,
        outcome=outcome,
        confidence=confidence,
        raw=(text or "").strip()[:300],
        reason="parsed" if meaningful else "unparseable",
    )
def _frame_paths(
    video_path: str | Path,
    center: float,
    directory: Path,
) -> list[str]:
    cap = cv2.VideoCapture(str(video_path))
    duration_ms = max(0.0, cap.get(cv2.CAP_PROP_FRAME_COUNT)) / max(
        cap.get(cv2.CAP_PROP_FPS) or 30.0, 1.0
    ) * 1000.0
    paths: list[str] = []
    for idx, offset in enumerate((-0.75, 0.0, 0.80)):
        sec = max(0.0, center + offset)
        if duration_ms:
            sec = min(sec, max(0.0, duration_ms / 1000.0 - 0.05))
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        h, w = frame.shape[:2]
        scale = min(1.0, 640.0 / max(h, w, 1))
        if scale < 1.0:
            frame = cv2.resize(
                frame,
                (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        target = directory / f"semantic_{idx}.jpg"
        if cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            paths.append(str(target))
    cap.release()
    return paths
@lru_cache(maxsize=1)
def _load_model():
    start = time.perf_counter()
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32,
    )
    model.eval()
    return processor, model, time.perf_counter() - start


def analyze_semantic(
    video_path: str | Path,
    center: float,
) -> SemanticHint:
    if not semantic_enabled():
        return SemanticHint(reason="disabled")

    try:
        processor, model, load_seconds = _load_model()
        with tempfile.TemporaryDirectory(prefix="judm_semantic_") as td:
            frame_paths = _frame_paths(video_path, center, Path(td))
            if len(frame_paths) < 2:
                return SemanticHint(reason="insufficient_frames")
            content = [
                {"type": "image", "path": p}
                for p in frame_paths
            ]
            content.append({"type": "text", "text": PROMPT})
            conversation = [{"role": "user", "content": content}]

            infer_start = time.perf_counter()
            inputs = processor.apply_chat_template(
                conversation,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(model.device)
            generated = model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=96,
            )
            prompt_len = inputs["input_ids"].shape[1]
            decoded = processor.batch_decode(
                generated[:, prompt_len:],
                skip_special_tokens=True,
            )[0]
            infer_seconds = time.perf_counter() - infer_start

        parsed = parse_semantic_response(decoded)
        reason = parsed.reason
        if not parsed.available and parsed.raw:
            compact = parsed.raw.replace("\n", " ").strip()[:160]
            reason = f"{reason}:{compact}"
        return SemanticHint(
            available=parsed.available,
            scene=parsed.scene,
            event=parsed.event,
            outcome=parsed.outcome,
            confidence=parsed.confidence,
            raw=parsed.raw,
            reason=reason,
            load_seconds=round(load_seconds, 3),
            infer_seconds=round(infer_seconds, 3),
        )
    except Exception as exc:
        detail = str(exc).replace("\n", " ").strip()[:180]
        suffix = f":{detail}" if detail else ""
        return SemanticHint(
            reason=f"fallback:{type(exc).__name__}{suffix}",
        )
