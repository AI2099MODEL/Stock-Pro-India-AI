#!/usr/bin/env python3
"""
nifty200_scanner.py  (merged: stock selection -> options eligibility check)

Live Nifty200 scanner + options feed.
- Pulls candle data from Shoonya for all Nifty200 stocks
- STOCK SELECTION (intraday, runs every INTRADAY_POLL_SECONDS during market hours):
    Composite 0-100 score per stock combining:
      Trend stack (EMA9>EMA21)      25 pts
      RVOL (time-of-day-adjusted)   25 pts
      Day-high/low proximity        20 pts
      ORB breakout position         15 pts
      VWAP institutional bias       15 pts
    Score >=70 -> STRONG_BUY/STRONG_SELL (written to intraday_signals AND
                  fed into the options-eligibility check below)
    Score 40-69 -> WATCH (written, not fed to options check)
    Score <40   -> ignored, nothing written
- BTST + WEEKLY MOMENTUM (EOD, once/day at EOD_SCAN_TIME): unchanged logic
  from the original nifty200_scanner.py (resistance breakout, bullish
  engulfing, 20-day high breakout, MACD crossover, golden cross)
- OPTIONS ELIGIBILITY (fires only for STRONG_BUY/STRONG_SELL stocks):
    1. Is this stock F&O-eligible? (checked against fo_stocks_list.csv,
       auto-downloaded from NSE archives, cached in this folder)
    2. If yes: fetch spot LTP, nearest ATM/ATM+-1/ATM+-2 strikes for
       nearest expiry, pull VWAP/EMA/day-high-low per leg (same approach
       as the old index_options_scanner.py), pick CE for BUY / PE for SELL
    3. Liquidity gate: leg must have live LTP>0 and available quote depth;
       otherwise flagged NOT_TRADABLE with a reason instead of silently
       dropped, so you can see *why* a strong stock had no usable option.
    Written to stock_options_signals.
- TSL: every poll cycle, any OPEN signal in intraday_signals/btst_signals
  is re-priced and trailed (breakeven at +1xATR profit, then trails by
  0.5xATR for every further 0.5xATR gained). NOTE: the strategy doc's TSL
  section had its actual percentage thresholds stripped when pasted in
  (blank formulas) -- these ATR multiples are a reasonable placeholder,
  not the numbers from your doc. Change TSL_BREAKEVEN_ATR / TSL_STEP_ATR
  below once you send the real numbers.
- Upserts into Supabase (resolution=merge-duplicates on symbol+strategy+trade_date)
- Runs continuously, active only during NSE market hours (09:15-15:30 IST, Mon-Fri)

Run:
    python3 nifty200_scanner.py
One-time setup (creates tables):
    python3 nifty200_scanner.py --setup
"""

from __future__ import annotations

import os
import sys
import json
import time as time_module
import logging
import traceback
import subprocess
from datetime import datetime, time as dtime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import pandas as pd
import numpy as np
import requests
import yaml

from NorenRestApiPy.NorenApi import NorenApi

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
ORB_MINUTES = 15
INTRADAY_POLL_SECONDS = 60
EOD_SCAN_TIME = dtime(15, 20)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NIFTY200_CSV = os.getenv("NIFTY200_CSV", os.path.join(SCRIPT_DIR, "nifty200_list.csv"))
NIFTY200_URL = "https://archives.nseindia.com/content/indices/ind_nifty200list.csv"
FO_STOCKS_CSV = os.getenv("FO_STOCKS_CSV", os.path.join(SCRIPT_DIR, "fo_stocks_list.csv"))
FO_STOCKS_URL = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"

INTRADAY_VOLUME_MULT = 1.5          # legacy fallback only, composite score uses RVOL below
RVOL_STRONG = 2.0
RVOL_MODERATE = 1.5
SCORE_STRONG = 70
SCORE_WATCH = 40

BTST_LOOKBACK_DAYS = 20
BTST_MIN_CLOSE_STRENGTH = 0.7
WEEKLY_LOOKBACK_DAYS = 20
WEEKLY_RSI_LOW = 55
WEEKLY_RSI_HIGH = 70
ATR_PERIOD = 14
ATR_STOP_MULT = 1.5
ATR_TARGET_MULT = 3.0

# TSL -- PLACEHOLDER numbers, see module docstring. Update once you send the
# real thresholds from the strategy doc.
TSL_BREAKEVEN_ATR = 1.0     # move SL to entry once profit >= 1x ATR
TSL_STEP_ATR = 0.5          # then trail SL by 0.5x ATR for every further 0.5x ATR gained

OPTION_STRIKE_WINDOW = 2    # ATM +/- N strikes to inspect

SUPABASE_URL = "https://gshiddtlkiihwnxvxzle.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F"

SHOONYA_CRED_PATH = os.getenv("SHOONYA_CRED_PATH", "/home/ubuntu/Stock-Pro-India/cred.yaml")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("nifty200_scanner")

