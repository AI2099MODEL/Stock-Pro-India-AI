import inspect
from NorenRestApiPy.NorenApi import NorenApi

api = NorenApi(host="https://api.shoonya.com/NorenWClientAPI/", websocket="wss://api.shoonya.com/NorenWSAPI/")
print("NorenApi attributes/methods:")
for m in dir(api):
    if not m.startswith("__"):
        print(" ", m)

print("\nset_session signature:", inspect.signature(api.set_session))
print("\ninjectOAuthHeader source:")
print(inspect.getsource(api.injectOAuthHeader))
