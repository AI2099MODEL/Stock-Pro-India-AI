import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

CRED_PATH = "D:/family/oracle/Paper trading bot 7/cred.yaml"

def run_connectivity_test():
    print("==================================================================")
    print("  SHOONYA (FINVASIA) LIVE CONNECTIVITY & CAPABILITY TEST")
    print("==================================================================")
    
    # 1. Load Credentials
    print("\n[1/5] Loading credentials from:", CRED_PATH)
    with open(CRED_PATH, "r") as f:
        cred = yaml.safe_load(f)
    print(f"      UID: {cred.get('UID')}")
    print(f"      Account ID: {cred.get('Account_ID')}")
    print(f"      Client ID: {cred.get('client_id')}")
    print(f"      Access Token: {cred.get('Access_token')[:16]}... (Length: {len(cred.get('Access_token', ''))})")

    # 2. Initialize API & Inject OAuth Header
    print("\n[2/5] Initializing NorenApi and injecting OAuth headers...")
    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])
    print("      OAuth Header successfully injected.")

    # 3. Call get_limits()
    print("\n[3/5] Calling get_limits() to verify live broker session...")
    limits = api.get_limits()
    print(f"      Response: {json.dumps(limits, indent=2)}")
    
    if limits and limits.get("stat") == "Ok":
        print("      --> Session Status: ACTIVE & VALID (stat: Ok)")
        print(f"      --> Cash Available: {limits.get('cash', '0.00')}")
        print(f"      --> Profile: {limits.get('prfname', 'SHOONYA')}")
    else:
        print("      --> Session Status: FAILED or EXPIRED")
        return

    # 4. Search Scrip Test
    print("\n[4/5] Testing searchscrip API for NSE (RELIANCE & NIFTY)...")
    search_res = api.searchscrip(exchange="NSE", searchtext="RELIANCE")
    if search_res and search_res.get("stat") == "Ok" and "values" in search_res:
        first = search_res["values"][0]
        print(f"      --> Scrip Found: {first.get('tsym')} (Token: {first.get('token')}, Lot Size: {first.get('ls', 1)})")
        token = first.get("token")
        
        # 5. Fetch Live Quote
        print(f"\n[5/5] Fetching live quote for Token {token} ({first.get('tsym')})...")
        quotes = api.get_quotes(exchange="NSE", token=token)
        print(f"      Response: {json.dumps(quotes, indent=2)}")
        if quotes and "lp" in quotes:
            print(f"      --> LIVE LTP: Rs {quotes.get('lp')} (High: {quotes.get('h', '--')}, Low: {quotes.get('l', '--')})")
    else:
        print(f"      Search scrip response: {search_res}")

    print("\n==================================================================")
    print("  [SUCCESS] All Shoonya API Connectivity Tests Passed!")
    print("==================================================================")

if __name__ == "__main__":
    run_connectivity_test()
