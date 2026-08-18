"""
Oracle / Shoonya Trading Configuration for Indian Markets (NSE, NFO, MCX).
"""
import os
import datetime

# Supabase default settings from Oracle
SUPABASE_URL = os.getenv("ORACLE_SUPABASE_URL", "https://gshiddtlkiihwnxvxzle.supabase.co")
SUPABASE_ANON_KEY = os.getenv("ORACLE_SUPABASE_KEY", "sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F")

PAPER_TRADING_TABLE = "Paper Trading"
PROFIT_LOG_TABLE = "Profit Log"

# Shoonya Credentials
SHOONYA_CRED_PATH = os.getenv("SHOONYA_CRED_PATH", "D:/family/oracle/Paper trading bot 7/cred.yaml")

# 5 Source Signal Tables
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

# Stock Signal to Option Conversion ("OPTIONS", "STOCK", "BOTH")
STOCK_SIGNAL_MODE = "OPTIONS"
OPTIONS_EXCHANGE = "NFO"
OPTION_CHAIN_STRIKE_WINDOW = 10
OPTIONS_TARGET_PCT_OF_PREMIUM = 0.30      # +30% target
OPTIONS_STOP_LOSS_PCT_OF_PREMIUM = 0.15   # -15% stop loss

# Capital Allocation (INR)
TOTAL_BUDGET_INR = 500_000.0              # Rs 5,00,000 Budget
CAPITAL_BUFFER_PCT = 0.30                 # 30% Buffer (Rs 1.5L reserved)
DEPLOYABLE_BUDGET_INR = TOTAL_BUDGET_INR * (1 - CAPITAL_BUFFER_PCT)  # Rs 3.5L deployable
MAX_ALLOCATION_PER_TRADE_PCT = 0.08       # 8% max per trade (Rs 40,000 max)
MAX_ALLOCATION_PER_TRADE_INR = TOTAL_BUDGET_INR * MAX_ALLOCATION_PER_TRADE_PCT
MIN_TRADE_VALUE_INR = 3_000.0

# Trailing SL rules
TRAIL_RULES = {
    "INTRADAY": {"trail_trigger_pct": 0.02, "trail_step_pct": 0.01},
    "BTST":     {"trail_trigger_pct": 0.03, "trail_step_pct": 0.015},
    "WEEKLY":   {"trail_trigger_pct": 0.05, "trail_step_pct": 0.02},
}

# Partial profit booking
PARTIAL_BOOKING_TRIGGER_PCT_OF_TARGET = 0.5   # 50% way to target
PARTIAL_BOOKING_FRACTION = 0.5                # Book 50% qty

# Brokerage & Statutory Rates (Shoonya Finvasia)
BROKERAGE_RATES = {
    "EQUITY_DELIVERY": {"mode": "flat", "pct": 0.0, "flat": 0.0},
    "EQUITY_INTRADAY": {"mode": "lower_of", "pct": 0.0003, "flat": 5.0},
    "FUTURES":         {"mode": "lower_of", "pct": 0.0003, "flat": 5.0},
    "OPTIONS":         {"mode": "flat", "pct": 0.0, "flat": 5.0},
}
GST_PCT = 0.18
EXCHANGE_TXN_CHARGE_PCT = 0.0000325
STT_INTRADAY_SELL_PCT = 0.00025
STT_DELIVERY_PCT = 0.001
STT_OPTIONS_SELL_PCT = 0.0015
STT_FUTURES_SELL_PCT = 0.0005
SEBI_CHARGE_PCT = 0.000001
STAMP_DUTY_BUY_PCT = 0.00003
DP_CHARGE_PER_SCRIP_INR = 9.0
