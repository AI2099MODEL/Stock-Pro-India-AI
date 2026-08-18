import yaml
import json
import requests

cred = yaml.safe_load(open('/home/ubuntu/Stock-Pro-India/login/cred.yaml'))
headers = {
    'Authorization': f"Bearer {cred['Access_token']}",
    'Content-Type': 'application/json'
}

values = {
    'ordersource': 'API',
    'uid': cred['UID'],
    'actid': cred['Account_ID'],
    'trantype': 'B',
    'prd': 'M',
    'exch': 'MCX',
    'tsym': 'CRUDEOILM19AUG26',
    'qty': '10',
    'dscqty': '0',
    'prctyp': 'LMT',
    'prc': '7500.0',
    'trgprc': 'None',
    'ret': 'DAY',
    'remarks': 'VPSTest'
}

r = requests.post('https://api.shoonya.com/NorenWClientAPI/PlaceOrder', data='jData=' + json.dumps(values), headers=headers, timeout=10)
print('VPS PlaceOrder Response:', r.text)
