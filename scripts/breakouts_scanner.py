#!/usr/bin/env python3
"""
breakouts_scanner.py

Parallel NSE stock breakout scanner. Implements the 9-algorithm composite
scoring engine (VWAP, EMA9/21, RSI14, MACD, Supertrend, Volume/RVOL,
Bollinger Bands, Stochastic, N-day High/Low) ported from the mobile app's
TechnicalAnalysis.kt / StockTradingLogicEngine.kt spec. Scans the stock
universe concurrently via a thread pool (I/O-bound on broker API calls),
scores each stock 0-100, and writes every stock clearing the gate to the
Supabase `breakouts` table.

Run: python3 breakouts_scanner.py
"""

from __future__ import annotations

import os
import sys
import json
import time as time_module
import logging
import traceback
import fcntl
from dataclasses import dataclass, asdict
from datetime import datetime, time as dtime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import yaml
from NorenRestApiPy.NorenApi import NorenApi
import pandas as pd
import numpy as np
import requests

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
SCAN_POLL_SECONDS = 60
MAX_WORKERS = 8  # concurrent broker calls -- tune against Shoonya rate limits

# --------------------------------------------------------------------------- #
# UNIVERSE -- placeholder. Replace with your actual scan list (Nifty50 /
# Nifty500 / F&O universe / custom watchlist). Kept short here so the script
# is runnable out of the box without a large hardcoded list going stale.
# --------------------------------------------------------------------------- #
NSE_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "LT", "KOTAKBANK",
]

CANDLE_INTERVAL_MINUTES = 5
DAILY_HISTORY_DAYS = 220

# --- Algo params, taken directly from the spec doc ---
EMA_FAST, EMA_SLOW = 9, 21
RSI_PERIOD = 14
RSI_BULLISH_LOW, RSI_BULLISH_HIGH = 55, 70   # "sweet spot" bullish momentum expansion
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 80                          # exhaustion risk penalty threshold
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
SUPERTREND_PERIOD, SUPERTREND_MULT = 10, 3.0
RVOL_LOOKBACK = 20
RVOL_SURGE_MULT = 2.0
BB_PERIOD, BB_STD = 20, 2.0
BB_SQUEEZE_BANDWIDTH_PCT = 4.0                # bandwidth below this = squeeze; tune per instrument
STOCH_PERIOD, STOCH_SMOOTH_K, STOCH_SMOOTH_D = 14, 3, 3
STOCH_OVERSOLD_ZONE = 20
STOCH_NEUTRAL_ZONE = 50
N_DAY_HIGH_SHORT, N_DAY_HIGH_LONG = 20, 50
ATR_PERIOD = 14

# --- Composite score weights, taken directly from the spec doc ---
SCORE_VWAP = (15, 25)                # +15 to +25
SCORE_EMA_CROSSOVER = 28
SCORE_EMA_TREND_CONTINUATION = 10
SCORE_RSI_BULLISH_EXPANSION = 20
SCORE_RSI_OVERSOLD_REVERSAL = 25
SCORE_RSI_EXHAUSTION_PENALTY = -10
SCORE_MACD_FRESH_CROSS = 35
SCORE_MACD_ALREADY_BULLISH = 15
SCORE_SUPERTREND_FRESH_FLIP = 30
SCORE_SUPERTREND_WHILE_GREEN = 10
SCORE_RVOL_SURGE = 25
SCORE_BB_SQUEEZE_BREAKOUT = 25
SCORE_BB_UPPER_RIDE = 20
SCORE_STOCH_OVERSOLD_CROSS = 20
SCORE_STOCH_BULLISH_CROSS = 10
SCORE_20D_HIGH = 40
SCORE_50D_HIGH = 50

INTRADAY_SCORE_GATE = 60             # composite >= this + 1 primary trigger
BTST_SCORE_GATE = 60                 # confluence + day gain + supertrend/vol green, entered only after 3:00 PM
BTST_MIN_DAY_GAIN_PCT = 2.0          # placeholder -- confirm against your app's actual threshold

# --- Target / Stop-loss, taken directly from the spec doc ---
ATR_SL_MULT = 1.5
TARGET1_RR = 1.8
TARGET2_RR = 3.0
SWING_LOW_LOOKBACK_DAYS = 5

# --------------------------------------------------------------------------- #
# UNIVERSE FILE -- nifty200_list.csv is expected in the same folder as this
# script. Any single-column CSV works; header can be "Symbol", "SYMBOL",
# "Ticker" or unlabeled (first column is used as a fallback).
# --------------------------------------------------------------------------- #
UNIVERSE_CSV_PATH = os.environ.get(
    "UNIVERSE_CSV_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "nifty200_list.csv"),
)

# --------------------------------------------------------------------------- #
# CAPITAL / POSITION SIZING -- Rs 1,00,000 total capital. Sizing is
# risk-based: qty is derived from how many rupees you're willing to lose if
# the initial stop is hit, not from "buy as many shares as capital allows"
# (which is how a lot of scanner scripts silently blow up account risk on a
# single low-priced, wide-ATR stock). With capital this size, 1% risk/trade
# (~Rs 1,000) and a max of 3 concurrent positions is the "wise spending"
# balance -- enough slots to diversify signal risk without spreading Rs 1L
# so thin that charges (Rs ~20-70/round-trip) eat an outsized share of any
# single trade's profit.
# --------------------------------------------------------------------------- #
TRADING_CAPITAL = float(os.environ.get("TRADING_CAPITAL", "100000"))       # total capital, INR
RISK_PER_TRADE_PCT = float(os.environ.get("RISK_PER_TRADE_PCT", "1.0"))    # % of capital risked per trade
MAX_NOTIONAL_PER_TRADE_PCT = 0.33   # hard cap: no single position > 33% of capital in notional value
MAX_CONCURRENT_POSITIONS = int(os.environ.get("MAX_CONCURRENT_POSITIONS", "3"))
MIS_LEVERAGE = float(os.environ.get("MIS_LEVERAGE", "1.0"))   # 1.0 = no margin/leverage -- fully cash-backed

