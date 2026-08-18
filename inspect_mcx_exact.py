import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

def inspect_exact_mcx():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    searches = [
        {"exch": "MCX", "query": "CRUDEOIL"},
        {"exch": "MCX", "query": "GOLD"},
        {"exch": "MCX", "query": "SILVER"},
        {"exch": "MCX", "query": "NATURALGAS"},
        {"exch": "NSE", "query": "RELIANCE-EQ"},
        {"exch": "NSE", "query": "TCS-EQ"},
        {"exch": "NSE", "query": "HDFCBANK-EQ"}
    ]

    results = {}
    for s in searches:
        res = api.searchscrip(exchange=s["exch"], searchtext=s["query"])
        if res and res.get("stat") == "Ok" and "values" in res:
            items = res["values"][:8]
            results[s["query"]] = []
            for item in items:
                tok = item.get("token")
                tsym = item.get("tsym")
                q = api.get_quotes(exchange=s["exch"], token=tok)
                results[s["query"]].append({
                    "tsym": tsym,
                    "token": tok,
                    "exd": item.get("exd"),
                    "lot_size": item.get("ls"),
                    "ltp": q.get("lp"),
                    "close": q.get("c"),
                    "open": q.get("o"),
                    "high": q.get("h"),
                    "low": q.get("l"),
                    "vol": q.get("v")
                })

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    inspect_exact_mcx()
