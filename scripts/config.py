"""
Central configuration for the paper trading bot.
"""
import datetime

# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------
SUPABASE_URL = "https://gshiddtlkiihwnxvxzle.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F"

PAPER_TRADING_TABLE = "Paper Trading"
PROFIT_LOG_TABLE = "Profit Log"

# ---------------------------------------------------------------------------
# Shoonya (Finvasia) session - OAuth header injection, see _get_shoonya_client()
# in trading.py. cred.yaml must contain Access_token / UID / Account_ID.
# ---------------------------------------------------------------------------
SHOONYA_CRED_PATH = "/home/ubuntu/Stock-Pro-India/cred.yaml"

SOURCE_TABLES = {
    "index_breakout_signals": {
        "trigger_column": "signal",
        "fixed_trade_type": "INTRADAY",
        "price_column": "ltp",
        "stop_loss_column": None,
        "target_column": "target_price",
        "trailing_sl_column": "trail_sl",
        "lot_size_column": "lot_size",
    },
    "mcx_intraday_signals": {
        "trigger_column": "status",
        "fixed_trade_type": "INTRADAY",
        "price_column": "price",
        "stop_loss_column": "stop_loss",
        "target_column": "target",
        "trailing_sl_column": "trailing_stop_loss",
        "lot_size_column": None,
    },
    "intraday_signals": {
        "trigger_column": "status",
        "fixed_trade_type": "INTRADAY",
        "price_column": "price",
        "stop_loss_column": "stop_loss",
        "target_column": "target",
        "trailing_sl_column": "trailing_stop_loss",
        "lot_size_column": None,
    },
    "btst_signals": {
        "trigger_column": "status",
        "fixed_trade_type": "BTST",
        "price_column": "price",
        "stop_loss_column": "stop_loss",
        "target_column": "target",
        "trailing_sl_column": "trailing_stop_loss",
        "lot_size_column": None,
    },
    "weekly_momentum_signals": {
        "trigger_column": "status",
        "fixed_trade_type": "WEEKLY",
        "price_column": "price",
        "stop_loss_column": "stop_loss",
        "target_column": "target",
        "trailing_sl_column": "trailing_stop_loss",
        "lot_size_column": None,
    },
}

# ---------------------------------------------------------------------------
# Stock-signal -> ATM option conversion
#
# When a signal comes from a STOCK-based source table (everything above
# except mcx_intraday_signals - MCX is commodity, left trading its own
# future directly), the bot can trade the underlying's nearest at-the-money
# option instead of the stock itself: bullish signal -> buy the ATM CE,
# bearish/short signal -> buy the ATM PE. Direction is read from the same
# `signal` field _is_short() already uses in trading.py.
#
# STOCK_SIGNAL_MODE:
#   "OPTIONS" - trade the ATM option instead of the stock (default here,
#               since that's what you asked for)
#   "STOCK"   - ignore this feature, trade the stock directly (old behavior)
#   "BOTH"    - log both a stock trade AND an option trade per signal
#               (roughly doubles capital usage per signal - be sure that's
#               really what you want before switching to this)
STOCK_SIGNAL_MODE = "OPTIONS"

# Tables eligible for conversion. MCX intentionally excluded - it's
# commodity futures, not NSE equity options.
OPTIONS_ENABLED_SOURCE_TABLES = {
    "index_breakout_signals",
    "intraday_signals",
    "btst_signals",
    "weekly_momentum_signals",
}

OPTIONS_EXCHANGE = "NFO"

# How many strikes on EACH side of spot to pull back from Shoonya when
# hunting for the true ATM strike (searchscrip returns every expiry/strike
# for the symbol - this just bounds how much we fetch before filtering).
OPTION_CHAIN_STRIKE_WINDOW = 10

# Options don't move 1:1 with the underlying (premium reflects delta, theta,
# IV - not just the stock's own price move), so the stock signal's
# stop_loss/target price levels can't be copied onto the option directly.
# These are % of ENTRY PREMIUM instead - same kind of placeholder as
# TRAIL_RULES below: tell me your real numbers if these aren't right.
OPTIONS_TARGET_PCT_OF_PREMIUM = 0.30      # book at +30% of entry premium
OPTIONS_STOP_LOSS_PCT_OF_PREMIUM = 0.15   # cut at -15% of entry premium

# Fallback lot size if Shoonya's searchscrip response doesn't carry "ls"
# for some reason - should essentially never be used, but decide_quantity()
# needs *some* lot_size to size the trade.
OPTIONS_FALLBACK_LOT_SIZE = 1

# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------
SIGNAL_SCAN_INTERVAL_SECONDS = 60
PRICE_UPDATE_INTERVAL_SECONDS = 60

# ---------------------------------------------------------------------------
# Market / session hours (IST - VPS clock must be IST or adjust with a tz lib)
# ---------------------------------------------------------------------------
EQUITY_INDEX_START = datetime.time(9, 15)
EQUITY_INDEX_END = datetime.time(15, 15)      # book stocks/index PNL by 3:15 PM

MCX_START = datetime.time(9, 0)
MCX_END = datetime.time(23, 15)               # MCX tradeable till 11:15 PM

