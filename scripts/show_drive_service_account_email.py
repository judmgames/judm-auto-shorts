import json,os
print(json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])['client_email'])