# --------------------------------------------------------------------------- #
# TRAILING STOP-LOSS -- two-stage trail.
#   Stage 1 (breakeven lock): once price reaches target1 (1.8R), SL jumps to
#   entry + a small buffer. A stop that merely returns you to your entry
#   price is still a net loser after charges -- see calculate_charges() --
#   so the buffer exists specifically to cover round-trip costs.
#   Stage 2 (active trail): after that, SL trails the live Supertrend line
#   (falls back to an ATR "chandelier" stop off the highest price seen since
#   entry if Supertrend is NaN). SL only ever ratchets up, never down.
# --------------------------------------------------------------------------- #
TRAIL_METHOD = os.environ.get("TRAIL_METHOD", "supertrend")   # "supertrend" | "atr_chandelier"
ATR_TRAIL_MULT = 2.0
BREAKEVEN_BUFFER_PCT = 0.0015   # ~0.15% above entry -- comfortably covers round-trip charges below

# --------------------------------------------------------------------------- #
# EXIT TIMING
# --------------------------------------------------------------------------- #
INTRADAY_SQUARE_OFF_TIME = dtime(15, 15)   # square off INTRADAY_BREAKOUT positions ahead of the 15:30 close
BTST_ENTRY_WINDOW_START = dtime(15, 0)     # BTST positions are only opened after 3:00 PM -- by request:
BTST_ENTRY_WINDOW_END = MARKET_CLOSE       # buying earlier risks an intraday reversal you'd be forced to carry home
BTST_EXIT_WINDOW_START = dtime(9, 15)      # exit BTST positions in the next session's opening window
BTST_EXIT_WINDOW_END = dtime(9, 45)

# --------------------------------------------------------------------------- #
# EXECUTION REALISM -- market/SL-M orders don't fill at the exact scanner
# price. This models a conservative per-side slippage against you.
# --------------------------------------------------------------------------- #
SLIPPAGE_PCT = float(os.environ.get("SLIPPAGE_PCT", "0.05")) / 100  # 0.05% per side, tune to instrument liquidity

# --------------------------------------------------------------------------- #
# BROKERAGE / STATUTORY CHARGES -- NSE equity INTRADAY segment only.
# Rates below are the current government + exchange levies, which are the
# same regardless of broker; only the brokerage line itself varies.
#   - Shoonya/Finvasia (this script's broker, via NorenApi) ran a genuinely
#     zero-brokerage model until 16 Dec 2024, when SEBI banned the exchange
#     rebate scheme that funded it. As of 2026 Shoonya charges Rs 5 flat OR
#     0.03% of order value, whichever is LOWER, per executed order on
#     intraday equity (delivery/equity investing remains free). This is the
#     accurate current rate -- do not assume zero brokerage anymore.
#   - "flat20" models a typical discount-broker plan for comparison: flat
#     Rs 20 or 0.03%, whichever lower, per executed order.
# Statutory components (NSE/SEBI circulars, Zerodha & Share India fee pages,
# current as of 2025/26):
#   STT (equity intraday): 0.025% on SELL turnover only
#   Exchange transaction charges (NSE): 0.00297% on BUY+SELL turnover
#   SEBI turnover fee: Rs 10/crore (0.0001%) on BUY+SELL turnover
#   Stamp duty: 0.003% on BUY turnover only (state levy, collected by exchange)
#   GST: 18% of (brokerage + exchange transaction charges + SEBI fee)
#   DP charges: not applicable -- intraday positions aren't delivered to demat
# These are statutory/exchange rates, not investment advice, and DO change --
# re-check nseindia.com / shoonya.com's tariff sheet periodically; the
# constants below are not fetched live.
# --------------------------------------------------------------------------- #
BROKERAGE_MODEL = os.environ.get("BROKERAGE_MODEL", "shoonya_2026")  # "shoonya_2026" | "flat20" | "shoonya_zero"
SHOONYA_BROKERAGE_CAP = 5.0     # Rs 5 flat cap per executed order (post Dec-2024 pricing)
SHOONYA_BROKERAGE_PCT = 0.0003  # 0.03%
FLAT20_BROKERAGE_CAP = 20.0
FLAT20_BROKERAGE_PCT = 0.0003
STT_INTRADAY_SELL_PCT = 0.00025
EXCH_TXN_NSE_PCT = 0.0000297
SEBI_TURNOVER_PCT = 0.000001   # Rs 10 per crore
STAMP_DUTY_BUY_PCT = 0.00003
GST_PCT = 0.18

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gshiddtlkiihwnxvxzle.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F")
SUPABASE_REST_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
}

