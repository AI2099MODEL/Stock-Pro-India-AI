import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

def find_active_front_month_contracts():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    commodities = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER"]
    active_contracts = {}

    for c in commodities:
        r = api.searchscrip(exchange="MCX", searchtext=c)
        if r and "values" in r:
            all_matches = []
            for item in r["values"]:
                tok = item.get("token")
                tsym = item.get("tsym")
                q = api.get_quotes(exchange="MCX", token=tok)
                vol = int(q.get("v", 0)) if q and q.get("v") else 0
                lp = float(q.get("lp", 0)) if q and q.get("lp") else 0.0
                all_matches.append({
                    "tradingsymbol": tsym,
                    "token": tok,
                    "expiry": item.get("exd"),
                    "instname": item.get("instname"),
                    "lot_size": item.get("ls"),
                    "ltp": lp,
                    "volume": vol,
                    "close": q.get("c"),
                    "high": q.get("h"),
                    "low": q.get("l")
                })
            # Sort by volume descending to find the TRUE front-month contract with maximum market liquidity
            all_matches.sort(key=lambda x: x["volume"], reverse=True)
            active_contracts[c] = all_matches[:5]

    print(json.dumps(active_contracts, indent=2))

if __name__ == "__main__":
    find_active_front_month_contracts()
