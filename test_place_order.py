import yaml
import json
from NorenRestApiPy.NorenApi import NorenApi

def test_live_order_submission():
    with open("D:/family/oracle/Paper trading bot 7/cred.yaml") as f:
        cred = yaml.safe_load(f)

    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/"
    )
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])

    # Test placing a real market order on MCX Crude Oil Mini
    ret = api.place_order(
        buy_or_sell="B",
        product_type="M",  # Margin / NRML for MCX
        exchange="MCX",
        tradingsymbol="CRUDEOILM19AUG26",
        quantity=10,
        discloseqty=0,
        price_type="LMT",
        price=7500.00,  # Below market limit price to test broker acceptance without bad fill
        trigger_price=None,
        retention="DAY",
        remarks="GeminiProTest"
    )

    print("Shoonya place_order response:")
    print(json.dumps(ret, indent=2))

    # Also check order book
    orders = api.get_order_book()
    print("Order book count:", len(orders) if isinstance(orders, list) else orders)

if __name__ == "__main__":
    test_live_order_submission()
