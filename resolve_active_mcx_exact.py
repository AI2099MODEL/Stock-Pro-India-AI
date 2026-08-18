import yaml
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from NorenRestApiPy.NorenApi import NorenApi

IST = ZoneInfo("Asia/Kolkata")

def resolve_all_active_mcx():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    symbols = ["CRUDEOILM", "GOLDM", "SILVERM", "NATURALGAS"]
    resolved = {}

    today = datetime.now(IST).date()

    for symbol in symbols:
        ret = api.searchscrip(exchange="MCX", searchtext=symbol)
        if not ret or ret.get("stat") != "Ok":
            continue
        
        pattern = re.compile(rf"^{re.escape(symbol.upper())}\d{{1,2}}[A-Z]{{3}}\d{{2}}$")
        candidates = [v for v in ret["values"] if pattern.match(v.get("tsym", "").upper())]

        best, best_exd = None, None
        for c in candidates:
            info = api.get_security_info(exchange="MCX", token=c["token"])
            exd_str = info.get("exd") if info else None
            if not exd_str:
                continue
            exd = datetime.strptime(exd_str, "%d-%b-%Y").date()
            if exd < today:
                continue
            if best_exd is None or exd < best_exd:
                best_exd = exd
                q = api.get_quotes(exchange="MCX", token=c["token"])
                best = {
                    "symbol": symbol,
                    "tradingsymbol": c["tsym"],
                    "token": c["token"],
                    "expiry": str(exd),
                    "ltp": float(q.get("lp", 0)),
                    "close": float(q.get("c", 0)),
                    "open": float(q.get("o", 0)),
                    "high": float(q.get("h", 0)),
                    "low": float(q.get("l", 0)),
                    "volume": int(q.get("v", 0))
                }
        resolved[symbol] = best

    print(json.dumps(resolved, indent=2))

if __name__ == "__main__":
    resolve_all_active_mcx()
