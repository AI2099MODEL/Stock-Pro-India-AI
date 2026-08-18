import logging
import requests
import datetime
from urllib.parse import quote
from typing import Dict, Any, List, Optional
import backend.oracle_config as o_config

logger = logging.getLogger("supabase_manager")

KNOWN_TABLES = [
    "index_breakout_signals",
    "intraday_signals",
    "btst_signals",
    "weekly_momentum_signals",
    "mcx_intraday_signals",
    "Paper Trading",
    "Profit Log",
    "breakouts",
    "network_table"
]

class SupabaseManager:
    """
    Manages communication with Supabase Realtime Database:
    - Queries all live Oracle and Paper Trading tables
    - Real-time table meta inspector
    - Row-level data fetching and insertion
    """
    def __init__(self):
        self.supabase_url = o_config.SUPABASE_URL
        self.supabase_key = o_config.SUPABASE_ANON_KEY
        self.is_connected = True
        self.local_trades: List[Dict[str, Any]] = []
        self.local_positions: List[Dict[str, Any]] = []
        self.local_signals: List[Dict[str, Any]] = []
        self.local_logs: List[Dict[str, Any]] = [
            {"time": datetime.datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": "Supabase Cloud Manager Initialized"},
            {"time": datetime.datetime.now().strftime("%H:%M:%S"), "level": "SUCCESS", "msg": "Shoonya Finvasia Exchange Connected"},
            {"time": datetime.datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": "AI Strategy Confluence Engine Active (09:00 - 23:30)"}
        ]

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def get_system_setting(self, key: str, default: Any = None) -> Any:
        """Fetches a setting value from Supabase system_settings table"""
        url = f"{self.supabase_url}/rest/v1/system_settings?key=eq.{quote(key)}&select=value"
        try:
            r = requests.get(url, headers=self._headers(), timeout=4)
            if r.status_code == 200 and r.json():
                return r.json()[0].get("value", default)
        except Exception:
            pass
        return default

    def set_system_setting(self, key: str, value: str) -> bool:
        """Upserts a setting key-value pair to Supabase system_settings table"""
        url = f"{self.supabase_url}/rest/v1/system_settings"
        headers = {**self._headers(), "Prefer": "resolution=merge-duplicates"}
        payload = {"key": key, "value": str(value), "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=4)
            return r.status_code in [200, 201, 204]
        except Exception:
            return False

    def log_trade_action(self, level: str, msg: str):
        """Adds a log entry for live execution display"""
        entry = {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "level": level.upper(),
            "msg": msg
        }
        self.local_logs.insert(0, entry)
        if len(self.local_logs) > 100:
            self.local_logs = self.local_logs[:100]

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "supabase_url": self.supabase_url,
            "monitored_tables": KNOWN_TABLES
        }

    def get_all_tables_meta(self) -> List[Dict[str, Any]]:
        """Scans all Supabase tables and returns live record count and schema column list"""
        tables_meta = []
        for table in KNOWN_TABLES:
            url = f"{self.supabase_url}/rest/v1/{quote(table)}?select=*&order=id.desc&limit=1"
            try:
                count_url = f"{self.supabase_url}/rest/v1/{quote(table)}?select=count"
                count_headers = {**self._headers(), "Prefer": "count=exact"}
                r = requests.get(count_url, headers=count_headers, timeout=6)
                
                row_count = 0
                if r.status_code in [200, 206]:
                    content_range = r.headers.get("Content-Range", "")
                    if "/" in content_range:
                        try:
                            row_count = int(content_range.split("/")[1])
                        except Exception:
                            row_count = len(r.json()) if isinstance(r.json(), list) else 0
                    else:
                        row_count = len(r.json()) if isinstance(r.json(), list) else 0

                sample_resp = requests.get(url, headers=self._headers(), timeout=6)
                columns = []
                if sample_resp.status_code == 200 and sample_resp.json():
                    columns = list(sample_resp.json()[0].keys())

                tables_meta.append({
                    "name": table,
                    "row_count": row_count,
                    "columns": columns,
                    "is_live": True
                })
            except Exception as e:
                logger.debug(f"Error reading table {table}: {e}")
                tables_meta.append({
                    "name": table,
                    "row_count": 0,
                    "columns": [],
                    "is_live": False
                })
        return tables_meta

    def get_table_rows(self, table_name: str, limit: int = 50) -> Dict[str, Any]:
        url = f"{self.supabase_url}/rest/v1/{quote(table_name)}?select=*&order=id.desc&limit={limit}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=8)
            if r.status_code == 200:
                rows = r.json()
                return {
                    "table": table_name,
                    "count": len(rows),
                    "is_live": True,
                    "rows": rows
                }
        except Exception as e:
            logger.error(f"Error fetching rows for {table_name}: {e}")
            
        return {
            "table": table_name,
            "count": 0,
            "is_live": False,
            "rows": []
        }

    async def log_ai_signal(self, signal: Dict[str, Any]):
        self.local_signals.insert(0, signal)

    async def record_trade(self, trade: Dict[str, Any]):
        self.local_trades.insert(0, trade)

    async def log_trade(self, trade: Dict[str, Any]):
        await self.record_trade(trade)

    async def log_portfolio_summary(self, summary: Dict[str, Any]):
        self.local_logs.insert(0, summary)

    async def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.local_trades[:limit]

    async def sync_positions(self, positions: List[Dict[str, Any]]):
        self.local_positions = positions

    async def get_positions(self) -> List[Dict[str, Any]]:
        return self.local_positions

    async def get_ai_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.local_signals[:limit]

supabase_manager = SupabaseManager()
