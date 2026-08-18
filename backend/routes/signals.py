import logging
import datetime
import requests
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException
from backend.config import settings
from backend.signal_writer import KNOWN_SCHEMAS

logger = logging.getLogger("routes.signals")
router = APIRouter(prefix="/api/signals", tags=["Signals"])

def _supabase_headers():
    return {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

@router.get("/summary")
async def get_signals_summary():
    """Returns last_signal_time and row_count for all 7 signal tables"""
    summary = {}
    total_signals = 0
    now_str = datetime.datetime.now().strftime("%Y-%m-%d")

    for tbl in KNOWN_SCHEMAS.keys():
        try:
            url = f"{settings.SUPABASE_URL}/rest/v1/{tbl}?select=Timestamp&order=Timestamp.desc&limit=1"
            r = requests.get(url, headers=_supabase_headers(), timeout=3)
            last_time = "N/A"
            if r.status_code == 200 and r.json():
                last_time = r.json()[0].get("Timestamp", "N/A")
            
            # Count approximation
            cnt_url = f"{settings.SUPABASE_URL}/rest/v1/{tbl}?select=Symbol"
            r_cnt = requests.get(cnt_url, headers={**_supabase_headers(), "Prefer": "count=exact"}, timeout=3)
            cnt = len(r_cnt.json()) if r_cnt.status_code == 200 and isinstance(r_cnt.json(), list) else 0
            
            summary[tbl] = {
                "table": tbl,
                "count": cnt,
                "last_signal_time": last_time
            }
            total_signals += cnt
        except Exception:
            summary[tbl] = {"table": tbl, "count": 0, "last_signal_time": "N/A"}

    return {
        "success": True,
        "total_active_signals": total_signals,
        "tables": summary
    }

@router.get("/{table_name}")
async def get_signals_for_table(table_name: str, limit: int = Query(default=50)):
    """Fetches recent signal rows from target Supabase table"""
    if table_name not in KNOWN_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Unknown signal table: {table_name}")

    try:
        url = f"{settings.SUPABASE_URL}/rest/v1/{table_name}?order=Timestamp.desc&limit={limit}"
        r = requests.get(url, headers=_supabase_headers(), timeout=4)
        if r.status_code == 200:
            return {"success": True, "table": table_name, "signals": r.json()}
        return {"success": False, "table": table_name, "signals": [], "error": r.text}
    except Exception as e:
        return {"success": False, "table": table_name, "signals": [], "error": str(e)}
