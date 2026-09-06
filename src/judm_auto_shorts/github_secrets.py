from __future__ import annotations
import base64, os, requests
from nacl import encoding, public

def update_secret(name:str,value:str):
    token=os.environ.get("GH_SECRETS_PAT")
    repo=os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo: return False
    h={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    k=requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",headers=h,timeout=30); k.raise_for_status(); kd=k.json()
    box=public.SealedBox(public.PublicKey(kd["key"].encode(),encoding.Base64Encoder())); enc=base64.b64encode(box.encrypt(value.encode())).decode()
    r=requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/{name}",headers=h,json={"encrypted_value":enc,"key_id":kd["key_id"]},timeout=30); r.raise_for_status(); return True
