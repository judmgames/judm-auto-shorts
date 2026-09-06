from __future__ import annotations
import os,time,requests
BASE="https://open.tiktokapis.com/v2"

def _post(path,token,json_body=None):
    r=requests.post(BASE+path,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json; charset=UTF-8"},json=json_body,timeout=60); r.raise_for_status(); d=r.json()
    if d.get("error",{}).get("code") not in (None,"ok"): raise RuntimeError(d)
    return d.get("data",{})

def publish_file(path:str,caption:str,token:str|None=None)->str:
    token=token or os.environ["TIKTOK_ACCESS_TOKEN"]
    info=_post("/post/publish/creator_info/query/",token)
    allowed=info.get("privacy_level_options",[]); wanted=os.getenv("TIKTOK_PRIVACY_LEVEL","PUBLIC_TO_EVERYONE")
    if wanted not in allowed: raise RuntimeError(f"TikTok privacy {wanted} is not allowed for this creator: {allowed}")
    size=os.path.getsize(path)
    init=_post("/post/publish/video/init/",token,{"post_info":{"title":caption,"privacy_level":wanted,"disable_duet":bool(info.get("duet_disabled",False)),"disable_comment":bool(info.get("comment_disabled",False)),"disable_stitch":bool(info.get("stitch_disabled",False)),"video_cover_timestamp_ms":1000},"source_info":{"source":"FILE_UPLOAD","video_size":size,"chunk_size":size,"total_chunk_count":1}})
    pub=init["publish_id"]
    with open(path,"rb") as f:
        up=requests.put(init["upload_url"],data=f,headers={"Content-Type":"video/mp4","Content-Length":str(size),"Content-Range":f"bytes 0-{size-1}/{size}"},timeout=600); up.raise_for_status()
    # Poll until direct post completes. Public post id can be delayed by moderation.
    for _ in range(90):
        st=_post("/post/publish/status/fetch/",token,{"publish_id":pub}); status=st.get("status")
        if status=="PUBLISH_COMPLETE":
            ids=st.get("publicaly_available_post_id") or []
            return str(ids[0]) if ids else pub
        if status=="FAILED": raise RuntimeError(f"TikTok publish failed: {st.get('fail_reason')}")
        time.sleep(5)
    raise TimeoutError(f"TikTok publish still processing: {pub}")