LOG_LEVEL = os.environ.get("BREAKOUTS_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("breakouts_scanner")

LOCK_PATH = "/tmp/breakouts_scanner.lock"


def acquire_singleton_lock():
    lock_file = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("Another instance is already running (lock held). Exiting.")
        sys.exit(1)
    return lock_file


def insert_breakout(row: dict):
    """breakouts table is insert-only from the anon role (no UPDATE policy,
    no unique constraint) -- this is an append-only scan log, not an
    upsert-in-place table like mcx_intraday_signals. Dedup/cooldown is
    handled in-process (see ALERTED_TODAY) rather than via on_conflict."""
    row.setdefault("scanned_at", datetime.now(IST).isoformat())
    url = f"{SUPABASE_URL}/rest/v1/breakouts"
    try:
        resp = requests.post(url, headers=SUPABASE_REST_HEADERS, json=row, timeout=15)
        resp.raise_for_status()
        log.info(f"[breakouts] {row['symbol']} -> {row['setup_type']} score={row['composite_score']}")
    except Exception as e:
        log.error(f"Supabase insert failed for breakouts/{row.get('symbol')}: {e}")


def insert_paper_trade_open(row: dict) -> int | None:
    """Opens a live position row in the existing `Paper Trading` table
    (status='OPEN') and returns its id so trailing-SL updates and the final
    close can PATCH the same row. Uses Prefer: return=representation to get
    the id back in one round trip."""
    url = f"{SUPABASE_URL}/rest/v1/Paper Trading"
    headers = {**SUPABASE_REST_HEADERS, "Prefer": "return=representation"}
    try:
        resp = requests.post(url, headers=headers, json=row, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        row_id = data[0]["id"] if isinstance(data, list) and data else None
        log.info(f"[Paper Trading] OPEN {row['symbol']} qty={row['quantity']} id={row_id}")
        return row_id
    except Exception as e:
        log.error(f"Supabase insert failed for Paper Trading/{row.get('symbol')}: {e}")
        return None


def patch_paper_trade(row_id: int, updates: dict):
    """PATCHes an existing `Paper Trading` row -- used both for live
    trailing-SL/CMP updates while a position is open and for the final
    status='CLOSED' update."""
    if row_id is None:
        return
    url = f"{SUPABASE_URL}/rest/v1/Paper Trading"
    try:
        resp = requests.patch(url, headers=SUPABASE_REST_HEADERS, params={"id": f"eq.{row_id}"},
                               json=updates, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.error(f"Supabase update failed for Paper Trading id={row_id}: {e}")


def insert_profit_log(row: dict):
    """Appends one closed-trade PnL record to the existing `Profit Log`
    table -- the permanent ledger of realized (net-of-charges) results,
    independent of `Paper Trading` which reflects only the current open
    book."""
    url = f"{SUPABASE_URL}/rest/v1/Profit Log"
    try:
        resp = requests.post(url, headers=SUPABASE_REST_HEADERS, json=row, timeout=15)
        resp.raise_for_status()
        log.info(f"[Profit Log] {row['symbol']} {row['exit_reason']} net_pnl={row['net_pnl']}")
    except Exception as e:
        log.error(f"Supabase insert failed for Profit Log/{row.get('symbol')}: {e}")


def load_universe_from_csv(path: str = UNIVERSE_CSV_PATH, fallback: list[str] | None = None) -> list[str]:
    fallback = fallback if fallback is not None else NSE_UNIVERSE
    if not os.path.exists(path):
        log.warning(f"{path} not found -- falling back to the {len(fallback)}-symbol hardcoded universe.")
        return fallback
    try:
        df = pd.read_csv(path)
        col = next((c for c in ["Symbol", "SYMBOL", "symbol", "Ticker", "TICKER"] if c in df.columns), None)
        if col is None:
            col = df.columns[0]
        symbols = [s for s in df[col].astype(str).str.strip().str.upper().tolist() if s and s != "NAN"]
        if not symbols:
            raise ValueError("CSV parsed but yielded zero symbols")
        log.info(f"Loaded {len(symbols)} symbols from {path} (column='{col}')")
        return symbols
    except Exception as e:
        log.error(f"Failed to read {path}: {e} -- falling back to hardcoded universe.")
        return fallback


# --------------------------------------------------------------------------- #
# CHARGES / POSITION SIZING
# --------------------------------------------------------------------------- #

def calculate_charges(buy_price: float, sell_price: float, qty: int,
                       brokerage_model: str = BROKERAGE_MODEL) -> dict:
    """Realistic net P&L for one round-trip NSE equity INTRADAY trade
    (buy then sell same day), net of brokerage + all statutory charges.
    See the BROKERAGE / STATUTORY CHARGES config block for rate sources."""
    buy_turnover = buy_price * qty
    sell_turnover = sell_price * qty
    total_turnover = buy_turnover + sell_turnover

    if brokerage_model == "shoonya_zero":
        brokerage = 0.0
    elif brokerage_model == "shoonya_2026":
        brokerage = (min(SHOONYA_BROKERAGE_CAP, buy_turnover * SHOONYA_BROKERAGE_PCT)
                     + min(SHOONYA_BROKERAGE_CAP, sell_turnover * SHOONYA_BROKERAGE_PCT))
    elif brokerage_model == "flat20":
        brokerage = (min(FLAT20_BROKERAGE_CAP, buy_turnover * FLAT20_BROKERAGE_PCT)
                     + min(FLAT20_BROKERAGE_CAP, sell_turnover * FLAT20_BROKERAGE_PCT))
    else:
        raise ValueError(f"Unknown BROKERAGE_MODEL: {brokerage_model}")

    stt = sell_turnover * STT_INTRADAY_SELL_PCT
    exchange_txn = total_turnover * EXCH_TXN_NSE_PCT
    sebi_charges = total_turnover * SEBI_TURNOVER_PCT
    stamp_duty = buy_turnover * STAMP_DUTY_BUY_PCT
    gst = (brokerage + exchange_txn + sebi_charges) * GST_PCT
    total_charges = brokerage + stt + exchange_txn + sebi_charges + stamp_duty + gst

    gross_pnl = sell_turnover - buy_turnover
    net_pnl = gross_pnl - total_charges

    return {
        "gross_pnl": round(gross_pnl, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_txn_charges": round(exchange_txn, 2),
        "sebi_charges": round(sebi_charges, 2),
        "stamp_duty": round(stamp_duty, 2),
        "gst": round(gst, 2),
        "total_charges": round(total_charges, 2),
        "net_pnl": round(net_pnl, 2),
        "net_pnl_pct_on_capital": round(net_pnl / buy_turnover * 100, 3) if buy_turnover else 0.0,
    }


def calc_position_size(entry_price: float, stop_loss: float,
                        capital: float = TRADING_CAPITAL,
                        risk_pct: float = RISK_PER_TRADE_PCT,
                        max_notional_pct: float = MAX_NOTIONAL_PER_TRADE_PCT,
                        leverage: float = MIS_LEVERAGE) -> int:
    """Risk-based sizing: qty such that a stop-loss hit loses ~risk_pct% of
    capital, capped so no single trade's notional exceeds max_notional_pct%
    of capital x leverage (protects against a tight-SL, high-price stock
    sizing up to an absurd share count). `capital` should be the CURRENTLY
    AVAILABLE capital (total minus whatever is already reserved in open
    positions), not the total account size, so concurrent and overnight
    (BTST) positions can't jointly overdraw the account."""
    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0 or entry_price <= 0 or capital <= 0:
        return 0
    risk_amount = capital * (risk_pct / 100)
    qty_by_risk = int(risk_amount / risk_per_share)
    qty_by_notional = int((capital * max_notional_pct * leverage) / entry_price)
    return max(0, min(qty_by_risk, qty_by_notional))


# --------------------------------------------------------------------------- #
# OPEN POSITION TRACKING + TRAILING STOP-LOSS
# --------------------------------------------------------------------------- #

@dataclass
class Position:
    symbol: str
    setup_type: str
    entry_price: float          # slippage-adjusted actual fill, not the raw scanner LTP
    qty: int
    initial_sl: float
    current_sl: float
    target1: float
    target2: float
    entry_time: datetime
    r_value: float               # risk per share at entry (entry_price - initial_sl)
    target1_hit: bool = False
    highest_price_since_entry: float = 0.0
    trade_date: str = ""
    paper_trade_id: int | None = None   # row id in Supabase "Paper Trading", set once opened

    def __post_init__(self):
        if not self.highest_price_since_entry:
            self.highest_price_since_entry = self.entry_price
        if not self.trade_date:
            self.trade_date = self.entry_time.date().isoformat()


class PositionManager:
    """Tracks open paper/live positions across scan cycles, persisted to a
    local JSON file so state survives a script restart. Owns the trailing
    stop-loss ratchet and exit decisions; actual order placement (if this is
    wired to live trading rather than signal-only) is intentionally left to
    the caller -- this class only decides *when* to exit and computes the
    realistic net P&L once a price is confirmed."""

    def __init__(self, state_path: str = "/tmp/breakouts_open_positions.json"):
        self.state_path = state_path
        self.positions: dict[str, Position] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path) as f:
                raw = json.load(f)
            for sym, p in raw.items():
                p = dict(p)
                p["entry_time"] = datetime.fromisoformat(p["entry_time"])
                self.positions[sym] = Position(**p)
            if self.positions:
                log.info(f"Restored {len(self.positions)} open position(s) from {self.state_path}")
        except Exception as e:
            log.warning(f"Could not load open-positions state ({self.state_path}): {e}")

    def _save(self):
        raw = {}
        for sym, p in self.positions.items():
            d = asdict(p)
            d["entry_time"] = p.entry_time.isoformat()
            raw[sym] = d
        try:
            with open(self.state_path, "w") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            log.warning(f"Could not persist open-positions state: {e}")

    def has_open(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_count(self) -> int:
        return len(self.positions)

    def reserved_capital(self) -> float:
        """Sum of notional (entry_price x qty) tied up in currently open
        positions -- includes BTST positions still held overnight, since
        those genuinely occupy the account's cash until sold next morning."""
        return sum(p.entry_price * p.qty for p in self.positions.values())

    def available_capital(self, total_capital: float = TRADING_CAPITAL) -> float:
        return max(0.0, total_capital - self.reserved_capital())

    def open_position(self, signal: dict, now: datetime) -> Position | None:
        if self.has_open(signal["symbol"]):
            return None
        if self.open_count() >= MAX_CONCURRENT_POSITIONS:
            log.info(f"[{signal['symbol']}] Skipped -- MAX_CONCURRENT_POSITIONS ({MAX_CONCURRENT_POSITIONS}) reached.")
            return None

        raw_entry = signal["ltp"]
        entry_price = raw_entry * (1 + SLIPPAGE_PCT)   # buying costs you a bit more than the scan price
        initial_sl = signal["stop_loss"]
        available = self.available_capital()
        qty = calc_position_size(entry_price, initial_sl, capital=available)
        if qty <= 0:
            log.info(
                f"[{signal['symbol']}] Skipped -- position size computed as 0 "
                f"(SL too wide/close, or available capital Rs{available:,.0f} insufficient)."
            )
            return None

        pos = Position(
            symbol=signal["symbol"], setup_type=signal["setup_type"],
            entry_price=entry_price, qty=qty,
            initial_sl=initial_sl, current_sl=initial_sl,
            target1=signal["target1"], target2=signal["target2"],
            entry_time=now, r_value=entry_price - initial_sl,
        )

        paper_row = {
            "source_table": "breakouts", "symbol": pos.symbol,
            "exchange": "NSE", "segment": "EQ",
            "trade_type": "BUY", "strategy": pos.setup_type, "signal": "BUY",
            "entry_price": round(entry_price, 2), "cmp": round(entry_price, 2),
            "stop_loss": round(initial_sl, 2), "target_price": round(pos.target2, 2),
            "trailing_stop_loss": round(initial_sl, 2),
            "highest_price": round(entry_price, 2), "lowest_price": round(entry_price, 2),
            "quantity": qty, "status": "OPEN",
            "entry_time": now.isoformat(), "last_checked_at": now.isoformat(),
            "trade_date": pos.trade_date,
            "invested_amount": round(entry_price * qty, 2),
            "details": {"target1": pos.target1, "r_value": pos.r_value, "composite_score": signal.get("composite_score")},
        }
        pos.paper_trade_id = insert_paper_trade_open(paper_row)

        self.positions[pos.symbol] = pos
        self._save()
        log.info(
            f"[OPEN] {pos.symbol} {pos.setup_type} qty={qty} entry={entry_price:.2f} "
            f"SL={initial_sl:.2f} T1={pos.target1:.2f} T2={pos.target2:.2f} "
            f"notional=Rs{entry_price * qty:,.0f} capital_remaining=Rs{self.available_capital():,.0f}"
        )
        return pos

    def update_trailing_sl(self, pos: Position, latest_price: float,
                            latest_supertrend: float | None, latest_atr: float):
        """Ratchets current_sl upward only -- it never loosens."""
        pos.highest_price_since_entry = max(pos.highest_price_since_entry, latest_price)

        if not pos.target1_hit and latest_price >= pos.target1:
            pos.target1_hit = True
            breakeven_sl = pos.entry_price * (1 + BREAKEVEN_BUFFER_PCT)
            pos.current_sl = max(pos.current_sl, breakeven_sl)
            log.info(f"[TRAIL] {pos.symbol} hit target1 ({pos.target1:.2f}) -- SL -> breakeven {pos.current_sl:.2f}")

        if pos.target1_hit:
            if TRAIL_METHOD == "supertrend" and latest_supertrend is not None and not pd.isna(latest_supertrend):
                candidate = latest_supertrend
            else:
                candidate = pos.highest_price_since_entry - ATR_TRAIL_MULT * latest_atr
            if candidate > pos.current_sl:
                pos.current_sl = candidate
                log.info(f"[TRAIL] {pos.symbol} SL trailed up -> {pos.current_sl:.2f}")

        patch_paper_trade(pos.paper_trade_id, {
            "cmp": round(latest_price, 2),
            "trailing_stop_loss": round(pos.current_sl, 2),
            "highest_price": round(pos.highest_price_since_entry, 2),
            "last_checked_at": datetime.now(IST).isoformat(),
        })

    def check_exit(self, pos: Position, latest_price: float, now: datetime) -> str | None:
        if latest_price <= pos.current_sl:
            return "TRAIL_SL_HIT" if pos.target1_hit else "SL_HIT"
        if latest_price >= pos.target2:
            return "TARGET2_HIT"
        if pos.setup_type == "BTST" and pos.trade_date != now.date().isoformat():
            if BTST_EXIT_WINDOW_START <= now.time() <= BTST_EXIT_WINDOW_END:
                return "BTST_NEXT_DAY_EXIT"
        if pos.setup_type == "INTRADAY_BREAKOUT" and now.time() >= INTRADAY_SQUARE_OFF_TIME:
            return "EOD_SQUARE_OFF"
        return None

    def close_position(self, pos: Position, raw_exit_price: float, exit_reason: str, now: datetime) -> dict:
        # SL/square-off exits are market-ish orders that slip against you;
        # a clean target hit is closer to a limit fill, so only discount the
        # unfavorable exit types for slippage.
        if exit_reason in ("SL_HIT", "TRAIL_SL_HIT", "EOD_SQUARE_OFF", "BTST_NEXT_DAY_EXIT"):
            exit_price = raw_exit_price * (1 - SLIPPAGE_PCT)
        else:
            exit_price = raw_exit_price

        charges = calculate_charges(pos.entry_price, exit_price, pos.qty)
        elapsed_minutes = round((now - pos.entry_time).total_seconds() / 60, 1)

        patch_paper_trade(pos.paper_trade_id, {
            "status": "CLOSED",
            "cmp": round(exit_price, 2), "exit_price": round(exit_price, 2),
            "exit_reason": exit_reason, "exit_time": now.isoformat(),
            "pnl": charges["gross_pnl"], "pnl_percent": charges["net_pnl_pct_on_capital"],
            "brokerage": charges["brokerage"], "net_pnl": charges["net_pnl"],
            "time_elapsed_minutes": elapsed_minutes,
            "last_checked_at": now.isoformat(),
        })

        insert_profit_log({
            "paper_trade_id": pos.paper_trade_id, "source_table": "breakouts",
            "symbol": pos.symbol, "exchange": "NSE", "segment": "EQ",
            "trade_type": "BUY", "strategy": pos.setup_type, "signal": "BUY",
            "entry_price": round(pos.entry_price, 2), "exit_price": round(exit_price, 2),
            "stop_loss": round(pos.initial_sl, 2), "target_price": round(pos.target2, 2),
            "trailing_stop_loss": round(pos.current_sl, 2), "exit_reason": exit_reason,
            "quantity": pos.qty, "pnl": charges["gross_pnl"], "pnl_percent": charges["net_pnl_pct_on_capital"],
            "invested_amount": round(pos.entry_price * pos.qty, 2), "net_pnl": charges["net_pnl"],
            "time_elapsed_minutes": elapsed_minutes, "event_type": "FULL_EXIT",
        })

        record = {
            "symbol": pos.symbol, "setup_type": pos.setup_type,
            "entry_price": round(pos.entry_price, 2), "exit_price": round(exit_price, 2), "qty": pos.qty,
            "entry_time": pos.entry_time.isoformat(), "exit_time": now.isoformat(),
            "exit_reason": exit_reason, "trade_date": pos.trade_date,
            **charges,
        }
        del self.positions[pos.symbol]
        self._save()
        log.info(
            f"[CLOSE] {pos.symbol} {exit_reason} exit={exit_price:.2f} "
            f"gross={charges['gross_pnl']} charges={charges['total_charges']} net={charges['net_pnl']}"
        )
        return record


def manage_open_positions(pm: PositionManager):
    """Runs once per scan cycle, before scanning for new setups: refreshes
    each open position's latest price/indicators, applies the trailing-SL
    ratchet, and closes anything that has hit its stop, target, or exit
    window. Reuses get_intraday_candles + the same indicator functions as
    score_stock so the trailing Supertrend/ATR match what generated the
    original signal."""
    if not pm.positions:
        return
    now = datetime.now(IST)
    for symbol in list(pm.positions.keys()):
        pos = pm.positions[symbol]
        try:
            intraday = get_intraday_candles(symbol)
            if intraday.empty or len(intraday) < ATR_PERIOD + 2:
                continue
            df = intraday.copy()
            df["atr"] = atr(df, ATR_PERIOD)
            st_line, _ = supertrend(df)
            df["supertrend"] = st_line
            latest = df.iloc[-1]
            latest_price = float(latest["close"])
            latest_atr = float(latest["atr"]) if not pd.isna(latest["atr"]) else (latest["high"] - latest["low"])
            latest_supertrend = float(latest["supertrend"]) if not pd.isna(latest["supertrend"]) else None

            pm.update_trailing_sl(pos, latest_price, latest_supertrend, latest_atr)
            exit_reason = pm.check_exit(pos, latest_price, now)
            if exit_reason:
                exit_price = pos.target2 if exit_reason == "TARGET2_HIT" else latest_price
                pm.close_position(pos, exit_price, exit_reason, now)
        except Exception as e:
            log.warning(f"Position management failed for {symbol}: {e}")


# --------------------------------------------------------------------------- #
# SHOONYA CONNECTION -- shared credential path with mcx_scanner.py
# --------------------------------------------------------------------------- #

CRED_PATH = "/home/ubuntu/Stock-Pro-India/cred.yaml"


def load_shoonya_client() -> NorenApi:
    with open(CRED_PATH) as f:
        cred = yaml.safe_load(f)
    client = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSAPI/",
    )
    client.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])
    return client


SHOONYA = load_shoonya_client()

TOKEN_CACHE: dict = {}


def resolve_nse_token(symbol: str) -> dict:
    if symbol in TOKEN_CACHE:
        return TOKEN_CACHE[symbol]
    ret = SHOONYA.searchscrip(exchange="NSE", searchtext=symbol)
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"searchscrip failed for {symbol}: {ret}")
    exact = [v for v in ret["values"] if v["tsym"].upper() == f"{symbol.upper()}-EQ"]
    if not exact:
        raise RuntimeError(f"no NSE equity tsym found for {symbol}")
    info = {"token": exact[0]["token"], "tsym": exact[0]["tsym"], "exch": "NSE"}
    TOKEN_CACHE[symbol] = info
    return info


