import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

def get_exact_quotes():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    # 1. NSE Equities
    nse_syms = ["RELIANCE-EQ", "TCS-EQ", "HDFCBANK-EQ", "INFY-EQ"]
    nse_quotes = {}
    for s in nse_syms:
        r = api.searchscrip(exchange="NSE", searchtext=s)
        if r and "values" in r:
            # find exact match
            match = next((x for x in r["values"] if x.get("tsym") == s), r["values"][0])
            tok = match["token"]
            q = api.get_quotes(exchange="NSE", token=tok)
            nse_quotes[s] = {
                "token": tok,
                "tsym": match.get("tsym"),
                "ltp": float(q.get("lp", 0)),
                "close": float(q.get("c", 0)),
                "open": float(q.get("o", 0)),
                "high": float(q.get("h", 0)),
                "low": float(q.get("l", 0))
            }

    # 2. MCX Commodities (Near month contracts)
    mcx_queries = ["CRUDEOIL", "GOLD", "SILVER", "NATURALGAS"]
    mcx_quotes = {}
    for sym in mcx_queries:
        r = api.searchscrip(exchange="MCX", searchtext=sym)
        if r and "values" in r:
            # filter for futures contracts (optt is XX or None)
            fut_contracts = [x for x in r["values"] if x.get("instname") == "FUTCOM" or x.get("optt") in ["XX", None, ""]]
            sample = fut_contracts[:3] if fut_contracts else r["values"][:3]
            mcx_quotes[sym] = []
            for item in sample:
                tok = item["token"]
                q = api.get_quotes(exchange="MCX", token=tok)
                mcx_quotes[sym].append({
                    "tradingsymbol": item.get("tsym"),
                    "token": tok,
                    "expiry": item.get("exd"),
                    "lot_size": item.get("ls"),
                    "ltp": float(q.get("lp", 0)),
                    "close": float(q.get("c", 0)),
                    "high": float(q.get("h", 0)),
                    "low": float(q.get("l", 0)),
                    "volume": int(q.get("v", 0))
                })

    print("=== NSE LIVE QUOTES ===")
    print(json.dumps(nse_quotes, indent=2))
    print("\n=== MCX LIVE CONTRACTS & QUOTES ===")
    print(json.dumps(mcx_quotes, indent=2))

if __name__ == "__main__":
    get_exact_quotes()
