import time
import random
import math
from typing import Dict, List, Any

# Official Real-Time Closing & LTP from Shoonya API
BASE_PRICES = {
    "RELIANCE": 1316.00,       # NSE Reliance-EQ (LTP: Rs 1,316.00, Close: Rs 1,310.00)
    "TCS": 2313.20,            # NSE TCS-EQ (LTP: Rs 2,313.20, Close: Rs 2,361.00)
    "HDFCBANK": 729.00,        # NSE HDFCBANK-EQ (LTP: Rs 729.00, Close: Rs 727.00)
    "INFY": 1139.90,           # NSE INFY-EQ (LTP: Rs 1,139.90, Close: Rs 1,169.20)
    "CRUDEOIL": 7679.00,       # MCX Crude Oil Futures (LTP: Rs 7,679.00)
    "NATURALGAS": 257.40,      # MCX Natural Gas Futures (LTP: Rs 257.40)
    "GOLD": 154575.00,         # MCX Gold Mini (LTP: Rs 1,54,575.00)
    "SILVER": 239690.00,       # MCX Silver Mini (LTP: Rs 2,39,690.00)
    "NIFTY 50": 24650.00,
    "BANKNIFTY": 50850.00,
    "FINNIFTY": 23400.00,
    "BTC/USDT": 93500.0,
    "ETH/USDT": 3180.0,
    "SOL/USDT": 194.50
}

VOLATILITIES = {
    "RELIANCE": 0.0001,
    "TCS": 0.0001,
    "HDFCBANK": 0.0001,
    "INFY": 0.0001,
    "CRUDEOIL": 0.0002,
    "NATURALGAS": 0.0003,
    "GOLD": 0.0001,
    "SILVER": 0.0001,
    "NIFTY 50": 0.0001,
    "BANKNIFTY": 0.0001,
    "FINNIFTY": 0.0001,
    "BTC/USDT": 0.0018,
    "ETH/USDT": 0.0025,
    "SOL/USDT": 0.0035
}