def get_intraday_candles(symbol: str, minutes: int = CANDLE_INTERVAL_MINUTES) -> pd.DataFrame:
    c = resolve_nse_token(symbol)
    day_start = datetime.combine(datetime.now(IST).date(), MARKET_OPEN, tzinfo=IST)
    ret = SHOONYA.get_time_price_series(
        exchange=c["exch"], token=c["token"],
        starttime=str(int(day_start.timestamp())),
        endtime=str(int(datetime.now(IST).timestamp())),
        interval=str(minutes),
    )
    if not ret:
        return pd.DataFrame()
    rows = []
    for r in ret:
        rows.append({
            "time": datetime.strptime(r["time"], "%d-%m-%Y %H:%M:%S"),
            "open": float(r["into"]), "high": float(r["inth"]),
            "low": float(r["intl"]), "close": float(r["intc"]),
            "volume": float(r["intv"]),
        })
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


def get_daily_candles(symbol: str, days: int = DAILY_HISTORY_DAYS) -> pd.DataFrame:
    c = resolve_nse_token(symbol)
    end = datetime.now(IST)
    start = end - timedelta(days=days * 2)
    ret = SHOONYA.get_daily_price_series(
        exchange=c["exch"], tradingsymbol=c["tsym"],
        startdate=str(int(start.timestamp())), enddate=str(int(end.timestamp())),
    )
    if not ret:
        return pd.DataFrame()
    rows = []
    for raw in ret:
        r = raw if isinstance(raw, dict) else __import__("json").loads(raw)
        rows.append({
            "time": datetime.strptime(r["time"], "%d-%b-%Y"),
            "open": float(r["into"]), "high": float(r["inth"]),
            "low": float(r["intl"]), "close": float(r["intc"]),
            "volume": float(r["intv"]),
        })
    return pd.DataFrame(rows).sort_values("time").tail(days).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# INDICATORS
