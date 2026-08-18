"""
shoonya_login.py

One-file Shoonya OAuth login + connection check.
Put this in the same folder as cred.yaml and run it.

Requires: pip install --user NorenRestApiOAuth pyyaml
"""

import os
import yaml
from NorenRestApiPy.NorenApi import NorenApi

CRED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cred.yaml')
HOST = 'https://api.shoonya.com/NorenWClientAPI/'
WEBSOCKET = 'wss://api.shoonya.com/NorenWSAPI/'


def load_cred():
    with open(CRED_PATH) as f:
        return yaml.safe_load(f)


def save_cred(cred):
    with open(CRED_PATH, 'w') as f:
        yaml.safe_dump(cred, f)


def new_api():
    return NorenApi(host=HOST, websocket=WEBSOCKET)


def try_existing_session(cred):
    """Return True if the token already in cred.yaml still works."""
    api = new_api()
    api.injectOAuthHeader(cred['Access_token'], cred['UID'], cred['Account_ID'])
    ret = api.get_limits()
    if ret and str(ret.get('stat', '')).lower() == 'ok':
        print("Existing session is still valid — no login needed.")
        print(ret)
        return True
    print("Existing session invalid:", ret)
    return False


def do_fresh_login(cred):
    """Walk the user through getting a new access token."""
    api = new_api()
    url = cred['oauth_url']  # already a complete, correct login URL

    print("\n1) Open this URL in your browser and log in:")
    print("  ", url)
    print("2) After login, you'll be redirected to a URL containing 'code=...'")
    auth_code = input("3) Paste ONLY the code value here: ").strip()

    result = api.getAccessToken(
        auth_code,
        cred['Secret_Code'],
        cred['client_id'],
        cred['UID'],
    )
    if not result:
        raise SystemExit("getAccessToken() returned nothing — the code was likely expired. Try again with a fresh one.")

    access_token, returned_uid, refresh_token, account_id = result
    if not access_token or not account_id:
        raise SystemExit(f"Incomplete response from Shoonya: {result}")

    cred['Access_token'] = access_token
    cred['Account_ID'] = account_id
    cred['UID'] = returned_uid or cred['UID']
    if refresh_token:
        cred['Refresh_token'] = refresh_token
    save_cred(cred)
    print("\ncred.yaml updated with a fresh Access_token.")

    api.injectOAuthHeader(access_token, cred['UID'], account_id)
    ret = api.get_limits()
    print("\nVerification call result:")
    print(ret)


if __name__ == '__main__':
    cred = load_cred()
    if not try_existing_session(cred):
        do_fresh_login(cred)
