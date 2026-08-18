import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

def get_live_market_data():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    instruments = [
        {"exch": "MCX", "sym": "CRUDEOIL"},
        {"exch": "MCX", "sym": "GOLD"},
        {"exch": "MCX", "sym": "SILVER"},
        {"exch": "NSE", "sym": "RELIANCE"},
        {"exch": "NSE", "sym": "TCS"},
        {"exch": "NSE", "sym": "HDFCBANK"},
        {"exch": "NSE", "sym": "INFY"},
        {"exch": "NSE", "sym": "SBIN"}
    ]

    live_quotes = {}
    for item in instruments:
        res = api.searchscrip(exchange=item["exch"], searchtext=item["sym"])
        if res and res.get("stat") == "Ok" and "values" in res:
            first = res["values"][0]
            token = first.get("token")
            tsym = first.get("tsym")
            q = api.get_quotes(exchange=item["exch"], token=token)
            live_quotes[tsym] = {
                "exchange": item["exch"],
                "token": token,
                "symbol": item["sym"],
                "tradingsymbol": tsym,
                "ltp": float(q.get("lp", 0.0)),
                "high": float(q.get("h", 0.0)),
                "low": float(q.get("l", 0.0)),
                "open": float(q.get("o", 0.0)),
                "close": float(q.get("c", 0.0)),
                "volume": int(q.get("v", 0)),
                "lot_size": int(first.get("ls", 1))
            }

    print(json.dumps(live_quotes, indent=2))

if __name__ == "__main__":
    get_live_market_data()