# --------------------------------------------------------------------------- #

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def supertrend(df: pd.DataFrame, period: int = SUPERTREND_PERIOD, mult: float = SUPERTREND_MULT):
    """Standard Supertrend: upper/lower bands from ATR around (H+L)/2, with
    band-flip logic on close crossing the trailing band."""
    hl2 = (df["high"] + df["low"]) / 2
    a = atr(df, period)
    upper_basic = hl2 + mult * a
    lower_basic = hl2 - mult * a

    upper = upper_basic.copy()
    lower = lower_basic.copy()
    direction = pd.Series(index=df.index, dtype=object)  # "up" / "down"
    st = pd.Series(index=df.index, dtype=float)

    for i in range(len(df)):
        if i == 0 or pd.isna(a.iloc[i]):
            direction.iloc[i] = "up"
            st.iloc[i] = lower_basic.iloc[i] if not pd.isna(lower_basic.iloc[i]) else df["close"].iloc[i]
            continue
        if upper_basic.iloc[i] < upper.iloc[i - 1] or df["close"].iloc[i - 1] > upper.iloc[i - 1]:
            upper.iloc[i] = upper_basic.iloc[i]
        else:
            upper.iloc[i] = upper.iloc[i - 1]
        if lower_basic.iloc[i] > lower.iloc[i - 1] or df["close"].iloc[i - 1] < lower.iloc[i - 1]:
            lower.iloc[i] = lower_basic.iloc[i]
        else:
            lower.iloc[i] = lower.iloc[i - 1]

        prev_dir = direction.iloc[i - 1]
        if prev_dir == "up":
            direction.iloc[i] = "down" if df["close"].iloc[i] < lower.iloc[i] else "up"
        else:
            direction.iloc[i] = "up" if df["close"].iloc[i] > upper.iloc[i] else "down"
        st.iloc[i] = lower.iloc[i] if direction.iloc[i] == "up" else upper.iloc[i]

    return st, direction