MCX_SEGMENTS = {"MCX"}

# BTST: only take fresh entries up to 3 PM; try to book profit at market open
# the next day by 9:30 AM. If not in profit by then, keep it running under
# normal target/SL/trailing-SL rules.
BTST_ENTRY_CUTOFF = datetime.time(15, 0)
BTST_MORNING_CHECK_START = datetime.time(9, 15)
BTST_MORNING_CHECK_END = datetime.time(9, 30)

# ---------------------------------------------------------------------------
# Trailing SL, expressed as fraction of entry price. Used to tighten SL once
# a trade has moved favorably enough. Placeholders - tune to your rules.
# ---------------------------------------------------------------------------
TRAIL_RULES = {
    "INTRADAY": {"trail_trigger_pct": 0.02, "trail_step_pct": 0.01},
    "BTST":     {"trail_trigger_pct": 0.03, "trail_step_pct": 0.015},
    "WEEKLY":   {"trail_trigger_pct": 0.05, "trail_step_pct": 0.02},
}

EOD_SQUAREOFF_INTRADAY = True

# ---------------------------------------------------------------------------
# Capital allocation
# ---------------------------------------------------------------------------
TOTAL_BUDGET_INR = 500_000
CAPITAL_BUFFER_PCT = 0.30                      # 30% kept aside, never deployed
DEPLOYABLE_BUDGET_INR = TOTAL_BUDGET_INR * (1 - CAPITAL_BUFFER_PCT)   # 3.5L

# Cap on how much of the total budget (not just deployable) goes into any
# single scrip at entry time, so no one position dominates.
MAX_ALLOCATION_PER_TRADE_PCT = 0.08            # 8% of 5L = 40,000 per trade cap
MAX_ALLOCATION_PER_TRADE_INR = TOTAL_BUDGET_INR * MAX_ALLOCATION_PER_TRADE_PCT

# Don't bother opening a position smaller than this (avoids odd-lot noise trades)
MIN_TRADE_VALUE_INR = 3_000

# ---------------------------------------------------------------------------
# Partial profit booking: once price has moved this fraction of the way from
# entry to target, book PARTIAL_BOOKING_FRACTION of the quantity and let the
# rest run under trailing SL. Only triggers once per trade.
# ---------------------------------------------------------------------------
PARTIAL_BOOKING_TRIGGER_PCT_OF_TARGET = 0.5    # halfway to target
PARTIAL_BOOKING_FRACTION = 0.5                 # book half the quantity

# ---------------------------------------------------------------------------
# Brokerage (Shoonya/Finvasia published flat-fee structure, approximated).
# Shoonya does not expose a brokerage-calculation endpoint in its trading
# API (NorenAPI) - the "brokerage calculator" is a website tool, not an API
# call. These constants replicate their publicly published rates as closely
# as possible; treat net_pnl as a best-effort estimate and spot check
# against Shoonya's live calculator periodically since rates can change.
# ---------------------------------------------------------------------------
BROKERAGE_RATES = {
    # per executed order (leg), i.e. charged once on entry and once on exit.
    # mode "lower_of": charge = min(turnover * pct, flat)
    # mode "flat": charge = flat, regardless of turnover
    "EQUITY_DELIVERY": {"mode": "flat", "pct": 0.0, "flat": 0.0},
    "EQUITY_INTRADAY": {"mode": "lower_of", "pct": 0.0003, "flat": 5.0},   # lower of 0.03% or Rs 5
    "FUTURES":         {"mode": "lower_of", "pct": 0.0003, "flat": 5.0},  # equity/index/MCX futures
    "OPTIONS":         {"mode": "flat", "pct": 0.0, "flat": 5.0},         # flat Rs 5 + GST per order
}
GST_PCT = 0.18                       # on brokerage + exchange txn charges; also applied to DP charge separately
EXCHANGE_TXN_CHARGE_PCT = 0.0000325  # approx NSE/BSE txn charge on turnover
STT_INTRADAY_SELL_PCT = 0.00025      # STT on sell side only, intraday equity
STT_DELIVERY_PCT = 0.001             # STT on BOTH legs, equity delivery (BTST/WEEKLY)

# Post-Budget-2026 rates, effective 1 Apr 2026 (STT on F&O nearly doubled -
# futures 0.02% -> 0.05%, options premium 0.10% -> 0.15%). Verify against
# https://shoonya.com/pricing or your contract notes if these change again.
STT_OPTIONS_SELL_PCT = 0.0015        # STT on sell side, options (on premium)
STT_FUTURES_SELL_PCT = 0.0005        # STT on sell side, futures

SEBI_CHARGE_PCT = 0.000001           # Rs 10 per crore
STAMP_DUTY_BUY_PCT = 0.00003         # on buy side only

# DP (depository participant) charge: Shoonya charges Rs 9 + GST per scrip,
# per day, ONLY when delivery shares are sold (demat debit) - i.e. on
# BTST/WEEKLY equity exits, never on intraday/options/futures. Source:
# https://shoonya.com/calculators/brokerage-calculator
DP_CHARGE_PER_SCRIP_INR = 9.0

REPORTS_DIR = "reports"
