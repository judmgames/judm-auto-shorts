from __future__ import annotations
import hashlib
from dataclasses import dataclass

HOOKS = {
 "SLIME":["여기서 떨어지면 진짜 끝ㅋㅋ","제발 거기만 밟지 마","이 높이부터 손이 떨린다","너라면 여기서 살 수 있음?"],
 "PN37":["이 기록 넘으면 인정","여기서 반응속도 갈린다","37연속 가는 순간 도파민 폭발","이 장면 바로 보이면 인정"],
 "BLINE":["망했다 싶었는데 이게 살아남네","여기서 살아남는 방법 딱 하나","이 한 칸 때문에 다 터질 뻔","이 맛에 퍼즐게임 한다"],
 "FAMMER":["감자가 선전포고함ㅋㅋ","농부 VS 작물떼 이게 맞냐","처음엔 농사게임인 줄 알았음","작물이 몰려오면 이렇게 된다"],
 "GENERIC":["이 장면은 그냥 못 넘긴다","여기서부터 분위기 바뀜","끝까지 보면 이유가 있음","딱 이 순간 때문에 한 판 더 함"],
}
LABEL={"SLIME":"뿅뿅슬라임","PN37":"피지컬넘버37","BLINE":"B.Line POP","FAMMER":"FammerWar","GENERIC":"JUD.M Games"}

@dataclass(frozen=True)
class Metadata:
    game_key:str; game_label:str; hook:str
    youtube_title:str; youtube_description:str; instagram_caption:str; tiktok_caption:str

def detect_game(name:str)->str:
    u=name.upper()
    if any(x in u for x in ("SLIME","BBYONG","뿅")): return "SLIME"
    if any(x in u for x in ("PN37","PHYSICAL","NUMBER37","피지컬")): return "PN37"
    if any(x in u for x in ("BLINE","B.LINE","LINEPOP")): return "BLINE"
    if any(x in u for x in ("FAMMER","FARMERWAR","파머")): return "FAMMER"
    return "GENERIC"

def make_metadata(filename:str)->Metadata:
    g=detect_game(filename); label=LABEL[g]
    d=hashlib.sha256(filename.encode()).digest(); hook=HOOKS[g][d[0]%len(HOOKS[g])]
    title=f"{hook} | {label}"[:100]
    yd=f"{hook}\n끝까지 살아남는지 직접 확인해봐.\n#JUDMGames #모바일게임 #인디게임 #게임추천 #Shorts"
    ig=f"{hook}\n{label}\n#JUDMGames #모바일게임 #인디게임 #게임추천"
    tt=f"{hook} #모바일게임 #인디게임 #JUDMGames"
    return Metadata(g,label,hook,title,yd,ig[:2200],tt[:2200])
