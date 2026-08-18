"""
Quick check: is the Shoonya session currently live?
Run this any time — it does NOT trigger a login, just checks.
"""

import os
import yaml
from NorenRestApiPy.NorenApi import NorenApi

CRED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cred.yaml')

with open(CRED_PATH) as f:
    cred = yaml.safe_load(f)

api = NorenApi(
    host='https://api.shoonya.com/NorenWClientAPI/',
    websocket='wss://api.shoonya.com/NorenWSAPI/'
)
api.injectOAuthHeader(cred['Access_token'], cred['UID'], cred['Account_ID'])

ret = api.get_limits()

if ret and str(ret.get('stat', '')).lower() == 'ok':
    print("LIVE — connection is working.")
    print(f"  Account: {ret.get('actid', cred['Account_ID'])}")
    print(f"  Cash available: {ret.get('cash', 'n/a')}")
else:
    emsg = ret.get('emsg', 'unknown error') if ret else 'empty response'
    print(f"NOT LIVE — {emsg}")
    print("Run shoonya_login.py to refresh your session.")
