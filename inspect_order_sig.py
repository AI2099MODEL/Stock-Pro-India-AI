import inspect
from NorenRestApiPy.NorenApi import NorenApi

api = NorenApi(host="https://api.shoonya.com/NorenWClientAPI/", websocket="wss://api.shoonya.com/NorenWSAPI/")
print("place_order signature:", inspect.signature(api.place_order))
print("place_order doc:", api.place_order.__doc__)
