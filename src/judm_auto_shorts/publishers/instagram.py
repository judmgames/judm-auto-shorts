from __future__ import annotations
import os,time,requests

def base():
    v=os.getenv("INSTAGRAM_API_VERSION","v25.0").strip("/")
    return f"https://graph.instagram.com/{v}"

def publish_reel(video_url:str,caption:str)->str:
    uid=os.environ["INSTAGRAM_USER_ID"]; tok=os.environ["INSTAGRAM_ACCESS_TOKEN"]
    r=requests.post(f"{base()}/{uid}/media",data={"media_type":"REELS","video_url":video_url,"caption":caption,"share_to_feed":"true","access_token":tok},timeout=60); r.raise_for_status(); cid=r.json()["id"]
    for _ in range(72):
        s=requests.get(f"{base()}/{cid}",params={"fields":"status_code,status","access_token":tok},timeout=30); s.raise_for_status(); d=s.json(); code=d.get("status_code")
        if code=="FINISHED": break
        if code in {"ERROR","EXPIRED"}: raise RuntimeError(f"Instagram container failed: {d}")
        time.sleep(5)
    else: raise TimeoutError("Instagram container processing timeout")
    p=requests.post(f"{base()}/{uid}/media_publish",data={"creation_id":cid,"access_token":tok},timeout=60); p.raise_for_status(); return p.json()["id"]
