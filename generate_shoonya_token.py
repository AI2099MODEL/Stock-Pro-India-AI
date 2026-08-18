"""
Automated Shoonya Finvasia Daily OAuth Token Generator & Validator
Usage:
  python generate_shoonya_token.py [code_or_url]
"""

import os
import sys
import yaml
from typing import Optional

def main():
    cred_path = "D:/Antigravity/cred.yaml"
    if not os.path.exists(cred_path):
        cred_path = "D:/family/oracle/Paper trading bot 7/cred.yaml"

    if not os.path.exists(cred_path):
        print(f"❌ Error: {cred_path} not found.")
        sys.exit(1)

    with open(cred_path, "r") as f:
        cred = yaml.safe_load(f) or {}

    uid = cred.get("UID", "")
    client_id = cred.get("client_id", "")
    secret_code = cred.get("Secret_Code", "")
    oauth_url = cred.get("oauth_url", f"https://api.shoonya.com/OAuthlogin/authorize/oauth?client_id={client_id}")

    try:
        from NorenRestApiPy.NorenApi import NorenApi
    except ImportError:
        print("❌ Please install NorenRestApiPy: pip install NorenRestApiPy")
        sys.exit(1)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )

    # 1. First test existing session token
    existing_token = cred.get("Access_token")
    if existing_token and len(sys.argv) < 2:
        print(f"🔍 Testing existing Access Token for UID: {uid}...")
        api.injectOAuthHeader(existing_token, uid, cred.get("Account_ID", uid))
        limits = api.get_limits()
        if limits and isinstance(limits, dict) and limits.get("stat") == "Ok":
            print("✅ Existing Shoonya session is ALREADY ACTIVE and VALID!")
            print(f"   Account: {limits.get('actid', uid)} | Cash: ₹{limits.get('cash', '0.00')}")
            return

    # 2. Get auth code
    if len(sys.argv) >= 2:
        raw_input_code = sys.argv[1].strip()
    else:
        print("\n==============================================================")
        print("   SHOONYA FINVASIA DAILY OAUTH LOGIN")
        print("==============================================================")
        print(f"\n1. Open this URL in your browser and authorize:")
        print(f"   👉 {oauth_url}\n")
        print("2. After login, copy the redirected URL or the code parameter.")
        raw_input_code = input("\n3. Paste the code or redirected URL here: ").strip()

    if not raw_input_code:
        print("❌ No code provided. Exiting.")
        sys.exit(1)

    import re
    if "code=" in raw_input_code:
        m = re.search(r"code=([a-zA-Z0-9\-]+)", raw_input_code)
        if m:
            auth_code = m.group(1)
        else:
            auth_code = raw_input_code
    else:
        auth_code = raw_input_code

    print(f"\n[INFO] Exchanging auth code '{auth_code}' with Shoonya OAuth API...")
    result = api.getAccessToken(auth_code, secret_code, client_id, uid)
    if not result:
        print("[ERROR] getAccessToken returned empty response. The code may be expired or already used.")
        sys.exit(1)

    access_token, returned_uid, refresh_token, account_id = result
    if not access_token:
        print(f"[ERROR] Failed to get access token: {result}")
        sys.exit(1)

    # Save to cred.yaml
    cred["Access_token"] = access_token
    cred["Account_ID"] = account_id or uid
    cred["UID"] = returned_uid or uid
    if refresh_token:
        cred["Refresh_token"] = refresh_token

    for p in ["D:/Antigravity/cred.yaml", "D:/family/oracle/Paper trading bot 7/cred.yaml"]:
        try:
            with open(p, "w") as f:
                yaml.safe_dump(cred, f)
            print(f"💾 Updated credentials in: {p}")
        except Exception as e:
            print(f"⚠️ Could not write to {p}: {e}")

    # Verify new session
    print("\n🔍 Verifying fresh Shoonya session...")
    api.injectOAuthHeader(access_token, cred["UID"], cred["Account_ID"])
    limits = api.get_limits()
    if limits and isinstance(limits, dict) and limits.get("stat") == "Ok":
        print("🎉 SUCCESS: Shoonya Finvasia Connected Successfully!")
        print(f"   UID: {cred['UID']}")
        print(f"   Account ID: {cred['Account_ID']}")
        print(f"   New Access Token: {access_token[:10]}...{access_token[-8:]}")
    else:
        print(f"⚠️ Token saved but verification returned: {limits}")

if __name__ == "__main__":
    main()