def bollinger_bands(series: pd.Series, period: int = BB_PERIOD, num_std: float = BB_STD):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    bandwidth = (upper - lower) / mid.replace(0, np.nan) * 100
    return upper, mid, lower, bandwidth


def stochastic(df: pd.DataFrame, period: int = STOCH_PERIOD, smooth_k: int = STOCH_SMOOTH_K,
               smooth_d: int = STOCH_SMOOTH_D):
    low_min = df["low"].rolling(period).min()
    high_max = df["high"].rolling(period).max()
    raw_k = (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan) * 100
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vp = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    return cum_vp / cum_vol


# --------------------------------------------------------------------------- #
# 9-ALGORITHM COMPOSITE SCORING ENGINE
# --------------------------------------------------------------------------- #

def score_stock(symbol: str, intraday: pd.DataFrame, daily: pd.DataFrame) -> dict | None:
    """Runs all 9 algorithms against one stock's data and returns a dict with
    the composite score, per-algo diagnostics, and derived SL/target -- or
    None if there isn't enough data yet to score."""
    min_intraday = max(EMA_SLOW, MACD_SLOW + MACD_SIGNAL, RSI_PERIOD, BB_PERIOD, STOCH_PERIOD) + 2
    if intraday.empty or len(intraday) < min_intraday:
        return None
    if daily.empty or len(daily) < N_DAY_HIGH_LONG + 1:
        return None

    df = intraday.copy()
    df["vwap"] = vwap(df)
    df["ema_fast"] = ema(df["close"], EMA_FAST)
    df["ema_slow"] = ema(df["close"], EMA_SLOW)
    df["rsi14"] = rsi(df["close"], RSI_PERIOD)
    macd_line, macd_signal, macd_hist = macd(df["close"])
    df["macd_line"], df["macd_signal"], df["macd_hist"] = macd_line, macd_signal, macd_hist
    df["atr"] = atr(df, ATR_PERIOD)
    st_line, st_dir = supertrend(df)
    df["supertrend"], df["supertrend_dir"] = st_line, st_dir
    bb_u, bb_m, bb_l, bb_bw = bollinger_bands(df["close"])
    df["bb_upper"], df["bb_mid"], df["bb_lower"], df["bb_bandwidth"] = bb_u, bb_m, bb_l, bb_bw
    k, d = stochastic(df)
    df["stoch_k"], df["stoch_d"] = k, d

    latest, prev = df.iloc[-1], df.iloc[-2]
    close = latest["close"]

    score = 0
    triggers = {}
    primary_trigger = False

    # 1. VWAP dynamic bias -- institutions paying a premium above VWAP
    if not pd.isna(latest["vwap"]) and close > latest["vwap"]:
        vwap_premium_pct = (close - latest["vwap"]) / latest["vwap"] * 100
        vwap_pts = SCORE_VWAP[0] + min(SCORE_VWAP[1] - SCORE_VWAP[0], vwap_premium_pct * 5)
        score += vwap_pts
        triggers["vwap_bias"] = round(vwap_pts, 1)

    # 2. EMA 9/21 golden crossover
    golden_cross = (not pd.isna(prev["ema_fast"]) and not pd.isna(prev["ema_slow"])
                     and prev["ema_fast"] <= prev["ema_slow"] and latest["ema_fast"] > latest["ema_slow"])
    steady_trend = (not pd.isna(latest["ema_fast"]) and not pd.isna(latest["ema_slow"])
                     and latest["ema_fast"] > latest["ema_slow"])
    if golden_cross:
        score += SCORE_EMA_CROSSOVER
        triggers["ema_golden_cross"] = SCORE_EMA_CROSSOVER
        primary_trigger = True
    elif steady_trend:
        score += SCORE_EMA_TREND_CONTINUATION
        triggers["ema_trend_continuation"] = SCORE_EMA_TREND_CONTINUATION

    # 3. RSI14 momentum range
    r = latest["rsi14"]
    if not pd.isna(r):
        if RSI_BULLISH_LOW <= r <= RSI_BULLISH_HIGH:
            score += SCORE_RSI_BULLISH_EXPANSION
            triggers["rsi_bullish_expansion"] = SCORE_RSI_BULLISH_EXPANSION
        elif r <= RSI_OVERSOLD and not pd.isna(prev["rsi14"]) and prev["rsi14"] < r:
            score += SCORE_RSI_OVERSOLD_REVERSAL
            triggers["rsi_oversold_reversal"] = SCORE_RSI_OVERSOLD_REVERSAL
        elif r >= RSI_OVERBOUGHT:
            score += SCORE_RSI_EXHAUSTION_PENALTY
            triggers["rsi_exhaustion_penalty"] = SCORE_RSI_EXHAUSTION_PENALTY

    # 4. MACD bullish crossover
    fresh_macd_cross = (not pd.isna(prev["macd_line"]) and not pd.isna(prev["macd_signal"])
                          and prev["macd_line"] <= prev["macd_signal"]
                          and latest["macd_line"] > latest["macd_signal"])
    already_bullish_macd = (not pd.isna(latest["macd_line"]) and not pd.isna(latest["macd_signal"])
                              and latest["macd_line"] > latest["macd_signal"])
    if fresh_macd_cross:
        score += SCORE_MACD_FRESH_CROSS
        triggers["macd_fresh_cross"] = SCORE_MACD_FRESH_CROSS
        primary_trigger = True
    elif already_bullish_macd:
        score += SCORE_MACD_ALREADY_BULLISH
        triggers["macd_already_bullish"] = SCORE_MACD_ALREADY_BULLISH

    # 5. Supertrend flip
    fresh_st_flip = (prev["supertrend_dir"] == "down" and latest["supertrend_dir"] == "up")
    if fresh_st_flip:
        score += SCORE_SUPERTREND_FRESH_FLIP
        triggers["supertrend_fresh_flip"] = SCORE_SUPERTREND_FRESH_FLIP
        primary_trigger = True
    elif latest["supertrend_dir"] == "up":
        score += SCORE_SUPERTREND_WHILE_GREEN
        triggers["supertrend_while_green"] = SCORE_SUPERTREND_WHILE_GREEN

    # 6. Volume spike / RVOL surge
    avg_vol = df["volume"].iloc[:-1].tail(RVOL_LOOKBACK).mean() if len(df) > 1 else latest["volume"]
    rvol = latest["volume"] / avg_vol if avg_vol > 0 else 0
    rvol_surge = rvol >= RVOL_SURGE_MULT and close > prev["close"]
    if rvol_surge:
        score += SCORE_RVOL_SURGE
        triggers["rvol_surge"] = SCORE_RVOL_SURGE
        primary_trigger = True

    # 7. Bollinger Band squeeze & expansion
    bb_squeeze_breakout = (not pd.isna(prev["bb_bandwidth"]) and prev["bb_bandwidth"] < BB_SQUEEZE_BANDWIDTH_PCT
                             and not pd.isna(latest["bb_upper"]) and close > latest["bb_upper"])
    bb_upper_ride = (not pd.isna(latest["bb_upper"]) and close >= latest["bb_upper"])
    if bb_squeeze_breakout:
        score += SCORE_BB_SQUEEZE_BREAKOUT
        triggers["bb_squeeze_breakout"] = SCORE_BB_SQUEEZE_BREAKOUT
    elif bb_upper_ride:
        score += SCORE_BB_UPPER_RIDE
        triggers["bb_upper_ride"] = SCORE_BB_UPPER_RIDE

    # 8. Stochastic reversal
    stoch_oversold_cross = (not pd.isna(prev["stoch_k"]) and not pd.isna(prev["stoch_d"])
                              and prev["stoch_k"] <= prev["stoch_d"] and latest["stoch_k"] > latest["stoch_d"]
                              and latest["stoch_k"] < STOCH_OVERSOLD_ZONE)
    stoch_bullish_cross = (not pd.isna(prev["stoch_k"]) and not pd.isna(prev["stoch_d"])
                             and prev["stoch_k"] <= prev["stoch_d"] and latest["stoch_k"] > latest["stoch_d"]
                             and latest["stoch_k"] < STOCH_NEUTRAL_ZONE)
    if stoch_oversold_cross:
        score += SCORE_STOCH_OVERSOLD_CROSS
        triggers["stoch_oversold_cross"] = SCORE_STOCH_OVERSOLD_CROSS
    elif stoch_bullish_cross:
        score += SCORE_STOCH_BULLISH_CROSS
        triggers["stoch_bullish_cross"] = SCORE_STOCH_BULLISH_CROSS

    # 9. 20-day / 50-day multi-day high breakout
    hist20 = daily["close"].tail(N_DAY_HIGH_SHORT)
    hist50 = daily["close"].tail(N_DAY_HIGH_LONG)
    day20_high = float(hist20.max())
    day50_high = float(hist50.max())
    if close > day50_high:
        score += SCORE_50D_HIGH
        triggers["50day_high_breakout"] = SCORE_50D_HIGH
        primary_trigger = True
    elif close > day20_high:
        score += SCORE_20D_HIGH
        triggers["20day_high_breakout"] = SCORE_20D_HIGH
        primary_trigger = True

    # --- Target / Stop-loss: ATR + 5-day swing low ---
    latest_atr = latest["atr"] if not pd.isna(latest["atr"]) else (latest["high"] - latest["low"])
    swing_low = float(daily["low"].tail(SWING_LOW_LOOKBACK_DAYS).min())
    stop_loss = min(close - ATR_SL_MULT * latest_atr, swing_low)
    risk = close - stop_loss
    target1 = close + risk * TARGET1_RR
    target2 = close + risk * TARGET2_RR

    # --- Final selection gate ---
    setup_type = None
    if score >= INTRADAY_SCORE_GATE and primary_trigger:
        setup_type = "INTRADAY_BREAKOUT"

    now = datetime.now(IST)
    day_open = float(daily["open"].iloc[-1]) if not daily.empty else None
    day_gain_pct = (close - day_open) / day_open * 100 if day_open else 0
    in_btst_window = BTST_ENTRY_WINDOW_START <= now.time() <= BTST_ENTRY_WINDOW_END
    btst_confirm = latest["supertrend_dir"] == "up" or rvol_surge
    if (score >= BTST_SCORE_GATE and day_gain_pct >= BTST_MIN_DAY_GAIN_PCT
            and in_btst_window and btst_confirm):
        setup_type = "BTST"  # overrides INTRADAY_BREAKOUT if both qualify late in session

    if setup_type is None:
        return {"symbol": symbol, "composite_score": round(score, 1), "setup_type": None}

    return {
        "symbol": symbol,
        "ltp": float(close),
        "vwap": float(latest["vwap"]) if not pd.isna(latest["vwap"]) else None,
        "ema9": float(latest["ema_fast"]),
        "ema21": float(latest["ema_slow"]),
        "day_high": float(df["high"].max()),
        "day_low": float(df["low"].min()),
        "n_day_high": day20_high,
        "day20_high": day20_high,
        "day50_high": day50_high,
        "rsi14": float(r) if not pd.isna(r) else None,
        "macd_line": float(latest["macd_line"]) if not pd.isna(latest["macd_line"]) else None,
        "macd_signal": float(latest["macd_signal"]) if not pd.isna(latest["macd_signal"]) else None,
        "macd_hist": float(latest["macd_hist"]) if not pd.isna(latest["macd_hist"]) else None,
        "supertrend": float(latest["supertrend"]) if not pd.isna(latest["supertrend"]) else None,
        "supertrend_direction": latest["supertrend_dir"],
        "bb_upper": float(latest["bb_upper"]) if not pd.isna(latest["bb_upper"]) else None,
        "bb_mid": float(latest["bb_mid"]) if not pd.isna(latest["bb_mid"]) else None,
        "bb_lower": float(latest["bb_lower"]) if not pd.isna(latest["bb_lower"]) else None,
        "bb_bandwidth": float(latest["bb_bandwidth"]) if not pd.isna(latest["bb_bandwidth"]) else None,
        "stoch_k": float(latest["stoch_k"]) if not pd.isna(latest["stoch_k"]) else None,
        "stoch_d": float(latest["stoch_d"]) if not pd.isna(latest["stoch_d"]) else None,
        "volume": float(latest["volume"]),
        "avg_volume": float(avg_vol),
        "rvol": round(float(rvol), 2),
        "atr14": float(latest_atr),
        "stop_loss": round(float(stop_loss), 2),
        "target1": round(float(target1), 2),
        "target2": round(float(target2), 2),
        "composite_score": round(float(score), 1),
        "setup_type": setup_type,
        "signal": "BUY",
        "exchange": "NSE",
        "segment": "EQ",
        "details": triggers,
    }


