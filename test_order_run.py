import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
    cred = yaml.safe_load(f)

api = NorenApi(
    host="https://api.shoonya.com/NorenWClientAPI/",
    websocket="wss://api.shoonya.com/NorenWSAPI/"
)
api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

res = api.place_order(
    buy_or_sell="B",
    product_type="M",
    exchange="MCX",
    tradingsymbol="CRUDEOILM19AUG26",
    quantity=10,
    discloseqty=0,
    price_type="LMT",
    price=7500.0,
    trigger_price=None,
    retention="DAY",
    amo="NO",
    remarks="GeminiTest"
)
print("place_order response:", res)

# Check order book
orders = api.get_order_book()
print("get_order_book response:", orders)
