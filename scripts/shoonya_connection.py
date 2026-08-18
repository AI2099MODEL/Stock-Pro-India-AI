"""
Builds a live Shoonya (NorenApi) client session from cred.yaml.
Uses official NorenRestApiPy.NorenApi and injectOAuthHeader.
"""
import os
import yaml
from NorenRestApiPy.NorenApi import NorenApi
import config

def get_client():
    cred_path = getattr(config, "SHOONYA_CRED_PATH", "cred.yaml")
    if not os.path.exists(cred_path):
        for candidate in ["cred.yaml", "D:/family/oracle/Paper trading bot 7/cred.yaml", "D:/family/oracle/cred.yaml"]:
            if os.path.exists(candidate):
                cred_path = candidate
                break

    with open(cred_path, "r") as f:
        cred = yaml.safe_load(f)

    access_token = cred.get("Access_token")
    uid = cred.get("UID") or cred.get("user") or cred.get("Account_ID")
    account_id = cred.get("Account_ID") or uid

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(access_token, uid, account_id)

    # Verify session
    limits = api.get_limits()
    if not limits or limits.get("stat") != "Ok":
        raise Exception(f"Shoonya session rejected by get_limits: {limits}")

    return api

if __name__ == "__main__":
    client = get_client()
    print("Shoonya client connected successfully! Limits:", client.get_limits())
