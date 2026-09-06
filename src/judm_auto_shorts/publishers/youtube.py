from __future__ import annotations
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES=["https://www.googleapis.com/auth/youtube.upload"]

def creds():
    return Credentials(token=None,refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],token_uri="https://oauth2.googleapis.com/token",client_id=os.environ["GOOGLE_CLIENT_ID"],client_secret=os.environ["GOOGLE_CLIENT_SECRET"],scopes=SCOPES)

def publish(video_path:str,title:str,description:str)->str:
    yt=build("youtube","v3",credentials=creds(),cache_discovery=False)
    body={"snippet":{"title":title,"description":description,"categoryId":os.getenv("YOUTUBE_CATEGORY_ID","20")},"status":{"privacyStatus":os.getenv("YOUTUBE_PRIVACY_STATUS","public"),"selfDeclaredMadeForKids":False}}
    req=yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(video_path,mimetype="video/mp4",resumable=True,chunksize=8*1024*1024))
    response=None
    while response is None: _,response=req.next_chunk()
    return response["id"]
