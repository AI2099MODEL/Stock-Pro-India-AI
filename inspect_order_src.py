import inspect
from NorenRestApiPy.NorenApi import NorenApi

api = NorenApi(host="https://api.shoonya.com/NorenWClientAPI/", websocket="wss://api.shoonya.com/NorenWSAPI/")
print("=== place_order SOURCE ===")
print(inspect.getsource(api.place_order))

print("\n=== get_order_book SOURCE ===")
print(inspect.getsource(api.get_order_book))
