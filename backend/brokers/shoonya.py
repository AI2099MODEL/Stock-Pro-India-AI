import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("broker.shoonya")

class ShoonyaBroker:
    """
    Shoonya (Finvasia) Broker Connectivity Module
    Safely wraps NorenRestApiPy / REST API with structured result dicts.
    Never logs or exposes tokens, passwords, or secrets.
    """
    def __init__(self):
        self.user_id = os.getenv("SHOONYA_USER_ID", "")
        self.password = os.getenv("SHOONYA_PASSWORD", "")
        self.totp_secret = os.getenv("SHOONYA_TOTP_SECRET", "")
        self.vendor_code = os.getenv("SHOONYA_VENDOR_CODE", "")
        self.api_secret = os.getenv("SHOONYA_API_SECRET", "")
        self.imei = os.getenv("SHOONYA_IMEI", "")
        self.access_token = os.getenv("SHOONYA_ACCESS_TOKEN", "")
        self.base_url = "https://api.shoonya.com/NorenWClientAPI/"
        self.ws_url = "wss://api.shoonya.com/NorenWSAPI/"
        self.api = None
        self._init_api()

    def _init_api(self):
        try:
            from NorenRestApiPy.NorenApi import NorenApi
            self.api = NorenApi(host=self.base_url, websocket=self.ws_url)
        except ImportError:
            self.api = None
            logger.warning("NorenRestApiPy not installed. Operating in REST mode.")

    def login(self, uid: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        target_uid = (uid or self.user_id).strip()
        target_token = (token or self.access_token).strip()

        if not target_token:
            return {"success": False, "data": None, "error": "No Shoonya access token provided."}

        try:
            if self.api:
                self.api.injectOAuthHeader(target_token, target_uid, target_uid)
                limits = self.api.get_limits()
                if limits and limits.get("stat") == "Ok":
                    self.access_token = target_token
                    self.user_id = target_uid
                    return {"success": True, "data": {"status": "Connected", "actid": target_uid}, "error": None}
                elif limits and limits.get("stat") == "Not_Ok":
                    return {"success": False, "data": None, "error": limits.get("emsg", "Session expired or invalid token")}

            # Fallback to direct REST limits check
            jdata = json.dumps({"uid": target_uid, "actid": target_uid})
            r = requests.post(
                f"{self.base_url}Limits",
                data=f"jData={jdata}&jKey={target_token}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=5
            )
            res = r.json()
            if res.get("stat") == "Ok":
                self.access_token = target_token
                self.user_id = target_uid
                return {"success": True, "data": {"status": "Connected", "actid": target_uid}, "error": None}
            return {"success": False, "data": None, "error": res.get("emsg", "Login failed")}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def is_session_valid(self) -> bool:
        if not self.access_token:
            return False
        try:
            res = self.login(self.user_id, self.access_token)
            return res.get("success", False)
        except Exception:
            return False

    def logout(self) -> Dict[str, Any]:
        self.access_token = ""
        return {"success": True, "data": {"status": "Logged out"}, "error": None}

    def get_positions(self) -> Dict[str, Any]:
        if not self.access_token:
            return {"success": False, "data": [], "error": "Shoonya not connected"}
        try:
            if self.api:
                pos = self.api.get_positions()
                if pos and isinstance(pos, list):
                    return {"success": True, "data": pos, "error": None}
            jdata = json.dumps({"uid": self.user_id, "actid": self.user_id})
            r = requests.post(f"{self.base_url}PositionBook", data=f"jData={jdata}&jKey={self.access_token}", timeout=5)
            res = r.json()
            if isinstance(res, list):
                return {"success": True, "data": res, "error": None}
            return {"success": True, "data": [], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_holdings(self) -> Dict[str, Any]:
        if not self.access_token:
            return {"success": False, "data": [], "error": "Shoonya not connected"}
        try:
            if self.api:
                holdings = self.api.get_holdings()
                if holdings and isinstance(holdings, list):
                    return {"success": True, "data": holdings, "error": None}
            jdata = json.dumps({"uid": self.user_id, "actid": self.user_id})
            r = requests.post(f"{self.base_url}Holdings", data=f"jData={jdata}&jKey={self.access_token}", timeout=5)
            res = r.json()
            if isinstance(res, list):
                return {"success": True, "data": res, "error": None}
            return {"success": True, "data": [], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_ltp(self, symbol: str, exchange: str = "NSE", token: Optional[str] = None) -> Dict[str, Any]:
        if not self.access_token:
            return {"success": False, "data": None, "error": "Shoonya not connected"}
        try:
            t = token or symbol
            jdata = json.dumps({"uid": self.user_id, "exch": exchange, "token": t})
            r = requests.post(f"{self.base_url}GetQuotes", data=f"jData={jdata}&jKey={self.access_token}", timeout=4)
            res = r.json()
            if res.get("stat") == "Ok":
                lp = float(res.get("lp") or res.get("c") or 0.0)
                return {"success": True, "data": {"symbol": symbol, "exchange": exchange, "ltp": lp, "close": float(res.get("c") or lp)}, "error": None}
            return {"success": False, "data": None, "error": res.get("emsg", "Quote unavailable")}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def place_order(self, symbol: str, exchange: str, side: str, quantity: int, product_type: str = "M", order_type: str = "MKT", price: float = 0.0, trigger_price: float = 0.0) -> Dict[str, Any]:
        if not self.access_token:
            return {"success": False, "data": None, "error": "Shoonya session not active"}
        try:
            bs = "B" if side.upper() in ["BUY", "B"] else "S"
            prctyp = "MKT" if order_type.upper() in ["MKT", "MARKET"] else "LMT"
            prd = "I" if product_type.upper() in ["MIS", "I", "INTRADAY"] else "C"
            
            payload = {
                "uid": self.user_id,
                "actid": self.user_id,
                "exch": exchange,
                "tsym": symbol,
                "qty": str(quantity),
                "prc": str(price) if prctyp == "LMT" else "0",
                "prd": prd,
                "trantype": bs,
                "prctyp": prctyp,
                "ret": "DAY"
            }
            if trigger_price > 0:
                payload["trgprc"] = str(trigger_price)
                payload["prctyp"] = "SL-LMT"

            jdata = json.dumps(payload)
            r = requests.post(f"{self.base_url}PlaceOrder", data=f"jData={jdata}&jKey={self.access_token}", timeout=5)
            res = r.json()
            if res.get("stat") == "Ok":
                return {"success": True, "data": {"order_id": res.get("norenordno"), "status": "SUBMITTED"}, "error": None}
            return {"success": False, "data": None, "error": res.get("emsg", "Order rejected")}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def test_connection(self) -> Dict[str, Any]:
        valid = self.is_session_valid()
        status_text = "Operational" if valid else "Disconnected"
        print(f"[Shoonya Connectivity Test]: {status_text}")
        return {"success": valid, "data": {"status": status_text, "provider": "Shoonya Finvasia"}, "error": None if valid else "Invalid session"}

shoonya_client = ShoonyaBroker()
