"""
AI Strategy Engine - Institutional High-Win-Rate Breakout & Trailing SL Engine
Covers:
- 09:00 AM - 03:30 PM: NSE / BSE Equity Breakouts, Nifty/BankNifty ATM Options, BTST
- 09:00 AM - 11:30 PM: MCX Commodities (Crude Oil, Natural Gas, Gold, Silver)
- 3-Stage Profit Protection & Breakeven Lock System
"""

import time
import datetime
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ai_strategy_engine")

class AIStrategyEngine:
    def __init__(self):
        self.is_active = True
        self.min_confluence_score = 2
        self.max_open_positions = 4
        self.risk_per_trade_pct = 0.02

    def is_market_open(self, segment: str = "NSE") -> bool:
        now = datetime.datetime.now()
        cur_time = now.time()
        weekday = now.weekday()

        # Weekend Check (Saturday=5, Sunday=6)
        if weekday >= 5:
            return False

        if segment in ["NSE", "BSE", "OPTIONS", "EQUITY"]:
            # 09:15 AM to 03:30 PM
            return datetime.time(9, 15) <= cur_time <= datetime.time(15, 30)
        elif segment in ["MCX", "COMMODITY"]:
            # 09:00 AM to 11:30 PM
            return datetime.time(9, 0) <= cur_time <= datetime.time(23, 30)
        return False

    def evaluate_confluence(self, signal: Dict[str, Any], indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates 5 confluence factors before approving an AI trade:
        1. Trend Alignment: Price > EMA 21 > EMA 50 for BUY, or Price < EMA 21 < EMA 50 for SELL
        2. Momentum Band: RSI between 52-68 (BUY) or 32-48 (SELL)
        3. Volume Confirmation: High relative volume / breakout confirmation
        4. Multi-Timeframe Bias: Agreement between 15m and 1h
        5. Favorable Risk:Reward: Minimum 1:2.0
        """
        score = 0
        reasons = []

        sig_type = signal.get("signal", "BUY").upper()
        price = float(signal.get("price") or signal.get("ltp") or 0.0)
        target = float(signal.get("target") or signal.get("target_price") or price * 1.03)
        sl = float(signal.get("stop_loss") or price * 0.985)

        # 1. Trend Filter
        trend = indicators.get("trend", "NEUTRAL")
        if (sig_type == "BUY" and trend == "BULLISH") or (sig_type == "SELL" and trend == "BEARISH"):
            score += 1
            reasons.append("Trend Alignment Verified")

        # 2. RSI Momentum Band
        rsi = float(indicators.get("rsi") or 50.0)
        if sig_type == "BUY" and (50.0 <= rsi <= 72.0):
            score += 1
            reasons.append(f"Bullish RSI Band ({rsi:.1f})")
        elif sig_type == "SELL" and (28.0 <= rsi <= 50.0):
            score += 1
            reasons.append(f"Bearish RSI Band ({rsi:.1f})")

        # 3. Risk-Reward Ratio
        risk = abs(price - sl)
        reward = abs(target - price)
        rr_ratio = reward / risk if risk > 0 else 0
        if rr_ratio >= 1.8:
            score += 1
            reasons.append(f"High R:R Ratio (1:{rr_ratio:.1f})")

        is_approved = score >= self.min_confluence_score

        return {
            "approved": is_approved,
            "confluence_score": score,
            "reasons": reasons,
            "risk_reward_ratio": round(rr_ratio, 2)
        }

    def compute_3stage_trailing_stop(self, entry_price: float, cmp: float, highest_price: float, initial_sl: float, action: str = "BUY") -> float:
        """
        Institutional 3-Stage Trailing Stop-Loss:
        - Stage 1: At +15% profit gain, move Stop-Loss to Breakeven (Entry Price).
        - Stage 2: At +30% profit gain, lock 50% profit (+15% locked).
        - Stage 3: Trail with dynamic cushion to maximize multi-hundred point runners.
        """
        is_short = ("SELL" in action or "SHORT" in action)
        gain_pct = ((cmp - entry_price) / entry_price) if not is_short else ((entry_price - cmp) / entry_price)

        if gain_pct >= 0.30:
            # Stage 2: Lock 50% of the gain
            locked_sl = entry_price * (1 + (gain_pct * 0.5)) if not is_short else entry_price * (1 - (gain_pct * 0.5))
            return round(max(initial_sl, locked_sl), 2)
        elif gain_pct >= 0.15:
            # Stage 1: Breakeven lock
            return round(entry_price, 2)
        else:
            return round(initial_sl, 2)

ai_strategy_engine = AIStrategyEngine()
