from __future__ import annotations
import json, os
from .tokens import refresh_instagram,refresh_tiktok

def main():
    r={}
    if os.getenv("INSTAGRAM_ENABLED","false").lower() in {"1","true","yes","on"}: r["instagram"]=refresh_instagram()
    if os.getenv("TIKTOK_ENABLED","false").lower() in {"1","true","yes","on"}: r["tiktok_access_refreshed"]=bool(refresh_tiktok())
    print(json.dumps(r,ensure_ascii=False))
if __name__=="__main__": main()
