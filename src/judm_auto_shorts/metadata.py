from __future__ import annotations

from dataclasses import dataclass


LABEL = {
    "SLIME": "뿅뿅슬라임",
    "PN37": "피지컬넘버37",
    "BLINE": "B.Line POP",
    "FAMMER": "FammerWar",
    "GENERIC": "JUD.M Games",
}


@dataclass(frozen=True)
class Metadata:
    game_key: str
    game_label: str
    hook: str
    youtube_title: str
    youtube_description: str
    instagram_caption: str
    tiktok_caption: str


def detect_game(name: str) -> str:
    u = name.upper()
    if any(x in u for x in ("SLIME", "BBYONG", "뿅")):
        return "SLIME"
    if any(x in u for x in ("PN37", "PHYSICAL", "NUMBER37", "피지컬")):
        return "PN37"
    if any(x in u for x in ("BLINE", "B.LINE", "LINEPOP")):
        return "BLINE"
    if any(x in u for x in ("FAMMER", "FARMERWAR", "파머")):
        return "FAMMER"
    return "GENERIC"


def _scene_copy(style: str, clear_drop: float) -> tuple[str, str]:
    if style == "RESCUE":
        return "한 칸이 살렸네", "거의 막혔는데 한 수로 열렸다."
    if style == "CLEAR":
        if clear_drop >= 0.24:
            return "이건 좀 시원했다", "한 번에 정리되는 순간."
        return "여기서 딱 풀렸다", "막히던 판이 여기서 풀렸다."
    if style == "FEVER":
        return "여기서 터짐", "분위기가 바뀌는 순간."
    if style == "MISTAKE":
        return "아, 여기서 꼬였네", "다시 보니까 여기였다."
    if style == "ASMR":
        return "이 장면은 소리까지 좋다", "말보다 플레이가 더 잘 보이는 장면."
    return "이 장면은 남겼다", "플레이에서 제일 변화가 컸던 순간."


def make_metadata(filename: str, creative: dict | None = None) -> Metadata:
    game = detect_game(filename)
    label = LABEL[game]
    creative = creative or {}
    style = str(creative.get("style") or "GENERIC")
    clear_drop = float(creative.get("clear_drop") or 0.0)
    title_copy, detail = _scene_copy(style, clear_drop)

    hook = str(creative.get("lead_text") or "")
    title = f"{title_copy} | {label}"[:100]
    youtube_description = (
        f"{label}\n"
        f"{detail}\n"
        "#JUDMGames #모바일게임 #인디게임 #Shorts"
    )
    instagram_caption = (
        f"{title_copy}\n"
        f"{label}\n"
        "#JUDMGames #모바일게임 #인디게임"
    )
    tiktok_caption = f"{title_copy} | {label} #모바일게임 #인디게임 #JUDMGames"

    return Metadata(
        game_key=game,
        game_label=label,
        hook=hook,
        youtube_title=title,
        youtube_description=youtube_description,
        instagram_caption=instagram_caption[:2200],
        tiktok_caption=tiktok_caption[:2200],
    )
