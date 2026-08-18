import time
import os
import csv
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import yfinance as yf

logger = logging.getLogger("nifty200_service")

CSV_PATH = Path(__file__).resolve().parent / "nifty200.csv"

def load_nifty200_from_csv() -> List[str]:
    symbols = []
    if CSV_PATH.exists():
        try:
            with open(CSV_PATH, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = row.get("Symbol", "").strip()
                    if sym:
                        symbols.append(sym)
        except Exception as e:
            logger.warning(f"Error reading nifty200.csv: {e}")
    return symbols if symbols else [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", "SBIN", "ITC", "LT", "BAJFINANCE",
        "HINDUNILVR", "KOTAKBANK", "M&M", "AXISBANK", "TITAN", "ADANIENT", "MARUTI", "SUNPHARMA", "TATAMOTORS",
        "NTPC", "ONGC", "POWERGRID", "TATASTEEL", "JSWSTEEL", "COALINDIA", "BAJAJFINSV", "ASIANPAINT", "NESTLEIND",
        "ULTRACEMCO", "GRASIM", "HCLTECH", "WIPRO", "TECHM", "LTIM", "ADANIPORTS", "HINDALCO", "BPCL", "HEROMOTOCO",
        "DRREDDY", "CIPLA", "APOLLOHOSP", "EICHERMOT", "DIVISLAB", "TATACONSUM", "SBILIFE", "HDFCLIFE", "BRITANNIA",
        "BAJAJ-AUTO", "SHRIRAMFIN", "BEL", "HAL", "TRENT", "ZOMATO", "JIOFIN", "VEDL", "BSE", "CDSL", "MCX"
    ]

NIFTY_200_SYMBOLS = load_nifty200_from_csv()

class Nifty200Service:
    def __init__(self):
        self.symbols = NIFTY_200_SYMBOLS
        self._price_cache: Dict[str, Dict[str, Any]] = {}

    def get_all_symbols(self) -> List[str]:
        return self.symbols

    def get_realtime_quote(self, symbol: str) -> Dict[str, Any]:
        sym = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
        if sym == "M_MFIN":
            sym = "M&MFIN"
        now = time.time()
        
        if sym in self._price_cache and (now - self._price_cache[sym].get("ts", 0)) < 8:
            return self._price_cache[sym]["data"]

        yf_sym = f"{sym}.BO" if sym == "BSE" else f"{sym}.NS"
        try:
            t = yf.Ticker(yf_sym)
            fi = getattr(t, "fast_info", {})
            cmp = fi.get("lastPrice") or fi.get("regularMarketPrice") or 0.0
            prev = fi.get("previousClose") or cmp
            chg = round(cmp - prev, 2) if cmp and prev else 0.0
            chg_pct = round((chg / prev * 100), 2) if prev > 0 else 0.0
            high_24h = fi.get("dayHigh") or round(cmp * 1.02, 2)
            low_24h = fi.get("dayLow") or round(cmp * 0.98, 2)
            volume = fi.get("lastVolume") or fi.get("threeMonthAverageVolume") or 50000

            res = {
                "symbol": sym,
                "price": round(float(cmp), 2),
                "previous_close": round(float(prev), 2),
                "change": chg,
                "change_pct": chg_pct,
                "high_24h": round(float(high_24h), 2),
                "low_24h": round(float(low_24h), 2),
                "volume": int(volume),
                "exchange": "BSE" if sym == "BSE" else "NSE",
                "source": "Yahoo_Finance_Live"
            }
            self._price_cache[sym] = {"ts": now, "data": res}
            return res
        except Exception as e:
            logger.debug(f"Error fetching quote for {sym}: {e}")
            return {
                "symbol": sym,
                "price": 0.0,
                "previous_close": 0.0,
                "change": 0.0,
                "change_pct": 0.0,
                "high_24h": 0.0,
                "low_24h": 0.0,
                "volume": 0,
                "exchange": "NSE",
                "source": "Fallback"
            }

    def get_batch_quotes(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        target_syms = symbols if symbols else self.symbols[:35]
        results = []
        for s in target_syms:
            results.append(self.get_realtime_quote(s))
        return results

    def get_candles(self, symbol: str, timeframe: str = "15m", count: int = 120) -> List[Dict[str, Any]]:
        sym = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
        yf_sym = f"{sym}.BO" if sym == "BSE" else f"{sym}.NS"

        period_map = {
            "1m": ("1d", "1m"),
            "5m": ("5d", "5m"),
            "15m": ("1mo", "15m"),
            "1h": ("3mo", "1h"),
            "1D": ("1y", "1d")
        }
        period, interval = period_map.get(timeframe, ("1mo", "15m"))

        try:
            t = yf.Ticker(yf_sym)
            df = t.history(period=period, interval=interval)
            if df is not None and not df.empty:
                candles = []
                for idx, row in df.tail(count).iterrows():
                    candles.append({
                        "time": int(idx.timestamp()),
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": round(float(row["Volume"]), 2)
                    })
                return candles
        except Exception as e:
            logger.warning(f"Yahoo Finance candle fetch failed for {sym}: {e}")

        return []

nifty200_engine = Nifty200Service()