# --------------------------------------------------------------------------- #
# PARALLEL SCAN
# --------------------------------------------------------------------------- #

ALERTED_TODAY: set = set()  # (symbol, setup_type, date) -- in-process cooldown;
                              # table has no unique constraint so this is the
                              # only dedup layer (see insert_breakout docstring)


def scan_one(symbol: str) -> dict | None:
    try:
        intraday = get_intraday_candles(symbol)
        daily = get_daily_candles(symbol)
        result = score_stock(symbol, intraday, daily)
        return result
    except Exception as e:
        log.warning(f"Scan failed for {symbol}: {e}")
        return None


def run_parallel_scan(universe: list[str], pm: PositionManager):
    trade_date = datetime.now(IST).date().isoformat()
    now = datetime.now(IST)
    cycle_start = time_module.monotonic()
    scanned, failed, fired, opened = 0, 0, 0, 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scan_one, symbol): symbol for symbol in universe}
        for future in as_completed(futures):
            symbol = futures[future]
            result = future.result()
            if result is None:
                failed += 1
                continue
            scanned += 1
            if not result.get("setup_type"):
                continue
            key = (symbol, result["setup_type"], trade_date)
            if key in ALERTED_TODAY:
                continue
            insert_breakout(result)   # append-only scan log, independent of whether we actually take the trade
            ALERTED_TODAY.add(key)
            fired += 1

            if not pm.has_open(symbol) and pm.open_count() < MAX_CONCURRENT_POSITIONS:
                if pm.open_position(result, now):
                    opened += 1

    elapsed = time_module.monotonic() - cycle_start
    log.info(
        f"Cycle done in {elapsed:.1f}s | scanned={scanned}/{len(universe)} "
        f"failed={failed} breakouts_fired={fired} positions_opened={opened} "
        f"open_now={pm.open_count()}"
    )


