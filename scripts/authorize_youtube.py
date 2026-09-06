from __future__ import annotations
import argparse,json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES=['https://www.googleapis.com/auth/youtube.upload']

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--client-id',required=True); ap.add_argument('--client-secret',required=True); args=ap.parse_args()
    cfg={'installed':{'client_id':args.client_id,'client_secret':args.client_secret,'auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token','redirect_uris':['http://localhost']}}
    flow=InstalledAppFlow.from_client_config(cfg,SCOPES)
    c=flow.run_local_server(port=0,access_type='offline',prompt='consent')
    print('\nSAVE AS GITHUB SECRET GOOGLE_REFRESH_TOKEN:\n')
    print(c.refresh_token)
if __name__=='__main__': main()
