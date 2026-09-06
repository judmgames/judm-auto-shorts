from __future__ import annotations
import json, os
from pathlib import Path
from .config import Settings
from .providers.drive import DriveProvider
from .metadata import make_metadata
from .editor import auto_edit

def main():
    s=Settings.load(); d=DriveProvider(); sib=d.resolve_siblings(s.inbox_id)
    candidates=d.list_ready(s.inbox_id,sib["ready"],20) or d.list_new(s.inbox_id,20)
    if not candidates: raise SystemExit("No video found")
    f=candidates[0]; raw=Path("out")/"source"/f["name"]; d.download(f["id"],raw)
    outputs=auto_edit(raw,Path("out")/"edited",make_metadata(f["name"]))
    print(json.dumps({"source":f["name"],"outputs":outputs},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
