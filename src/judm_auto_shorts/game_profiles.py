from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameProfile:
    key: str
    roi: tuple[float, float, float, float]
    semantic_hint: str = ""
    min_focus_scale: float = 0.0


PROFILES = {
    "BLINE": GameProfile(
        "BLINE", (0.20, 0.07, 0.80, 0.94),
        semantic_hint="grid_clear", min_focus_scale=0.35,
    ),
    "PN37": GameProfile(
        "PN37", (0.06, 0.18, 0.94, 0.86),
        semantic_hint="merge_chain", min_focus_scale=0.18,
    ),
    "SLIME": GameProfile(
        "SLIME", (0.06, 0.08, 0.94, 0.92),
        semantic_hint="runner", min_focus_scale=0.12,
    ),
    "FAMMER": GameProfile(
        "FAMMER", (0.05, 0.07, 0.95, 0.93),
        semantic_hint="battle", min_focus_scale=0.12,
    ),
    "GENERIC": GameProfile(
        "GENERIC", (0.04, 0.04, 0.96, 0.96),
        semantic_hint="", min_focus_scale=0.0,
    ),
}


def get_profile(game_key: str) -> GameProfile:
    return PROFILES.get(game_key, PROFILES["GENERIC"])
