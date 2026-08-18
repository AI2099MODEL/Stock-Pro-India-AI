import asyncio
import logging
import datetime
from typing import Dict, Any, List
from backend.brokers.shoonya import shoonya_client
from backend.signal_writer import write_signal
import yfinance as yf

logger = logging.getLogger("scanner.loop")

# Core active watchlist: MCX commodities + Major Index ETFs / Equities
DEFAULT_WATCHLIST = [
    {"symbol": "CRUDEOIL", "exchange": "MCX", "table": "mcx_intraday_signals"},
    {"symbol": "NATURALGAS", "exchange": "MCX", "table": "mcx_intraday_signals"},
    {"symbol": "GOLD", "exchange": "MCX", "table": "mcx_intraday_signals"},
    {"symbol": "SILVER", "exchange": "MCX", "table": "mcx_intraday_signals"},
    {"symbol": "RELIANCE", "exchange": "NSE", "table": "intraday_signals"},
    {"symbol": "TCS", "exchange": "NSE", "table": "intraday_signals"},
    {"symbol": "HDFCBANK", "exchange": "NSE", "table": "intraday_signals"},
    {"symbol": "INFY", "exchange": "NSE", "table": "intraday_signals"},
    {"symbol": "NIFTYBEES", "exchange": "NSE", "table": "index_breakout_signals"},
    {"symbol": "BANKBEES", "exchange": "NSE", "table": "index_breakout_signals"}
]

class ScannerEngine:
    def __init__(self):
        self.is_running = False
        self.interval_seconds = 60
        self.watchlist = DEFAULT_WATCHLIST
        self.last_scan_time = None
        self.signals_fired_count = 0
        self._task = None

    def evaluate_technical_signal(self, symbol: str, ltp: float, close: float) -> Optional[Dict[str, Any]]:
        """
        Evaluates breakout and momentum conditions.
        Returns signal dict if breakout condition met, else None.
        """
        if ltp <= 0 or close <= 0:
            return None

        pct_change = round(((ltp - close) / close) * 100, 2)
        
        # Bullish Breakout Condition (> +1.2% intraday momentum)
        if pct_change >= 1.2:
            target = round(ltp * 1.025, 2)
            stop_loss = round(ltp * 0.988, 2)
            return {
                "Symbol": symbol,
                "Signal": "BUY",
                "Price": ltp,
                "Target": target,
                "StopLoss": stop_loss,
                "Strategy": "ORACLE_BREAKOUT_MOMENTUM",
                "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # Bearish Breakdown Condition (< -1.2% intraday momentum)
        elif pct_change <= -1.2:
            target = round(ltp * 0.975, 2)
            stop_loss = round(ltp * 1.012, 2)
            return {
                "Symbol": symbol,
                "Signal": "SELL",
                "Price": ltp,
                "Target": target,
                "StopLoss": stop_loss,
                "Strategy": "ORACLE_BREAKDOWN_MOMENTUM",
                "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        return None

    async def scan_once(self):
        """Executes single pass across watchlist"""
        self.last_scan_time = datetime.datetime.now().strftime("%H:%M:%S")
        for item in self.watchlist:
            sym = item["symbol"]
            exch = item["exchange"]
            tbl = item["table"]

            # 1. Fetch live quote from Shoonya if connected, else fallback to yfinance
            ltp = 0.0
            close = 0.0
            quote_res = shoonya_client.get_ltp(sym, exch)
            if quote_res.get("success") and quote_res.get("data"):
                ltp = quote_res["data"]["ltp"]
                close = quote_res["data"]["close"]
            else:
                # Fallback quote
                try:
                    yf_sym = f"{sym}.NS" if exch == "NSE" else f"{sym}=F"
                    t = yf.Ticker(yf_sym)
                    fi = getattr(t, "fast_info", {})
                    ltp = float(fi.get("lastPrice") or 0.0)
                    close = float(fi.get("previousClose") or ltp)
                except Exception:
                    pass

            if ltp > 0:
                sig = self.evaluate_technical_signal(sym, ltp, close)
                if sig:
                    res = write_signal(tbl, sig)
                    if res.get("success"):
                        self.signals_fired_count += 1
                        logger.info(f"Fired & saved signal: {sig} -> {tbl}")

    async def _loop(self):
        while self.is_running:
            try:
                await self.scan_once()
            except Exception as e:
                logger.error(f"Scanner loop exception: {e}")
            await asyncio.sleep(self.interval_seconds)

    def start(self) -> Dict[str, Any]:
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._loop())
            return {"success": True, "message": "Scanner started", "interval_seconds": self.interval_seconds}
        return {"success": True, "message": "Scanner is already running"}

    def stop(self) -> Dict[str, Any]:
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
            return {"success": True, "message": "Scanner stopped"}
        return {"success": True, "message": "Scanner was not running"}

scanner_engine = ScannerEngine()