def is_market_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def main():
    _lock = acquire_singleton_lock()
    log.info("Starting breakouts scanner")
    universe = load_universe_from_csv()
    log.info(f"Loaded {len(universe)} NSE symbols (MAX_WORKERS={MAX_WORKERS})")
    log.info(
        f"Capital=Rs{TRADING_CAPITAL:,.0f} risk/trade={RISK_PER_TRADE_PCT}% "
        f"max_concurrent={MAX_CONCURRENT_POSITIONS} brokerage_model={BROKERAGE_MODEL}"
    )

    pm = PositionManager()

    last_date = None
    while True:
        now = datetime.now(IST)
        if now.date() != last_date:
            ALERTED_TODAY.clear()
            last_date = now.date()

        # BTST next-day exit window needs to run even before regular market-open
        # scanning logic would otherwise kick in, so check it unconditionally.
        try:
            manage_open_positions(pm)
        except Exception:
            log.error("Error managing open positions:\n" + traceback.format_exc())

        if not is_market_open(now):
            log.info(f"Market closed. open_positions={pm.open_count()}. Sleeping 5 min...")
            time_module.sleep(300)
            continue

        try:
            run_parallel_scan(universe, pm)
        except Exception:
            log.error("Error in scan loop:\n" + traceback.format_exc())

        time_module.sleep(SCAN_POLL_SECONDS)


if __name__ == "__main__":
    main()