# --------------------------------------------------------------------------- #
# SHOONYA CLIENT
# --------------------------------------------------------------------------- #

api = NorenApi(
    host="https://api.shoonya.com/NorenWClientAPI/",
    websocket="wss://api.shoonya.com/NorenWSAPI/",
)


def shoonya_connect():
    with open(SHOONYA_CRED_PATH) as f:
        cred = yaml.safe_load(f)
    api.injectOAuthHeader(cred["Access_token"], cred["UID"], cred["Account_ID"])
    ret = api.get_limits()
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"Shoonya session invalid: {ret}")
    log.info("Shoonya session OK")
    return cred


# --------------------------------------------------------------------------- #
# SUPABASE CLIENT
# --------------------------------------------------------------------------- #

SUPABASE_REST_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

SIGNAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    id bigint generated always as identity primary key,
    symbol text not null,
    strategy text not null,
    signal text not null,
    price numeric,
    stop_loss numeric,
    target numeric,
    trailing_stop_loss numeric,
    status text default 'OPEN',
    details jsonb,
    trade_date date not null,
    signal_time timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (symbol, strategy, trade_date)
);
"""

STOCK_OPTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_options_signals (
    id bigint generated always as identity primary key,
    underlying_symbol text not null,
    underlying_signal text not null,
    underlying_score int,
    tradable boolean not null,
    reason text,
    option_symbol text,
    token text,
    strike numeric,
    option_type text,
    expiry text,
    ltp numeric,
    vwap numeric,
    ema9 numeric,
    ema21 numeric,
    lot_size int,
    money_required numeric,
    target_price numeric,
    trail_sl numeric,
    trade_date date not null,
    signal_time timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (underlying_symbol, trade_date)
);
"""

TABLE_SQL = (
    SIGNAL_TABLE_SQL.format(table="intraday_signals")
    + SIGNAL_TABLE_SQL.format(table="btst_signals")
    + SIGNAL_TABLE_SQL.format(table="weekly_momentum_signals")
    + STOCK_OPTIONS_TABLE_SQL
)


def setup_tables():
    sql_path = os.path.join(SCRIPT_DIR, "setup_tables.sql")
    with open(sql_path, "w") as f:
        f.write(TABLE_SQL)
    log.info(f"Wrote {sql_path}")

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        log.info("SUPABASE_DB_URL not set -- run setup_tables.sql once in the Supabase SQL editor")
        return
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(TABLE_SQL)
        cur.close()
        conn.close()
        log.info("Supabase tables created/verified via direct DB connection")
    except Exception as e:
        log.warning(f"Could not create tables via SUPABASE_DB_URL ({e}) -- use setup_tables.sql instead")


CRON_MARKER = "# nifty200_scanner_csv_refresh"


def install_cron():
    script_path = os.path.abspath(__file__)
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        log.warning("crontab not available -- skipping cron install")
        return
    if CRON_MARKER in existing:
        return
    line = f"0 8 * * 1-5 /usr/bin/python3 {script_path} --refresh-csv >> /tmp/nifty200_csv_refresh.log 2>&1 {CRON_MARKER}\n"
    new_crontab = existing + ("\n" if existing and not existing.endswith("\n") else "") + line
    subprocess.run(["crontab", "-"], input=new_crontab, text=True)
    log.info("Installed daily 08:00 IST cron job for CSV refresh")


def upsert_signal(table: str, row: dict, conflict_cols: str = "symbol,strategy,trade_date"):
    now_iso = datetime.now(IST).isoformat()
    row.setdefault("trade_date", datetime.now(IST).date().isoformat())
    row["signal_time"] = now_iso
    row["updated_at"] = now_iso
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict_cols}"
    try:
        resp = requests.post(url, headers=SUPABASE_REST_HEADERS, json=row, timeout=15)
        resp.raise_for_status()
        key = row.get("symbol") or row.get("underlying_symbol")
        log.info(f"[{table}] {key} -> {row.get('strategy') or row.get('underlying_signal')} ({row.get('signal') or row.get('tradable')})")
    except Exception as e:
        log.error(f"Supabase upsert failed for {table}/{row.get('symbol') or row.get('underlying_symbol')}: {e}")


def fetch_open_signals(table: str) -> list[dict]:
    url = (f"{SUPABASE_URL}/rest/v1/{table}"
           f"?status=eq.OPEN&trade_date=eq.{datetime.now(IST).date().isoformat()}&select=*")
    try:
        resp = requests.get(url, headers=SUPABASE_REST_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Supabase fetch OPEN signals failed for {table}: {e}")
        return []


# --------------------------------------------------------------------------- #
# NIFTY200 UNIVERSE
# --------------------------------------------------------------------------- #

def _nse_session() -> requests.Session:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        "Accept": "text/csv,application/csv,*/*",
    }
    session = requests.Session()
    session.headers.update(headers)
    session.get("https://www.nseindia.com/", timeout=10)
    session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
    return session


