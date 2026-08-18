import os
import yaml
import requests
from NorenRestApiPy.NorenApi import NorenApi

def check_reachability():
    print("==================================================================")
    print("           SHOONYA REACHABILITY & SESSION STATUS CHECK            ")
    print("==================================================================")

    api_url = "https://api.shoonya.com/NorenWClientAPI/"
    try:
        r = requests.get(api_url, timeout=5)
        print(f"[1] Network Reachability ({api_url}): REACHABLE (HTTP {r.status_code})")
    except Exception as e:
        print(f"[1] Network Reachability ({api_url}): FAILED - {e}")

    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cred.yaml')
    with open(cred_path, "r") as f:
        cred = yaml.safe_load(f)

    uid = cred.get("UID")
    act_id = cred.get("Account_ID")
    token = cred.get("Access_token")

    print(f"\n[2] Session Authentication:")
    print(f"    - UID: {uid}")
    print(f"    - Account: {act_id}")
    print(f"    - Token: {token[:16]}... (Loaded from {cred_path})")

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(token, uid, act_id)

    ret = api.get_limits()

    if ret and str(ret.get('stat', '')).lower() == 'ok':
        print("\n[3] Result: LIVE — Shoonya connection is active and working.")
        print(f"    - Account: {ret.get('actid', act_id)}")
        print(f"    - Profile: {ret.get('prfname', 'SHOONYA')}")
        print(f"    - Cash Available: Rs {ret.get('cash', '0.00')}")
        print(f"    - Turnover Limit: Rs {ret.get('turnoverlmt', 'Unlimited')}")
    else:
        emsg = ret.get('emsg', 'unknown error') if ret else 'empty response'
        print(f"\n[3] Result: NOT LIVE — {emsg}")

    print("==================================================================")

if __name__ == "__main__":
    check_reachability()
