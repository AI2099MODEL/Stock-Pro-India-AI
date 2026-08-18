import yaml
import json
import requests

with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
    cred = yaml.safe_load(f)

access_token = cred["Access_token"]
uid = cred["UID"]
actid = cred["Account_ID"]

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json; charset=utf-8"
}

url = "https://api.shoonya.com/NorenWClientAPI/PlaceOrder"
values = {
    "ordersource": "API",
    "uid": uid,
    "actid": actid,
    "trantype": "B",
    "prd": "M",  # Margin / NRML
    "exch": "MCX",
    "tsym": "CRUDEOILM19AUG26",
    "qty": "10",
    "dscqty": "0",
    "prctyp": "LMT",
    "prc": "7500.0",
    "trgprc": "None",
    "ret": "DAY",
    "remarks": "GeminiLiveTrade"
}

payload = 'jData=' + json.dumps(values)
resp = requests.post(url, data=payload, headers=headers, timeout=10)
print("Raw HTTP Status:", resp.status_code)
print("Raw Shoonya Broker Response:", resp.text)
