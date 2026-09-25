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
        return "여기서 살았다", "막히던 판이 한 수로 열렸다."
    if style == "CLEAR":
        if clear_drop >= 0.24:
            return "한 번에 정리됐다", "한 번에 크게 정리된 장면."
        return "여기서 지웠다", "POP이 나온 순간."
    if style == "FEVER":
        return "왔다", "플레이 흐름이 바뀐 순간."
    if style == "TURNAROUND":
        return "여기서 바뀌었다", "흐름이 뒤집힌 장면."
    if style == "BUILDUP":
        return "여기까지 이어졌다", "쌓이던 흐름이 결과로 이어진 순간."
    if style == "IMPACT":
        return "딱 이 장면", "가장 큰 변화가 나온 순간."
    if style == "NEAR_FAIL":
        return "아슬아슬했던 순간", "끝까지 결과가 갈린 장면."
    if style == "FAIL":
        return "여기서 끝났다", "결과가 갈린 순간."
    if style == "RHYTHM":
        return "손맛 좋았던 구간", "플레이 리듬이 이어진 구간."
    if style == "MISTAKE":
        return "여기서 꼬였다", "다시 보니 여기였다."
    if style == "ASMR":
        return "그냥 이 장면", "말 없이 보기 좋은 플레이."
    return "플레이 한 장면", "가장 변화가 컸던 순간."


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
