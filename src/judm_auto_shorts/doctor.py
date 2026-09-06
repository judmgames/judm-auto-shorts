from __future__ import annotations
import json, os, shutil
from .config import Settings

def main():
    s=Settings.load(); issues=[]
    for exe in ("ffmpeg","ffprobe","fc-match"):
        if not shutil.which(exe): issues.append(f"missing executable: {exe}")
    if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"): issues.append("missing GOOGLE_SERVICE_ACCOUNT_JSON")
    for p in s.targets:
        if not s.enabled(p): continue
        if p=="youtube":
            for k in ("GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GOOGLE_REFRESH_TOKEN"):
                if not os.getenv(k): issues.append(f"youtube enabled but {k} missing")
        if p=="instagram":
            for k in ("INSTAGRAM_USER_ID","INSTAGRAM_ACCESS_TOKEN","CLOUDINARY_CLOUD_NAME","CLOUDINARY_API_KEY","CLOUDINARY_API_SECRET"):
                if not os.getenv(k): issues.append(f"instagram enabled but {k} missing")
        if p=="tiktok" and not os.getenv("TIKTOK_ACCESS_TOKEN"): issues.append("tiktok enabled but TIKTOK_ACCESS_TOKEN missing")
    out={"ok":not issues,"targets":s.targets,"enabled":{"youtube":s.youtube_enabled,"instagram":s.instagram_enabled,"tiktok":s.tiktok_enabled},"issues":issues}
    print(json.dumps(out,ensure_ascii=False,indent=2)); raise SystemExit(0 if not issues else 2)
if __name__=="__main__": main()
