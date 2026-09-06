from __future__ import annotations
import os,requests
from .github_secrets import update_secret

def refresh_instagram()->bool:
    tok=os.environ["INSTAGRAM_ACCESS_TOKEN"]
    r=requests.get("https://graph.instagram.com/refresh_access_token",params={"grant_type":"ig_refresh_token","access_token":tok},timeout=30)
    r.raise_for_status(); new=r.json()["access_token"]
    if not update_secret("INSTAGRAM_ACCESS_TOKEN",new):
        raise RuntimeError("GH_SECRETS_PAT is required to persist refreshed Instagram token")
    return True

def refresh_tiktok()->str:
    key=os.environ["TIKTOK_CLIENT_KEY"]; secret=os.environ["TIKTOK_CLIENT_SECRET"]; refresh=os.environ["TIKTOK_REFRESH_TOKEN"]
    r=requests.post("https://open.tiktokapis.com/v2/oauth/token/",headers={"Content-Type":"application/x-www-form-urlencoded"},data={"client_key":key,"client_secret":secret,"grant_type":"refresh_token","refresh_token":refresh},timeout=30)
    r.raise_for_status(); d=r.json()
    access=d["access_token"]; new_refresh=d["refresh_token"]
    if not update_secret("TIKTOK_ACCESS_TOKEN",access) or not update_secret("TIKTOK_REFRESH_TOKEN",new_refresh):
        raise RuntimeError("GH_SECRETS_PAT is required to persist refreshed TikTok tokens")
    return access