def download_nifty200_csv(path: str = NIFTY200_CSV):
    session = _nse_session()
    resp = session.get(NIFTY200_URL, timeout=15)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    log.info(f"Downloaded Nifty200 list -> {path}")


def load_universe() -> list[dict]:
    if not os.path.exists(NIFTY200_CSV):
        log.info(f"{NIFTY200_CSV} not found, attempting auto-download...")
        try:
            download_nifty200_csv(NIFTY200_CSV)
        except Exception as e:
            raise RuntimeError(f"Could not auto-download Nifty200 list ({e}).")
    df = pd.read_csv(NIFTY200_CSV)
    df.columns = [c.strip() for c in df.columns]
    symbols = df["Symbol"].dropna().unique().tolist()
    return [{"symbol": s.strip(), "exchange": "NSE"} for s in symbols]


# --------------------------------------------------------------------------- #
# F&O ELIGIBLE STOCK LIST (auto-download + cache in this folder)
# --------------------------------------------------------------------------- #

def download_fo_stocks_csv(path: str = FO_STOCKS_CSV):
    session = _nse_session()
    resp = session.get(FO_STOCKS_URL, timeout=15)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    log.info(f"Downloaded F&O stock list -> {path}")


def load_fo_symbols() -> set[str]:
    """fo_mktlots.csv columns vary by NSE format version -- be liberal about
    which column holds the symbol; fall back to empty set (== options check
    always says NOT_TRADABLE with a clear reason) rather than crashing."""
    if not os.path.exists(FO_STOCKS_CSV):
        try:
            download_fo_stocks_csv(FO_STOCKS_CSV)
        except Exception as e:
            log.warning(f"F&O list download failed ({e}); options-eligibility checks will report NOT_TRADABLE")
            return set()
    try:
        try:
            df = pd.read_csv(FO_STOCKS_CSV, skipinitialspace=True, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(FO_STOCKS_CSV, skipinitialspace=True, encoding="latin-1")
        df.columns = [c.strip().upper() for c in df.columns]
        sym_col = next((c for c in df.columns if "SYMBOL" in c), None)
        if not sym_col:
            log.warning(f"No SYMBOL column found in {FO_STOCKS_CSV}; columns were {list(df.columns)}")
            return set()
        return set(df[sym_col].dropna().astype(str).str.strip().str.upper())
    except Exception as e:
        log.warning(f"Failed parsing {FO_STOCKS_CSV}: {e}")
        return set()


_token_cache: dict[str, str] = {}
_tsym_cache: dict[str, str] = {}


def resolve_token(symbol: str, exchange: str = "NSE") -> str | None:
    cache_key = f"{exchange}:{symbol}"
    if cache_key in _token_cache:
        return _token_cache[cache_key]
    try:
        res = api.searchscrip(exchange=exchange, searchtext=symbol)
        if res and res.get("stat") == "Ok" and res.get("values"):
            for v in res["values"]:
                if v.get("tsym", "").split("-")[0] == symbol:
                    _token_cache[cache_key] = v["token"]
                    _tsym_cache[cache_key] = v["tsym"]
                    return v["token"]
    except Exception as e:
        log.warning(f"Token resolve failed for {symbol}: {e}")
    return None


def resolve_tsym(symbol: str, exchange: str = "NSE") -> str | None:
    cache_key = f"{exchange}:{symbol}"
    if cache_key not in _tsym_cache:
        resolve_token(symbol, exchange)
    return _tsym_cache.get(cache_key)


# --------------------------------------------------------------------------- #
# DATA FETCH
# --------------------------------------------------------------------------- #

def get_intraday_candles(token: str, exchange: str = "NSE", minutes: int = 1) -> pd.DataFrame:
    now = datetime.now(IST)
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    try:
        data = api.get_time_price_series(
            exchange=exchange, token=token,
            starttime=str(int(start.timestamp())), endtime=str(int(now.timestamp())), interval=minutes,
        )
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data).rename(columns={
            "into": "open", "inth": "high", "intl": "low",
            "intc": "close", "intv": "volume", "time": "time",
        })
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["time"] = pd.to_datetime(df["time"], format="%d-%m-%Y %H:%M:%S")
        return df.sort_values("time").reset_index(drop=True)
    except Exception as e:
        log.warning(f"Intraday fetch failed for token {token}: {e}")
        return pd.DataFrame()


_debug_daily_logged = [0]


