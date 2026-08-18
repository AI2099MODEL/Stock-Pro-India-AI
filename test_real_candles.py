import yaml
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from NorenRestApiPy.NorenApi import NorenApi

IST = ZoneInfo("Asia/Kolkata")

def test_real_time_series():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    # CRUDEOILM 19-AUG-2026 (token 560978)
    token = "560978"
    now = datetime.now(IST)
    start = now - timedelta(days=2)

    ret = api.get_time_price_series(
        exchange="MCX",
        token=token,
        starttime=str(int(start.timestamp())),
        endtime=str(int(now.timestamp())),
        interval="15"
    )

    print(f"Time price series response for CRUDEOILM (type: {type(ret)}):")
    if isinstance(ret, list):
        print(f"Received {len(ret)} real historical candles from Shoonya API.")
        print("Last 3 candles:")
        for c in ret[-3:]:
            print(" ", c)
    else:
        print("Response:", ret)

if __name__ == "__main__":
    test_real_time_series()
