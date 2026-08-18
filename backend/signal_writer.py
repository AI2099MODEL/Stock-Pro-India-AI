import os
import json
import logging
import datetime
from typing import Dict, Any, Optional
import requests
from backend.config import settings

# Setup dedicated logger for signal writes
logger = logging.getLogger("signal_writer")
logger.setLevel(logging.INFO)

log_file = "signal_writer.log"
fh = logging.FileHandler(log_file, encoding="utf-8")
fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
if not logger.handlers:
    logger.addHandler(fh)

KNOWN_SCHEMAS = {
    "intraday_signals": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"],
    "mcx_intraday_signals": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"],
    "btst_signals": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"],
    "weekly_momentum_signals": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"],
    "stock_options_signals": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"],
    "index_breakout_signals": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"],
    "breakouts": ["Symbol", "Signal", "Price", "Target", "StopLoss", "Strategy", "Timestamp"]
}

def validate_signal_payload(table_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizes and validates signal payload for table insertion"""
    cleaned = dict(payload)
    if "Symbol" not in cleaned and "symbol" in cleaned:
        cleaned["Symbol"] = cleaned["symbol"]
    if "Signal" not in cleaned and "signal" in cleaned:
        cleaned["Signal"] = cleaned["signal"]
    if "Price" not in cleaned and "price" in cleaned:
        cleaned["Price"] = cleaned["price"]
    if "Target" not in cleaned and "target" in cleaned:
        cleaned["Target"] = cleaned["target"]
    if "StopLoss" not in cleaned and "stop_loss" in cleaned:
        cleaned["StopLoss"] = cleaned["stop_loss"]
    if "Strategy" not in cleaned and "strategy" in cleaned:
        cleaned["Strategy"] = cleaned["strategy"]
    if "Timestamp" not in cleaned and "timestamp" in cleaned:
        cleaned["Timestamp"] = cleaned["timestamp"]
    elif "Timestamp" not in cleaned:
        cleaned["Timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return cleaned

def write_signal(table_name: str, signal_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and writes signal payload to Supabase target table.
    Logs every write attempt (table, symbol, signal, success/failure) to signal_writer.log.
    """
    if table_name not in KNOWN_SCHEMAS:
        err = f"Unknown target table: {table_name}"
        logger.error(err)
        return {"success": False, "error": err}

    normalized = validate_signal_payload(table_name, signal_dict)
    sym = normalized.get("Symbol", "UNKNOWN")
    sig = normalized.get("Signal", "HOLD")

    supabase_url = settings.SUPABASE_URL
    supabase_key = settings.SUPABASE_KEY

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    try:
        url = f"{supabase_url}/rest/v1/{table_name}"
        r = requests.post(url, headers=headers, json=normalized, timeout=5)
        if r.status_code in [200, 201]:
            logger.info(f"SUCCESS: Inserted signal for {sym} ({sig}) into {table_name}")
            return {"success": True, "data": r.json(), "error": None}
        else:
            err = f"FAILED [{r.status_code}]: {r.text}"
            logger.error(f"FAILED: Insert signal for {sym} ({sig}) into {table_name}: {err}")
            return {"success": False, "error": err}
    except Exception as e:
        err = str(e)
        logger.error(f"EXCEPTION: Insert signal for {sym} ({sig}) into {table_name}: {err}")
        return {"success": False, "error": err}