def get_daily_candles(tradingsymbol: str, exchange: str = "NSE", days: int = 120) -> pd.DataFrame:
    now = datetime.now(IST)
    start = now - timedelta(days=days * 2)
    try:
        data = api.get_daily_price_series(
            exchange=exchange, tradingsymbol=tradingsymbol,
            startdate=str(int(start.timestamp())), enddate=str(int(now.timestamp())),
        )
        if not data:
            return pd.DataFrame()

        # Shoonya's daily-series endpoint can return either a list of dicts
        # (same shape as intraday) or a list of raw CSV strings
        # "time,into,inth,intl,intc,intv,intoi" depending on account/version.
        # Handle both instead of assuming dicts.
        if isinstance(data[0], str):
            # Each element is a JSON string, e.g.
            # '{"time":"14-AUG-2026", "into":"1179.00", "inth":..., "intv":...}'
            parsed = [json.loads(r) for r in data if r.strip()]
            df = pd.DataFrame(parsed).rename(columns={
                "into": "open", "inth": "high", "intl": "low",
                "intc": "close", "intv": "volume", "time": "time",
            })
        else:
            df = pd.DataFrame(data).rename(columns={
                "into": "open", "inth": "high", "intl": "low",
                "intc": "close", "intv": "volume", "time": "time",
            })

        for c in ["open", "high", "low", "close", "volume"]:
            if c not in df.columns:
                log.warning(f"Daily fetch for {tradingsymbol}: missing column {c!r}, got {list(df.columns)}")
                return pd.DataFrame()
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["time"] = pd.to_datetime(df["time"], format="%d-%b-%Y", errors="coerce")
        if df["time"].isna().all():
            df["time"] = pd.to_datetime(df["time"].astype(str), errors="coerce")  # fallback if format differs
        df = df.dropna(subset=["time"])
        return df.sort_values("time").reset_index(drop=True).tail(days)
    except Exception as e:
        log.warning(f"Daily fetch failed for {tradingsymbol}: {e}")
        return pd.DataFrame()


# Cached once/day per symbol: (avg_daily_volume over 20d). Reused all session
# by the intraday RVOL calc instead of refetching every poll.
_daily_avg_vol_cache: dict[str, float] = {}
_daily_avg_vol_cache_date: datetime.date | None = None


def refresh_daily_avg_volume_cache(universe: list[dict]):
    global _daily_avg_vol_cache, _daily_avg_vol_cache_date
    log.info("Refreshing daily-avg-volume cache for RVOL (once/day, ~1 API call per symbol)...")
    cache = {}
    for stock in universe:
        symbol = stock["symbol"]
        token = resolve_token(symbol, stock["exchange"])
        tsym = resolve_tsym(symbol, stock["exchange"])
        if not token or not tsym:
            continue
        daily_df = get_daily_candles(tsym, stock["exchange"], days=25)
        if daily_df.empty or len(daily_df) < 5:
            continue
        cache[symbol] = float(daily_df["volume"].tail(20).mean())
    _daily_avg_vol_cache = cache
    _daily_avg_vol_cache_date = datetime.now(IST).date()
    log.info(f"Daily-avg-volume cache ready for {len(cache)} symbols")


# --------------------------------------------------------------------------- #
# INDICATORS
# --------------------------------------------------------------------------- #

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def roc(series: pd.Series, period: int = 10) -> pd.Series:
    return (series / series.shift(period) - 1) * 100


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vp = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    return cum_vp / cum_vol


def is_bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False
    prev, cur = df.iloc[-2], df.iloc[-1]
    return (
        prev["close"] < prev["open"]
        and cur["close"] > cur["open"]
        and cur["close"] >= prev["open"]
        and cur["open"] <= prev["close"]
    )


# --------------------------------------------------------------------------- #
# STRATEGY 1: UNIFIED INTRADAY COMPOSITE SCORE (replaces separate ORB/VWAP signals)
# --------------------------------------------------------------------------- #

