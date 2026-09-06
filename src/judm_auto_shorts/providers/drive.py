from __future__ import annotations
import json, os
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

SCOPES=["https://www.googleapis.com/auth/drive"]

class DriveProvider:
    def __init__(self):
        raw=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
        info=json.loads(raw)
        creds=service_account.Credentials.from_service_account_info(info,scopes=SCOPES)
        self.api=build("drive","v3",credentials=creds,cache_discovery=False)

    def folder(self, folder_id:str):
        return self.api.files().get(fileId=folder_id,fields="id,name,parents",supportsAllDrives=True).execute()

    def resolve_siblings(self,inbox_id:str):
        inbox=self.folder(inbox_id); parents=inbox.get("parents") or []
        if not parents: raise RuntimeError("00_INBOX parent not visible to service account")
        root=parents[0]
        def find(name):
            q=f"'{root}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder' and name='{name}'"
            r=self.api.files().list(q=q,fields="files(id,name)",pageSize=10,supportsAllDrives=True,includeItemsFromAllDrives=True).execute().get("files",[])
            if not r: raise RuntimeError(f"Sibling folder missing or not shared: {name}")
            return r[0]["id"]
        return {"root":root,"ready":find("01_READY"),"posted":find("02_POSTED")}

    def _list(self,folder_id:str,limit=20):
        q=f"'{folder_id}' in parents and trashed=false and mimeType contains 'video/'"
        return self.api.files().list(q=q,fields="files(id,name,mimeType,size,createdTime,parents,appProperties)",orderBy="createdTime",pageSize=limit,supportsAllDrives=True,includeItemsFromAllDrives=True).execute().get("files",[])

    def list_new(self,inbox_id:str,limit=20):
        return [f for f in self._list(inbox_id,limit) if (f.get("appProperties") or {}).get("judm_state") not in {"ready","posting","posted"}]

    def list_ready(self,inbox_id:str,ready_id:str,limit=20):
        out=[]; seen=set()
        for folder in (ready_id,inbox_id):
            for f in self._list(folder,limit):
                if f["id"] in seen: continue
                props=f.get("appProperties") or {}
                if folder==ready_id or props.get("judm_state") in {"ready","posting"}:
                    out.append(f); seen.add(f["id"])
        out.sort(key=lambda x:x.get("createdTime", "")); return out[:limit]

    def download(self,file_id:str,target:str|Path):
        target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
        req=self.api.files().get_media(fileId=file_id,supportsAllDrives=True)
        with target.open("wb") as fh:
            dl=MediaIoBaseDownload(fh,req,chunksize=8*1024*1024); done=False
            while not done: _,done=dl.next_chunk()
        return target

    def set_props(self,file_id:str,**props):
        cur=self.get(file_id).get("appProperties") or {}
        clean=dict(cur)
        for k,v in props.items():
            if v is None: clean.pop(k,None)
            else: clean[k]=str(v)[:120]
        return self.api.files().update(fileId=file_id,body={"appProperties":clean},fields="id,appProperties",supportsAllDrives=True).execute()

    def get(self,file_id:str):
        return self.api.files().get(fileId=file_id,fields="id,name,parents,appProperties",supportsAllDrives=True).execute()

    def move(self,file_id:str,to_parent:str):
        cur=self.get(file_id); old=",".join(cur.get("parents") or [])
        return self.api.files().update(fileId=file_id,addParents=to_parent,removeParents=old,fields="id,parents",supportsAllDrives=True).execute()

    def move_or_mark(self,file_id:str,to_parent:str,state:str):
        self.set_props(file_id,judm_state=state,judm_error="")
        try:
            self.move(file_id,to_parent); return True
        except HttpError:
            # Some My Drive permission combinations allow editing/appProperties but not organizer moves.
            # State marker keeps the automation idempotent even in that case.
            return False
