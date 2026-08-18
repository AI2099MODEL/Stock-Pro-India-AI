import os
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("broker.dhan")

class DhanBroker:
    """
    Dhan HQ Open API v2 Connectivity Module
    Safely wraps Dhan Free Open API with structured {success, data, error} returns.
    Never logs or exposes tokens, passwords, or secrets.
    """
    def __init__(self):
        self.client_id = os.getenv("DHAN_CLIENT_ID", "")
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
        self.base_url = "https://api.dhan.co/v2"

    def _headers(self, custom_client_id: Optional[str] = None, custom_token: Optional[str] = None) -> Dict[str, str]:
        cid = (custom_client_id or self.client_id).strip()
        tok = (custom_token or self.access_token).strip()
        return {
            "access-token": tok,
            "client-id": cid,
            "Content-Type": "application/json"
        }

    def get_fund_limits(self, client_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
        headers = self._headers(client_id, access_token)
        if not headers["access-token"] or not headers["client-id"]:
            return {"success": False, "data": None, "error": "Dhan credentials not configured"}
        try:
            r = requests.get("https://api.dhan.co/fundlimit", headers=headers, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json(), "error": None}
            return {"success": False, "data": None, "error": f"Dhan HTTP {r.status_code}: {r.text[:100]}"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_holdings(self, client_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
        headers = self._headers(client_id, access_token)
        if not headers["access-token"] or not headers["client-id"]:
            return {"success": False, "data": [], "error": "Dhan credentials not configured"}
        try:
            r = requests.get(f"{self.base_url}/holdings", headers=headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return {"success": True, "data": data, "error": None}
                return {"success": True, "data": [], "error": None}
            return {"success": False, "data": [], "error": f"Dhan HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_positions(self, client_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
        headers = self._headers(client_id, access_token)
        if not headers["access-token"] or not headers["client-id"]:
            return {"success": False, "data": [], "error": "Dhan credentials not configured"}
        try:
            r = requests.get(f"{self.base_url}/positions", headers=headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return {"success": True, "data": data, "error": None}
                return {"success": True, "data": [], "error": None}
            return {"success": False, "data": [], "error": f"Dhan HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_order_book(self, client_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
        headers = self._headers(client_id, access_token)
        if not headers["access-token"] or not headers["client-id"]:
            return {"success": False, "data": [], "error": "Dhan credentials not configured"}
        try:
            r = requests.get(f"{self.base_url}/orders", headers=headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return {"success": True, "data": data, "error": None}
                return {"success": True, "data": [], "error": None}
            return {"success": False, "data": [], "error": f"Dhan HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def test_connection(self) -> Dict[str, Any]:
        """Tests Dhan connection and prints status only (never tokens/secrets)"""
        res = self.get_fund_limits()
        is_ok = res.get("success", False)
        status_text = "Operational" if is_ok else "Disconnected"
        print(f"[Dhan Connectivity Test]: {status_text}")
        return {"success": is_ok, "data": {"status": status_text, "provider": "Dhan HQ v2"}, "error": res.get("error")}

dhan_client = DhanBroker()