def score_intraday_setup(symbol: str, df: pd.DataFrame) -> dict | None:
    """0-100 composite: trend stack 25, RVOL 25, day-range proximity 20,
    ORB breakout 15, VWAP bias 15. Returns None if not enough data or score
    too low to act on (bucket == IGNORED)."""
    if df.empty or len(df) < ORB_MINUTES + 1:
        return None

    df = df.copy()
    df["vwap"] = vwap(df)
    df["ema9"] = ema(df["close"], min(9, len(df)))
    df["ema21"] = ema(df["close"], min(21, len(df)))
    df["atr"] = atr(df, period=min(ATR_PERIOD, max(2, len(df) - 1)))
    latest, prev = df.iloc[-1], df.iloc[-2]
    a = latest["atr"] if not pd.isna(latest["atr"]) else (latest["high"] - latest["low"])

    # 1. Trend stack
    trend_pts = 0
    if latest["close"] > latest["ema9"] > latest["ema21"]:
        trend_pts = 25
    elif latest["close"] > latest["ema9"]:
        trend_pts = 12

    # 2. RVOL -- time-of-day-adjusted against cached 20-day avg daily volume
    daily_avg = _daily_avg_vol_cache.get(symbol)
    session_elapsed_frac = min(1.0, max(0.02, (latest["time"] - df["time"].iloc[0]).total_seconds() / (6.25 * 3600)))
    cum_vol_today = df["volume"].sum()
    if daily_avg:
        expected_vol_by_now = daily_avg * session_elapsed_frac
        rvol = cum_vol_today / expected_vol_by_now if expected_vol_by_now > 0 else 0
    else:
        # No cache yet (first run of the day before cache warms) -- crude fallback
        avg_vol_today = df["volume"].iloc[:-1].mean() if len(df) > 1 else latest["volume"]
        rvol = latest["volume"] / avg_vol_today if avg_vol_today else 0
    rvol_pts = 25 if rvol >= RVOL_STRONG else (15 if rvol >= RVOL_MODERATE else 0)

    # 3. Day-range proximity
    day_high, day_low = df["high"].max(), df["low"].min()
    day_range = day_high - day_low
    proximity_up = (latest["close"] - day_low) / day_range if day_range > 0 else 0
    proximity_down = (day_high - latest["close"]) / day_range if day_range > 0 else 0
    prox_pts_up = 20 if proximity_up >= 0.9 else (10 if proximity_up >= 0.75 else 0)
    prox_pts_down = 20 if proximity_down >= 0.9 else (10 if proximity_down >= 0.75 else 0)

    # 4. ORB breakout position
    orb = df[df["time"].dt.time <= (df["time"].iloc[0] + timedelta(minutes=ORB_MINUTES)).time()]
    or_high, or_low = (orb["high"].max(), orb["low"].min()) if not orb.empty else (None, None)
    orb_pts, orb_side = 0, None
    if or_high is not None:
        if latest["close"] > or_high:
            orb_pts, orb_side = 15, "BUY"
        elif latest["close"] < or_low:
            orb_pts, orb_side = 15, "SELL"

    # 5. VWAP institutional bias
    vwap_pts, vwap_side = 0, None
    if not pd.isna(latest["vwap"]) and not pd.isna(prev["vwap"]):
        if prev["close"] <= prev["vwap"] and latest["close"] > latest["vwap"]:
            vwap_pts, vwap_side = 15, "BUY"
        elif prev["close"] >= prev["vwap"] and latest["close"] < latest["vwap"]:
            vwap_pts, vwap_side = 15, "SELL"
        elif latest["close"] > latest["vwap"]:
            vwap_pts, vwap_side = 8, "BUY"
        elif latest["close"] < latest["vwap"]:
            vwap_pts, vwap_side = 8, "SELL"

    sides = [s for s in (orb_side, vwap_side) if s]
    if not sides or len(set(sides)) > 1:
        return None  # conflicting or no directional signal -- skip

    direction = sides[0]
    prox_pts = prox_pts_up if direction == "BUY" else prox_pts_down
    score = trend_pts + rvol_pts + prox_pts + orb_pts + vwap_pts

    if score >= SCORE_STRONG:
        bucket = "STRONG_BUY" if direction == "BUY" else "STRONG_SELL"
    elif score >= SCORE_WATCH:
        bucket = "WATCH_BUY" if direction == "BUY" else "WATCH_SELL"
    else:
        return None

    sl = latest["close"] - ATR_STOP_MULT * a if direction == "BUY" else latest["close"] + ATR_STOP_MULT * a
    tgt = latest["close"] + ATR_TARGET_MULT * a if direction == "BUY" else latest["close"] - ATR_TARGET_MULT * a

    return {
        "symbol": symbol, "signal": bucket, "strategy": "intraday_composite",
        "price": float(latest["close"]), "stop_loss": float(sl), "target": float(tgt),
        "trailing_stop_loss": float(sl),
        "details": {
            "score": score, "direction": direction,
            "trend_pts": trend_pts, "rvol": round(float(rvol), 2), "rvol_pts": rvol_pts,
            "day_range_proximity": round(float(proximity_up if direction == "BUY" else proximity_down), 3),
            "prox_pts": prox_pts, "orb_side": orb_side, "orb_pts": orb_pts,
            "vwap_side": vwap_side, "vwap_pts": vwap_pts, "atr": round(float(a), 2),
        },
    }


# --------------------------------------------------------------------------- #
# STRATEGY 2: BTST (unchanged from original)
# --------------------------------------------------------------------------- #