class MarketEngine:
    def __init__(self):
        self.prices = {sym: price for sym, price in BASE_PRICES.items()}
        self.candles_history: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._initialize_histories()

    def _initialize_histories(self):
        # Generate initial 120 candles for each symbol and timeframe
        timeframes = ["1m", "5m", "15m", "1h", "1D"]
        for symbol, base_price in BASE_PRICES.items():
            self.candles_history[symbol] = {}
            for tf in timeframes:
                self.candles_history[symbol][tf] = self._generate_seed_candles(symbol, tf, count=120)

    def _generate_seed_candles(self, symbol: str, timeframe: str, count: int = 120) -> List[Dict[str, Any]]:
        vol = VOLATILITIES.get(symbol, 0.002)
        base = BASE_PRICES.get(symbol, 100.0)
        candles = []
        
        # Calculate time step in seconds
        tf_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "1D": 86400
        }.get(timeframe, 60)
        
        now = int(time.time())
        current_price = base * (1 + random.uniform(-0.05, 0.05))
        
        for i in range(count, 0, -1):
            ts = now - (i * tf_seconds)
            delta = current_price * vol * random.gauss(0.0005, 1.0)
            open_p = current_price
            close_p = open_p + delta
            high_p = max(open_p, close_p) + abs(random.gauss(0, delta * 0.8 if delta != 0 else open_p * 0.001))
            low_p = min(open_p, close_p) - abs(random.gauss(0, delta * 0.8 if delta != 0 else open_p * 0.001))
            volume = random.uniform(10.0, 150.0) * (base / 1000.0)
            
            candles.append({
                "time": ts,
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": round(volume, 2)
            })
            current_price = close_p
            
        self.prices[symbol] = round(current_price, 2)
        return candles

    def tick(self, symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """Advance price by 1 live micro-tick and update 1m candle"""
        vol = VOLATILITIES.get(symbol, 0.002)
        current = self.prices.get(symbol, BASE_PRICES.get(symbol, 100.0))
        
        # Small micro step
        change = current * vol * random.gauss(0.0001, 0.3)
        new_price = round(max(0.01, current + change), 2)
        self.prices[symbol] = new_price
        
        # Update current 1m candle
        history_1m = self.candles_history.get(symbol, {}).get("1m", [])
        now = int(time.time())
        
        if history_1m:
            last_candle = history_1m[-1]
            # Check if within same 60s bucket
            if now - last_candle["time"] < 60:
                last_candle["close"] = new_price
                last_candle["high"] = max(last_candle["high"], new_price)
                last_candle["low"] = min(last_candle["low"], new_price)
                last_candle["volume"] += round(random.uniform(0.1, 1.5), 2)
            else:
                # Start new candle
                new_candle = {
                    "time": now,
                    "open": last_candle["close"],
                    "high": max(last_candle["close"], new_price),
                    "low": min(last_candle["close"], new_price),
                    "close": new_price,
                    "volume": round(random.uniform(0.5, 3.0), 2)
                }
                history_1m.append(new_candle)
                if len(history_1m) > 300:
                    history_1m.pop(0)
                    
        return {
            "symbol": symbol,
            "price": new_price,
            "change": round(change, 2),
            "timestamp": now
        }

    def get_market_overview(self) -> List[Dict[str, Any]]:
        overview = []
        for sym, price in self.prices.items():
            seed = BASE_PRICES.get(sym, price)
            chg_pct = round(((price - seed) / seed) * 100, 2) if seed > 0 else 0.0
            vol_24h = round(price * random.uniform(8000, 25000), 2)
            overview.append({
                "symbol": sym,
                "price": price,
                "change_pct": chg_pct,
                "high_24h": round(price * 1.035, 2),
                "low_24h": round(price * 0.965, 2),
                "volume_24h": vol_24h
            })
        return overview

    def get_order_book(self, symbol: str = "BTC/USDT", depth: int = 10) -> Dict[str, Any]:
        mid = self.prices.get(symbol, BASE_PRICES.get(symbol, 100.0))
        spread = mid * 0.0002
        bids = []
        asks = []
        
        for i in range(1, depth + 1):
            bid_p = round(mid - (spread * i) - (mid * 0.00015 * i), 2)
            bid_vol = round(random.uniform(0.2, 3.5), 3)
            bids.append({"price": bid_p, "amount": bid_vol, "total": round(bid_p * bid_vol, 2)})
            
            ask_p = round(mid + (spread * i) + (mid * 0.00015 * i), 2)
            ask_vol = round(random.uniform(0.2, 3.5), 3)
            asks.append({"price": ask_p, "amount": ask_vol, "total": round(ask_p * ask_vol, 2)})
            
        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "spread": round(asks[0]["price"] - bids[0]["price"], 2)
        }

    def calculate_indicators(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates RSI, MACD, Bollinger Bands, and EMAs"""
        if not candles or len(candles) < 30:
            return {}

        closes = [c["close"] for c in candles]
        
        # --- EMA Calculation ---
        def ema(data, period):
            k = 2 / (period + 1)
            ema_vals = [data[0]]
            for val in data[1:]:
                ema_vals.append(val * k + ema_vals[-1] * (1 - k))
            return ema_vals

        ema9 = ema(closes, 9)[-1]
        ema21 = ema(closes, 21)[-1]
        ema50 = ema(closes, 50)[-1]
        ema200 = ema(closes, min(200, len(closes)))[-1]

        # --- RSI (14) ---
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(0, diff))
            losses.append(max(0, -diff))

        period = 14
        if len(gains) >= period:
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = round(100 - (100 / (1 + rs)), 2)
        else:
            rsi = 50.0

        # --- Bollinger Bands (20, 2) ---
        bb_period = 20
        bb_slice = closes[-bb_period:]
        bb_middle = sum(bb_slice) / bb_period
        variance = sum((x - bb_middle) ** 2 for x in bb_slice) / bb_period
        std_dev = math.sqrt(variance)
        bb_upper = round(bb_middle + (2 * std_dev), 2)
        bb_lower = round(bb_middle - (2 * std_dev), 2)
        bb_middle = round(bb_middle, 2)

        # --- MACD (12, 26, 9) ---
        ema12_series = ema(closes, 12)
        ema26_series = ema(closes, 26)
        macd_line_series = [e12 - e26 for e12, e26 in zip(ema12_series, ema26_series)]
        signal_line_series = ema(macd_line_series, 9)
        macd_line = round(macd_line_series[-1], 2)
        signal_line = round(signal_line_series[-1], 2)
        macd_hist = round(macd_line - signal_line, 2)

        # Trend Determination
        current_price = closes[-1]
        trend = "BULLISH" if current_price > ema50 and rsi > 50 else "BEARISH" if current_price < ema50 and rsi < 50 else "NEUTRAL"

        return {
            "price": current_price,
            "rsi": rsi,
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "bollinger": {
                "upper": bb_upper,
                "middle": bb_middle,
                "lower": bb_lower
            },
            "macd": {
                "macd": macd_line,
                "signal": signal_line,
                "histogram": macd_hist
            },
            "trend": trend
        }

market_engine = MarketEngine()
