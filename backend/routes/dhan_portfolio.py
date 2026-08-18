import asyncio
import logging
import time
from typing import Dict, Any, List
from fastapi import APIRouter, Header
from backend.brokers.dhan import dhan_client
import yfinance as yf

logger = logging.getLogger("routes.dhan_portfolio")
router = APIRouter(prefix="/api/dhan", tags=["Dhan Portfolio"])

# In-memory portfolio cache
_cached_portfolio: Dict[str, Any] = {
    "connected": False,
    "holdings": [],
    "positions": [],
    "net_worth": 0.0,
    "invested_capital": 0.0,
    "available_margin": 0.0,
    "day_pnl": 0.0,
    "overall_pnl": 0.0,
    "last_updated": 0
}

def _calculate_portfolio_data(client_id: str = "", access_token: str = "") -> Dict[str, Any]:
    global _cached_portfolio
    fund_res = dhan_client.get_fund_limits(client_id, access_token)
    holdings_res = dhan_client.get_holdings(client_id, access_token)
    pos_res = dhan_client.get_positions(client_id, access_token)

    connected = fund_res.get("success", False) or holdings_res.get("success", False)
    if not connected:
        return {
            "connected": False,
            "holdings": [],
            "positions": [],
            "net_worth": 0.0,
            "invested_capital": 0.0,
            "available_margin": 0.0,
            "day_pnl": 0.0,
            "overall_pnl": 0.0,
            "last_updated": time.time(),
            "status_text": "Disconnected"
        }

    raw_holdings = holdings_res.get("data", [])
    raw_positions = pos_res.get("data", [])
    funds = fund_res.get("data", {}) or {}

    available_margin = float(funds.get("availabelBalance") or funds.get("availableBalance") or 0.0)
    total_invested = 0.0
    total_net_worth = available_margin
    total_day_pnl = 0.0
    processed_holdings = []

    for h in raw_holdings:
        sym = h.get("tradingSymbol", "").strip()
        qty = int(h.get("totalQty") or h.get("availableQty") or 0)
        avg = float(h.get("avgCostPrice") or 0.0)
        invested = round(qty * avg, 2)
        total_invested += invested

        # Estimate live price via yfinance or holdings
        cmp = float(h.get("ltp") or 0.0)
        if cmp <= 0 and sym:
            try:
                yf_sym = f"{sym}.BO" if sym == "BSE" else f"{sym}.NS"
                t = yf.Ticker(yf_sym)
                cmp = float(getattr(t, "fast_info", {}).get("lastPrice") or avg)
            except Exception:
                cmp = avg

        current_val = round(qty * cmp, 2)
        pnl = round(current_val - invested, 2)
        pnl_pct = round((pnl / invested * 100), 2) if invested > 0 else 0.0
        total_net_worth += current_val

        processed_holdings.append({
            "symbol": sym,
            "exchange": h.get("exchange", "NSE"),
            "isin": h.get("isin", ""),
            "qty": qty,
            "avg_price": avg,
            "ltp": cmp,
            "invested_val": invested,
            "current_val": current_val,
            "unrealized_pnl": pnl,
            "pnl_pct": pnl_pct
        })

    overall_pnl = round(total_net_worth - (total_invested + available_margin), 2)

    result = {
        "connected": True,
        "holdings": processed_holdings,
        "positions": raw_positions,
        "net_worth": round(total_net_worth, 2),
        "invested_capital": round(total_invested, 2),
        "available_margin": round(available_margin, 2),
        "day_pnl": round(total_day_pnl, 2),
        "overall_pnl": overall_pnl,
        "last_updated": time.time(),
        "status_text": "Live Connected"
    }
    _cached_portfolio = result
    return result

@router.get("/portfolio")
async def get_dhan_portfolio(
    x_dhan_client_id: str = Header(default=""),
    x_dhan_access_token: str = Header(default="")
):
    """Returns consolidated live Dhan portfolio (cached or live refresh)"""
    if x_dhan_client_id and x_dhan_access_token:
        # If client passes custom headers, calculate live
        return _calculate_portfolio_data(x_dhan_client_id, x_dhan_access_token)
    
    # Return in-memory cache if fresh (<15s)
    if (time.time() - _cached_portfolio.get("last_updated", 0)) < 15 and _cached_portfolio.get("connected"):
        return _cached_portfolio

    return _calculate_portfolio_data()

async def start_dhan_portfolio_polling_task():
    """Background 15s cache refresher"""
    while True:
        try:
            _calculate_portfolio_data()
        except Exception as e:
            logger.debug(f"Portfolio background poll error: {e}")
        await asyncio.sleep(15)