def check_btst(symbol: str, daily_df: pd.DataFrame) -> list[dict]:
    signals = []
    if daily_df.empty or len(daily_df) < BTST_LOOKBACK_DAYS + 1:
        return signals
    df = daily_df.copy()
    df["atr"] = atr(df)
    hist = df.iloc[:-1].tail(BTST_LOOKBACK_DAYS)
    today = df.iloc[-1]
    resistance = hist["high"].max()
    avg_vol = hist["volume"].mean()
    a = today["atr"] if not pd.isna(today["atr"]) else (today["high"] - today["low"])
    day_range = today["high"] - today["low"]
    close_strength = (today["close"] - today["low"]) / day_range if day_range > 0 else 0
    vol_ok = today["volume"] > avg_vol * INTRADAY_VOLUME_MULT

    if today["close"] > resistance and vol_ok and close_strength >= BTST_MIN_CLOSE_STRENGTH:
        signals.append({
            "symbol": symbol, "signal": "BUY_BTST", "strategy": "btst_resistance_breakout",
            "price": float(today["close"]),
            "stop_loss": float(today["close"] - ATR_STOP_MULT * a),
            "target": float(today["close"] + ATR_TARGET_MULT * a),
            "trailing_stop_loss": float(today["close"] - ATR_STOP_MULT * a),
            "details": {"resistance": float(resistance), "close_strength": round(float(close_strength), 3),
                        "volume": float(today["volume"])},
        })
    if is_bullish_engulfing(df) and vol_ok:
        signals.append({
            "symbol": symbol, "signal": "BUY_BTST", "strategy": "btst_bullish_engulfing",
            "price": float(today["close"]),
            "stop_loss": float(today["low"] - 0.5 * a),
            "target": float(today["close"] + ATR_TARGET_MULT * a),
            "trailing_stop_loss": float(today["low"] - 0.5 * a),
            "details": {"volume": float(today["volume"]), "avg_volume": float(avg_vol)},
        })
    return signals


# --------------------------------------------------------------------------- #
# STRATEGY 3: WEEKLY MOMENTUM (unchanged from original)
# --------------------------------------------------------------------------- #

def check_weekly_momentum(symbol: str, daily_df: pd.DataFrame) -> list[dict]:
    signals = []
    if daily_df.empty or len(daily_df) < WEEKLY_LOOKBACK_DAYS + 5:
        return signals
    df = daily_df.copy()
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50) if len(df) >= 50 else np.nan
    df["ema200"] = ema(df["close"], 200) if len(df) >= 200 else np.nan
    df["rsi14"] = rsi(df["close"], 14)
    df["roc10"] = roc(df["close"], 10)
    df["atr"] = atr(df)
    macd_line, signal_line, hist = macd(df["close"])
    df["macd"], df["macd_signal"], df["macd_hist"] = macd_line, signal_line, hist

    today, prev = df.iloc[-1], df.iloc[-2]
    a = today["atr"] if not pd.isna(today["atr"]) else (today["high"] - today["low"])
    lookback_high = df["close"].iloc[-(WEEKLY_LOOKBACK_DAYS + 1):-1].max()

    trend_ok = today["close"] > today["ema20"]
    if not pd.isna(today["ema50"]):
        trend_ok = trend_ok and today["ema20"] > today["ema50"]
    momentum_ok = WEEKLY_RSI_LOW <= today["rsi14"] <= WEEKLY_RSI_HIGH and today["roc10"] > 0
    breakout_ok = today["close"] > lookback_high

    if trend_ok and momentum_ok and breakout_ok:
        signals.append({
            "symbol": symbol, "signal": "BUY_WEEKLY_MOMENTUM", "strategy": "weekly_momentum_breakout",
            "price": float(today["close"]),
            "stop_loss": float(today["close"] - ATR_STOP_MULT * a),
            "target": float(today["close"] + ATR_TARGET_MULT * a),
            "trailing_stop_loss": float(today["close"] - ATR_STOP_MULT * a),
            "details": {"lookback_high": float(lookback_high), "rsi14": round(float(today["rsi14"]), 2),
                        "roc10": round(float(today["roc10"]), 2)},
        })
    macd_cross_up = prev["macd"] <= prev["macd_signal"] and today["macd"] > today["macd_signal"]
    if macd_cross_up and today["close"] > today["ema20"]:
        signals.append({
            "symbol": symbol, "signal": "BUY_WEEKLY_MOMENTUM", "strategy": "weekly_macd_crossover",
            "price": float(today["close"]),
            "stop_loss": float(today["close"] - ATR_STOP_MULT * a),
            "target": float(today["close"] + ATR_TARGET_MULT * a),
            "trailing_stop_loss": float(today["close"] - ATR_STOP_MULT * a),
            "details": {"macd": float(today["macd"]), "macd_signal": float(today["macd_signal"])},
        })
    if not pd.isna(today["ema200"]) and not pd.isna(prev["ema200"]):
        golden_cross = prev["ema50"] <= prev["ema200"] and today["ema50"] > today["ema200"]
        if golden_cross:
            signals.append({
                "symbol": symbol, "signal": "BUY_WEEKLY_MOMENTUM", "strategy": "weekly_golden_cross",
                "price": float(today["close"]),
                "stop_loss": float(today["close"] - ATR_STOP_MULT * a),
                "target": float(today["close"] + ATR_TARGET_MULT * a),
                "trailing_stop_loss": float(today["close"] - ATR_STOP_MULT * a),
                "details": {"ema50": float(today["ema50"]), "ema200": float(today["ema200"])},
            })
    return signals


# --------------------------------------------------------------------------- #
# STOCK -> OPTIONS HANDOFF
# --------------------------------------------------------------------------- #

def parse_exd(exd_str: str) -> datetime:
    return datetime.strptime(exd_str, "%d-%b-%Y")


