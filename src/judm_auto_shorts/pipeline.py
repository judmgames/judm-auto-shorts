from __future__ import annotations
import json, os, tempfile, traceback
from pathlib import Path
from .config import Settings
from .providers.drive import DriveProvider
from .metadata import make_metadata
from .editor import auto_edit, probe
from .publishers.youtube import publish as publish_youtube
from .publishers.instagram import publish_reel
from .publishers.tiktok import publish_file as publish_tiktok
from .hosting.cloudinary_host import upload_video, delete_video
from .tokens import refresh_tiktok

KEY={"youtube":"judm_youtube_id","instagram":"judm_instagram_id","tiktok":"judm_tiktok_id"}

def published(props,platform): return bool((props or {}).get(KEY[platform]))

def prepare_oldest(drive:DriveProvider,s:Settings,ready_id:str):
    new=drive.list_new(s.inbox_id,limit=20)
    if not new: return None
    f=new[0]
    # Mark first so a failed physical move cannot cause duplicate intake on next run.
    drive.set_props(f["id"],judm_state="ready",judm_error="")
    try: drive.move(f["id"],ready_id)
    except Exception: pass
    return drive.get(f["id"])

def process_one()->dict:
    s=Settings.load(); drive=DriveProvider(); sib=drive.resolve_siblings(s.inbox_id)
    prepared=prepare_oldest(drive,s,sib["ready"])
    ready=drive.list_ready(s.inbox_id,sib["ready"],limit=20)
    if not ready:
        return {"status":"idle","message":"No source videos in 00_INBOX or 01_READY"}
    f=ready[0]; props=f.get("appProperties") or {}; missing=[p for p in s.targets if not published(props,p)]
    if not missing:
        drive.move_or_mark(f["id"],sib["posted"],"posted")
        return {"status":"posted","source":f["name"],"message":"Already complete; finalized folder state"}
    runnable=[p for p in missing if s.enabled(p)]
    if not runnable:
        drive.set_props(f["id"],judm_state="ready",judm_error="waiting_for_platform_approval")
        return {"status":"waiting","source":f["name"],"missing":missing,"message":"Edited/publish pipeline is ready; no missing target platform is enabled yet"}

    drive.set_props(f["id"],judm_state="posting",judm_error="")
    meta=make_metadata(f["name"])
    result={"status":"posting","source":f["name"],"missing_before":missing,"attempting":runnable,"published":{}}
    try:
        with tempfile.TemporaryDirectory(prefix="judm_") as td:
            raw=Path(td)/f["name"]; drive.download(f["id"],raw); pr=probe(raw)
            if pr.duration<2 or pr.width<240 or pr.height<240: raise RuntimeError(f"Source video too small/short: {pr}")
            outputs=auto_edit(raw,Path(td)/"edited",meta); result["highlight"]=outputs["highlight"]
            if "youtube" in runnable:
                vid=publish_youtube(outputs["youtube"],meta.youtube_title,meta.youtube_description)
                drive.set_props(f["id"],judm_youtube_id=vid,judm_error=""); result["published"]["youtube"]=vid
            if "instagram" in runnable:
                url,pid=upload_video(outputs["instagram"])
                try: mid=publish_reel(url,meta.instagram_caption)
                finally:
                    try: delete_video(pid)
                    except Exception: pass
                drive.set_props(f["id"],judm_instagram_id=mid,judm_error=""); result["published"]["instagram"]=mid
            if "tiktok" in runnable:
                # TikTok access tokens last 24h; refresh silently and persist the rotated pair.
                tiktok_token=refresh_tiktok() if os.getenv("TIKTOK_REFRESH_TOKEN") else os.getenv("TIKTOK_ACCESS_TOKEN")
                tid=publish_tiktok(outputs["tiktok"],meta.tiktok_caption,tiktok_token)
                drive.set_props(f["id"],judm_tiktok_id=tid,judm_error=""); result["published"]["tiktok"]=tid
        props=drive.get(f["id"]).get("appProperties") or {}
        still=[p for p in s.targets if not published(props,p)]
        if still:
            drive.set_props(f["id"],judm_state="ready",judm_error="waiting:"+",".join(still))
            result.update(status="partial",missing_after=still)
        else:
            drive.move_or_mark(f["id"],sib["posted"],"posted"); result.update(status="posted",missing_after=[])
        return result
    except Exception as e:
        msg=(type(e).__name__+":"+str(e))[:115]
        drive.set_props(f["id"],judm_state="ready",judm_error=msg)
        result.update(status="error",error=msg)
        raise

def main():
    try: print(json.dumps(process_one(),ensure_ascii=False,indent=2))
    except Exception:
        traceback.print_exc(); raise

if __name__=="__main__": main()