def check_stock_options(symbol: str, underlying_signal: str, score: int, exchange: str = "NSE") -> dict:
    """For a STRONG_BUY/STRONG_SELL stock: is it F&O eligible, and if so is
    there a live/liquid near-ATM option to act on? Always returns a row --
    tradable=False rows carry a `reason` so you can see why, instead of the
    stock silently disappearing."""
    base = {
        "underlying_symbol": symbol, "underlying_signal": underlying_signal,
        "underlying_score": score, "tradable": False, "reason": None,
    }

    if symbol.upper() not in _fo_symbols_cache:
        base["reason"] = "not F&O eligible"
        return base

    try:
        fut_search = api.searchscrip(exchange="NFO", searchtext=symbol)
        if not fut_search or "values" not in fut_search:
            base["reason"] = "no NFO contracts found via searchscrip"
            return base

        opts = [v for v in fut_search["values"] if v.get("instname") == "OPTSTK"]
        if not opts:
            base["reason"] = "no OPTSTK contracts in search results"
            return base

        spot_quote = api.get_quotes(exchange=exchange, token=resolve_token(symbol, exchange))
        spot_price = float(spot_quote.get("lp") or 0) if spot_quote else 0
        if spot_price <= 0:
            base["reason"] = "could not fetch live spot price"
            return base

        strikes = sorted({float(v["strprc"]) for v in opts if v.get("strprc")})
        if not strikes:
            base["reason"] = "no strike prices found"
            return base
        atm_strike = min(strikes, key=lambda s: abs(s - spot_price))

        nearest_exd = min(parse_exd(v["exd"]) for v in opts if v.get("exd"))
        nearest_exd_str = nearest_exd.strftime("%d-%b-%Y").upper()

        want_type = "CE" if underlying_signal in ("STRONG_BUY", "WATCH_BUY") else "PE"
        leg = next((v for v in opts
                    if v.get("exd") == nearest_exd_str
                    and float(v.get("strprc", 0) or 0) == atm_strike
                    and v.get("optt") == want_type), None)
        if not leg:
            base["reason"] = f"no {want_type} contract at ATM strike {atm_strike} for {nearest_exd_str}"
            return base

        quote = api.get_quotes(exchange="NFO", token=leg["token"])
        ltp = float(quote.get("lp") or 0) if quote else 0
        if ltp <= 0:
            base["reason"] = f"{leg.get('tsym')} has no live quote (LTP=0) -- illiquid"
            return base

        candles = get_intraday_candles(leg["token"], "NFO")
        vwap_val = ema9 = ema21 = None
        if not candles.empty:
            candles = candles.copy()
            candles["vwap"] = vwap(candles)
            candles["ema9"] = ema(candles["close"], min(9, len(candles)))
            candles["ema21"] = ema(candles["close"], min(21, len(candles)))
            last = candles.iloc[-1]
            vwap_val, ema9, ema21 = float(last["vwap"]), float(last["ema9"]), float(last["ema21"])

        lot_size = int(leg.get("ls", 0) or 0)
        target_price = ltp * 1.15
        trail_sl = ltp * 0.92

        base.update({
            "tradable": True, "reason": "OK",
            "option_symbol": leg.get("tsym"), "token": leg["token"], "strike": atm_strike,
            "option_type": want_type, "expiry": nearest_exd_str, "ltp": ltp,
            "vwap": vwap_val, "ema9": ema9, "ema21": ema21, "lot_size": lot_size,
            "money_required": ltp * lot_size if lot_size else None,
            "target_price": target_price, "trail_sl": trail_sl,
        })
        return base
    except Exception as e:
        base["reason"] = f"error: {e}"
        return base


# --------------------------------------------------------------------------- #
# TRAILING STOP-LOSS (applies uniformly to any OPEN signal, any strategy)
# --------------------------------------------------------------------------- #

def apply_trailing_stop(table: str):
    """PLACEHOLDER thresholds (TSL_BREAKEVEN_ATR / TSL_STEP_ATR) -- your
    strategy doc's real TSL percentages didn't come through when pasted
    (blank formulas). Replace the constants at the top of this file once
    you send the real numbers; the mechanism (breakeven, then step-trail)
    is wired up and ready."""
    open_rows = fetch_open_signals(table)
    for row in open_rows:
        symbol = row["symbol"]
        token = resolve_token(symbol)
        if not token:
            continue
        quote = api.get_quotes(exchange="NSE", token=token)
        ltp = float(quote.get("lp") or 0) if quote else 0
        if ltp <= 0:
            continue

        entry = float(row["price"])
        current_sl = float(row.get("trailing_stop_loss") or row["stop_loss"])
        is_buy = "BUY" in row["signal"]
        a = abs(entry - float(row["stop_loss"])) / ATR_STOP_MULT  # back out the ATR used at entry

        profit = (ltp - entry) if is_buy else (entry - ltp)
        new_sl = current_sl

        if profit >= TSL_BREAKEVEN_ATR * a:
            steps_beyond_breakeven = int((profit - TSL_BREAKEVEN_ATR * a) / (TSL_STEP_ATR * a)) if a > 0 else 0
            trailed = entry + steps_beyond_breakeven * TSL_STEP_ATR * a * (1 if is_buy else -1)
            new_sl = max(current_sl, trailed) if is_buy else min(current_sl, trailed)

        # Check stop hit
        stopped_out = (ltp <= new_sl) if is_buy else (ltp >= new_sl)
        status = "STOPPED_OUT" if stopped_out else "OPEN"

        if new_sl != current_sl or status != row.get("status"):
            upsert_signal(table, {
                "symbol": symbol, "strategy": row["strategy"], "signal": row["signal"],
                "price": entry, "stop_loss": row["stop_loss"], "target": row["target"],
                "trailing_stop_loss": new_sl, "status": status,
                "details": row.get("details"), "trade_date": row["trade_date"],
            })


# --------------------------------------------------------------------------- #
# MARKET HOURS
# --------------------------------------------------------------------------- #

def is_market_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


# --------------------------------------------------------------------------- #
# MAIN SCAN PASSES
# --------------------------------------------------------------------------- #

def run_intraday_scan(universe: list[dict]):
    for stock in universe:
        symbol = stock["symbol"]
        token = resolve_token(symbol, stock["exchange"])
        if not token:
            continue
        df = get_intraday_candles(token, stock["exchange"])
        try:
            sig = score_intraday_setup(symbol, df)
        except Exception as e:
            log.error(f"score_intraday_setup failed for {symbol}: {e}")
            continue
        if not sig:
            continue
        upsert_signal("intraday_signals", sig)

        if sig["signal"] in ("STRONG_BUY", "STRONG_SELL"):
            try:
                opt_row = check_stock_options(symbol, sig["signal"], sig["details"]["score"], stock["exchange"])
                upsert_signal("stock_options_signals", opt_row, conflict_cols="underlying_symbol,trade_date")
            except Exception as e:
                log.error(f"check_stock_options failed for {symbol}: {e}")


def run_eod_scans(universe: list[dict]):
    for stock in universe:
        symbol = stock["symbol"]
        token = resolve_token(symbol, stock["exchange"])
        tsym = resolve_tsym(symbol, stock["exchange"])
        if not token or not tsym:
            continue
        daily_df = get_daily_candles(tsym, stock["exchange"], days=220)
        try:
            for sig in check_btst(symbol, daily_df):
                upsert_signal("btst_signals", sig)
        except Exception as e:
            log.error(f"check_btst failed for {symbol}: {e}")
        try:
            for sig in check_weekly_momentum(symbol, daily_df):
                upsert_signal("weekly_momentum_signals", sig)
        except Exception as e:
            log.error(f"check_weekly_momentum failed for {symbol}: {e}")


def refresh_universe() -> list[dict]:
    try:
        download_nifty200_csv(NIFTY200_CSV)
    except Exception as e:
        log.warning(f"Nifty200 CSV refresh failed, keeping existing list: {e}")
    return load_universe()


_fo_symbols_cache: set[str] = set()


def main():
    global _fo_symbols_cache
    log.info("Starting merged Nifty200 stock+options scanner")
    setup_tables()
    install_cron()
    shoonya_connect()

    universe = refresh_universe()
    log.info(f"Loaded {len(universe)} symbols from {NIFTY200_CSV}")

    _fo_symbols_cache = load_fo_symbols()
    log.info(f"Loaded {len(_fo_symbols_cache)} F&O-eligible symbols from {FO_STOCKS_CSV}")

    refresh_daily_avg_volume_cache(universe)

    eod_done_today = None
    csv_refreshed_on = datetime.now(IST).date()

    while True:
        now = datetime.now(IST)

        if now.date() != csv_refreshed_on:
            universe = refresh_universe()
            _fo_symbols_cache = load_fo_symbols()
            refresh_daily_avg_volume_cache(universe)
            csv_refreshed_on = now.date()
            log.info(f"Daily refresh done: {len(universe)} symbols, {len(_fo_symbols_cache)} F&O-eligible")

        if not is_market_open(now):
            log.info("Market closed. Sleeping 5 min...")
            time_module.sleep(300)
            continue

        try:
            run_intraday_scan(universe)
            apply_trailing_stop("intraday_signals")

            if now.time() >= EOD_SCAN_TIME and eod_done_today != now.date():
                log.info("Running BTST + weekly momentum EOD scan")
                run_eod_scans(universe)
                eod_done_today = now.date()
        except Exception:
            log.error("Error in scan loop:\n" + traceback.format_exc())

        time_module.sleep(INTRADAY_POLL_SECONDS)


if __name__ == "__main__":
    if "--refresh-csv" in sys.argv:
        download_nifty200_csv(NIFTY200_CSV)
    elif "--setup" in sys.argv:
        setup_tables()
        install_cron()
    else:
        main()
