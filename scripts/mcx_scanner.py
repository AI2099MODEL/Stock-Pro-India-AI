#!/usr/bin/env python3
"""
mcx_scanner.py

Live MCX options breakout scanner. Signals are generated off each mini
contract's own futures price series (used only as data, never traded), then
executed as a long ATM option (CE on a bullish breakout, PE on a bearish
breakdown). Target/stop/trailing all move with the option's own premium.
Run: python3 mcx_scanner.py

CHANGELOG (fixes applied on review):
  - ORB breakout no longer blocked behind the 1-hour RVOL warm-up window;
    it now evaluates as soon as the opening range itself is complete.
  - compute_daily_bias() now detects bearish confluence symmetrically with
    bullish confluence (was bullish-only before, with BEARISH as a weak
    fallback). Direction is now the side with the higher score, gated by a
    matching trend confirmation.
  - Added a per-symbol exposure cap: only one open option position per
    underlying at a time, regardless of which strategy/direction fired it.
  - OPEN_POSITIONS is now rehydrated from Supabase on startup, so a process
    restart mid-session doesn't lose entry price / trailing-stop state and
    silently re-fire a strategy at a new cost basis.
"""

from __future__ import annotations

import os
import sys
import re
import time as time_module
import logging
import subprocess
import traceback
import fcntl
from datetime import datetime, time as dtime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import json
import yaml
from NorenRestApiPy.NorenApi import NorenApi
import pandas as pd
import numpy as np
import requests

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(23, 45)
ORB_MINUTES = 15
INTRADAY_POLL_SECONDS = 60

MCX_CONTRACTS = [
    "CRUDEOILM", "GOLDM", "SILVERM",
]

CANDLE_INTERVAL_MINUTES = 5  # 5-min bars for signal generation -- 1-min MCX volume
                              # is too thin for RVOL/streak filters to fire reliably;
                              # 5-min is the standard ORB interval in the published
                              # literature (Zarattini, Barbon & Aziz 2024).
INTRADAY_VOLUME_MULT = 1.5
INTRADAY_RVOL_LOOKBACK = 12  # 12 x 5-min bars = trailing 1 hour, not an arbitrary span
INTRADAY_RVOL_MULT = 2.0
INTRADAY_MIN_PRICE_CHANGE_PCT = 0.15
INTRADAY_MOMENTUM_CANDLES = 2  # 2 consecutive 5-min bars (10 min of continuation) --
                                # 3 consecutive 5-min bars proved too strict in practice
INTRADAY_MAX_RANGE_PCT = 1.5   # intra-candle high/low range filter (NOT bid/ask spread --
                                # that's checked separately on the option leg via bp1/sp1)
DEPTH_IMBALANCE_MULT = 1.3
POSITIONAL_LOOKBACK_DAYS = 20
POSITIONAL_MIN_CLOSE_STRENGTH = 0.7
WEEKLY_LOOKBACK_DAYS = 20
WEEKLY_RSI_LOW = 55
WEEKLY_RSI_HIGH = 70
WEEKLY_RSI_BEAR_LOW = 30       # symmetric bearish RSI band (mirrors 55-70 bullish band)
WEEKLY_RSI_BEAR_HIGH = 45
ATR_PERIOD = 14
ATR_STOP_MULT = 1.5
ATR_TARGET_MULT = 3.0
BIAS_SCORE_MIN = 2             # minimum confluence score to declare a direction
REQUIRE_TREND_CONFIRMATION = True  # score alone isn't enough; matching trend leg must also agree

OPTION_TARGET_PCT = 0.40
OPTION_SL_PCT = 0.20
OPTION_TRAIL_TRIGGER_PCT = 0.20
OPTION_TRAIL_LOCK_PCT = 0.10
OPTION_CHAIN_COUNT = 1

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gshiddtlkiihwnxvxzle.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F")

SUPABASE_REST_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

LOG_LEVEL = os.environ.get("MCX_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("mcx_scanner")

LOCK_PATH = "/tmp/mcx_scanner.lock"


def acquire_singleton_lock():
    lock_file = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("Another instance is already running (lock held). Exiting.")
        sys.exit(1)
    return lock_file


def upsert_signal(table: str, row: dict):
    now_iso = datetime.now(IST).isoformat()
    row.setdefault("trade_date", datetime.now(IST).date().isoformat())
    row["signal_time"] = now_iso
    row["updated_at"] = now_iso
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict=symbol,strategy,trade_date"
    try:
        resp = requests.post(url, headers=SUPABASE_REST_HEADERS, json=row, timeout=15)
        resp.raise_for_status()
        log.info(f"[{table}] {row['symbol']} -> {row['strategy']} ({row['signal']})")
    except Exception as e:
        log.error(f"Supabase upsert failed for {table}/{row.get('symbol')}: {e}")


def fetch_open_positions_from_supabase(table: str, trade_date: str) -> list[dict]:
    """Rehydrates OPEN_POSITIONS on startup so a process restart mid-session
    doesn't lose entry price / trailing-stop state and silently re-fire a
    strategy at a new cost basis (see CHANGELOG)."""
    url = (
        f"{SUPABASE_URL}/rest/v1/{table}"
        f"?trade_date=eq.{trade_date}&status=eq.OPEN&select=*"
    )
    try:
        resp = requests.get(url, headers=SUPABASE_REST_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json() or []
    except Exception as e:
        log.warning(f"Supabase fetch of open positions failed for {table}: {e}")
        return []


CRON_MARKER = "# mcx_scanner_watchdog"


def install_cron():
    """Manual use only (python3 mcx_scanner.py --setup). Not called automatically
    from main() -- add the cron line yourself when ready."""
    script_path = os.path.abspath(__file__)
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        log.warning("crontab not available -- skipping cron install")
        return
    if CRON_MARKER in existing:
        return
    line = (
        f"*/5 * * * * pgrep -f {script_path} > /dev/null || "
        f"/usr/bin/python3 {script_path} >> /tmp/mcx_scanner.log 2>&1 & {CRON_MARKER}\n"
    )
    new_crontab = existing + ("\n" if existing and not existing.endswith("\n") else "") + line
    subprocess.run(["crontab", "-"], input=new_crontab, text=True)
    log.info("Installed cron watchdog (checks every 5 min, restarts scanner if down)")


# --------------------------------------------------------------------------- #
# SHOONYA CONNECTION -- unchanged, live, do not touch
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

CONTRACT_CACHE: dict = {}
CONTRACT_CACHE_DATE = None
PREV_OI_CACHE: dict = {}
PREV_OI_CACHE_DATE = None
FUTURE_TSYM_RE_CACHE: dict = {}


def _future_tsym_pattern(symbol: str):
    if symbol not in FUTURE_TSYM_RE_CACHE:
        FUTURE_TSYM_RE_CACHE[symbol] = re.compile(rf"^{re.escape(symbol.upper())}\d{{1,2}}[A-Z]{{3}}\d{{2}}$")
    return FUTURE_TSYM_RE_CACHE[symbol]


def resolve_mcx_contract(symbol: str) -> dict:
    """Resolves the FUTURES line only -- used purely as the price/volume/OI data
    source for breakout detection, never traded directly. Excludes options and
    any other tsym variant via strict regex (SYMBOL+DDMMMYY, nothing after)."""
    ret = SHOONYA.searchscrip(exchange="MCX", searchtext=symbol)
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"searchscrip failed for {symbol}: {ret}")
    pattern = _future_tsym_pattern(symbol)
    candidates = [v for v in ret["values"] if pattern.match(v["tsym"].upper())]
    if not candidates:
        raise RuntimeError(f"no MCX futures line found for {symbol}")
    today = datetime.now(IST).date()
    best, best_exd = None, None
    for c in candidates:
        info = SHOONYA.get_security_info(exchange="MCX", token=c["token"])
        exd_str = info.get("exd") if info else None
        if not exd_str:
            continue
        exd = datetime.strptime(exd_str, "%d-%b-%Y").date()
        if exd < today:
            continue
        if best_exd is None or exd < best_exd:
            best_exd, best = exd, {"token": c["token"], "tsym": c["tsym"], "exch": "MCX", "expiry": exd}
    if best is None:
        raise RuntimeError(f"no unexpired MCX futures contract found for {symbol}")
    return best


def get_contract(symbol: str) -> dict:
    global CONTRACT_CACHE_DATE
    today = datetime.now(IST).date()
    if CONTRACT_CACHE_DATE != today:
        CONTRACT_CACHE.clear()
        CONTRACT_CACHE_DATE = today
    if symbol not in CONTRACT_CACHE:
        CONTRACT_CACHE[symbol] = resolve_mcx_contract(symbol)
    return CONTRACT_CACHE[symbol]


def _parse_tp_series(raw: list) -> pd.DataFrame:
    rows = []
    for r in raw:
        rows.append({
            "time": datetime.strptime(r["time"], "%d-%m-%Y %H:%M:%S"),  # naive IST wall-clock -- avoids pandas/zoneinfo tz bug
            "open": float(r["into"]), "high": float(r["inth"]),
            "low": float(r["intl"]), "close": float(r["intc"]),
            "volume": float(r["intv"]), "oi": float(r.get("oi", 0) or 0),
        })
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


def get_intraday_candles(symbol: str, minutes: int = CANDLE_INTERVAL_MINUTES) -> pd.DataFrame:
    c = get_contract(symbol)
    day_start = datetime.combine(datetime.now(IST).date(), MARKET_OPEN, tzinfo=IST)
    ret = SHOONYA.get_time_price_series(
        exchange=c["exch"], token=c["token"],
        starttime=str(int(day_start.timestamp())),
        endtime=str(int(datetime.now(IST).timestamp())),
        interval=str(minutes),
    )
    if not ret:
        return pd.DataFrame()
    return _parse_tp_series(ret)


def get_daily_candles(symbol: str, days: int = 220) -> pd.DataFrame:
    c = get_contract(symbol)
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
        r = json.loads(raw) if isinstance(raw, str) else raw
        rows.append({
            "time": datetime.strptime(r["time"], "%d-%b-%Y"),
            "open": float(r["into"]), "high": float(r["inth"]),
            "low": float(r["intl"]), "close": float(r["intc"]),
            "volume": float(r["intv"]),
        })
    return pd.DataFrame(rows).sort_values("time").tail(days).reset_index(drop=True)


def get_ltp(symbol: str) -> float:
    c = get_contract(symbol)
    ret = SHOONYA.get_quotes(exchange=c["exch"], token=c["token"])
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"get_quotes failed for {symbol}: {ret}")
    return float(ret["lp"])


def get_prev_oi(symbol: str):
    global PREV_OI_CACHE_DATE
    today = datetime.now(IST).date()
    if PREV_OI_CACHE_DATE != today:
        PREV_OI_CACHE.clear()
        PREV_OI_CACHE_DATE = today
    if symbol in PREV_OI_CACHE:
        return PREV_OI_CACHE[symbol]
    c = get_contract(symbol)
    end = datetime.combine(today, MARKET_OPEN, tzinfo=IST)
    start = end - timedelta(days=5)
    ret = SHOONYA.get_time_price_series(
        exchange=c["exch"], token=c["token"],
        starttime=str(int(start.timestamp())), endtime=str(int(end.timestamp())),
        interval="60",
    )
    if not ret:
        return None
    df = _parse_tp_series(ret)
    df = df[df["oi"] > 0]
    if df.empty:
        return None
    val = float(df.iloc[-1]["oi"])
    PREV_OI_CACHE[symbol] = val
    return val


def get_market_snapshot(symbol: str) -> dict:
    c = get_contract(symbol)
    q = SHOONYA.get_quotes(exchange=c["exch"], token=c["token"])
    if not q or q.get("stat") != "Ok":
        raise RuntimeError(f"get_quotes failed for {symbol}: {q}")
    bid_qty = sum(float(q.get(f"bq{i}", 0) or 0) for i in range(1, 6))
    ask_qty = sum(float(q.get(f"sq{i}", 0) or 0) for i in range(1, 6))
    candles = get_intraday_candles(symbol, minutes=1)
    current_oi = float(candles.iloc[-1]["oi"]) if not candles.empty else None
    return {
        "ltp": float(q["lp"]), "volume": float(q.get("v", 0) or 0),
        "oi": current_oi, "prev_oi": get_prev_oi(symbol),
        "bid_qty": bid_qty, "ask_qty": ask_qty,
    }


# --------------------------------------------------------------------------- #
# OPTIONS -- resolve ATM contract for a breakout, quote its own premium
# --------------------------------------------------------------------------- #

OPTION_TSYM_FULL_RE = re.compile(r"^([A-Z]+)(\d{1,2}[A-Z]{3}\d{2})([CP])([0-9.]+)$")
MIN_DAYS_TO_OPT_EXPIRY = 3       # warn if using an option series expiring this soon
OPTION_MAX_SPREAD_PCT = 8.0      # reject strikes wider than this bid/ask spread


def _discover_option_expiry(symbol: str, opt_type: str) -> str:
    """One broad searchscrip call just to learn the option series' expiry
    string (e.g. '28AUG26'), which is often different from the futures
    contract's own expiry on MCX. Truncation from the ~25-result cap doesn't
    matter here -- we only need ONE matching option tsym to read the expiry."""
    ret = SHOONYA.searchscrip(exchange="MCX", searchtext=symbol)
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"searchscrip failed for {symbol}: {ret}")
    for v in ret["values"]:
        m = OPTION_TSYM_FULL_RE.match(v["tsym"].upper())
        if m and m.group(1) == symbol.upper() and m.group(3) == opt_type:
            return m.group(2)
    raise RuntimeError(f"no {opt_type} option series visible for {symbol} in initial scan")


def _strikes_near(symbol: str, expiry_str: str, opt_type: str, spot: float) -> list:
    """Narrows searchscrip by spot's leading digits so strikes near spot
    aren't pushed out by the ~25-result cap -- regardless of spot's
    magnitude (works for a 175-priced underlying same as a 250000-priced
    one). Starts unprefixed; if that call hits the cap (a sign of
    truncation, not a true empty/small result), lengthens the prefix by one
    digit and also queries the adjacent prefixes on each side to avoid
    missing strikes that sit right at a digit-block boundary."""
    root = f"{symbol}{expiry_str}{opt_type}"
    spot_digits = str(int(spot))

    for prefix_len in range(0, len(spot_digits) + 1):
        prefix = spot_digits[:prefix_len]
        probe_prefixes = {prefix}
        if prefix:
            p_int = int(prefix)
            probe_prefixes.add(str(max(p_int - 1, 0)))
            probe_prefixes.add(str(p_int + 1))

        seen = {}
        hit_cap = False
        for p in probe_prefixes:
            ret = SHOONYA.searchscrip(exchange="MCX", searchtext=root + p)
            if not ret or ret.get("stat") != "Ok":
                continue
            if len(ret["values"]) >= 25:
                hit_cap = True
            for v in ret["values"]:
                m = OPTION_TSYM_FULL_RE.match(v["tsym"].upper())
                if not m or m.group(1) != symbol.upper() or m.group(2) != expiry_str or m.group(3) != opt_type:
                    continue
                seen[v["tsym"]] = {
                    "token": v["token"], "tsym": v["tsym"], "exch": "MCX",
                    "strike": float(m.group(4)), "opt_type": opt_type,
                }

        if not hit_cap or prefix_len == len(spot_digits):
            if hit_cap and prefix_len == len(spot_digits):
                log.warning(
                    f"{symbol}: strike search hit the ~25-result cap even at full "
                    f"spot-digit precision -- candidate list may be truncated"
                )
            return list(seen.values())

    return []


def resolve_option_contract(symbol: str, spot: float, opt_type: str) -> dict:
    """Discovers the option series independently of the futures contract --
    MCX options and futures on the same commodity often expire on different
    dates, so we can't reuse the futures tsym's expiry. searchscrip caps
    results at ~25, so strikes are found by narrowing the query to spot's
    neighborhood rather than enumerating the whole chain. Returns the
    closest strike with a real, liquid two-sided quote."""
    expiry_str = _discover_option_expiry(symbol, opt_type)
    expiry = datetime.strptime(expiry_str, "%d%b%y").date()
    today = datetime.now(IST).date()
    if expiry < today:
        raise RuntimeError(f"discovered option expiry {expiry} for {symbol} is already past")
    if expiry < today + timedelta(days=MIN_DAYS_TO_OPT_EXPIRY):
        log.warning(f"{symbol}: option expiry {expiry} is inside {MIN_DAYS_TO_OPT_EXPIRY}d")

    candidates = _strikes_near(symbol, expiry_str, opt_type, spot)
    if not candidates:
        raise RuntimeError(f"no {opt_type} strikes found near {spot} for {symbol} (expiry {expiry})")

    candidates.sort(key=lambda c: abs(c["strike"] - spot))
    for cand in candidates:
        try:
            q = SHOONYA.get_quotes(exchange="MCX", token=cand["token"])
        except Exception as e:
            log.warning(f"get_quotes failed for {cand['tsym']}: {e}")
            continue
        if not q or q.get("stat") != "Ok":
            continue
        lp = float(q.get("lp", 0) or 0)
        bp1 = float(q.get("bp1", 0) or 0)
        sp1 = float(q.get("sp1", 0) or 0)
        if lp <= 0 or bp1 <= 0 or sp1 <= 0:
            continue  # unquoted / dead strike
        spread_pct = (sp1 - bp1) / lp * 100
        if spread_pct > OPTION_MAX_SPREAD_PCT:
            continue  # quoted but not tradeable at a sane price
        cand["premium"] = lp
        cand["expiry"] = expiry
        return cand

    raise RuntimeError(f"no liquid {opt_type} strike found near {spot} for {symbol} (expiry {expiry})")


def build_option_signal(symbol: str, contract: dict, direction: str, strategy: str,
                         spot: float, extra_details: dict):
    opt_type = "C" if direction == "BUY" else "P"
    try:
        opt = resolve_option_contract(symbol, spot, opt_type)
        premium = opt["premium"]
    except Exception as e:
        log.warning(f"Option resolution failed for {symbol} {direction}: {e}")
        return None
    return {
        "symbol": symbol, "signal": direction, "strategy": strategy,
        "price": float(premium),
        "stop_loss": float(premium * (1 - OPTION_SL_PCT)),
        "target": float(premium * (1 + OPTION_TARGET_PCT)),
        "status": "OPEN",
        "details": {
            **extra_details, "underlying_price": float(spot),
            "option_tsym": opt["tsym"], "option_token": opt["token"],
            "option_strike": opt["strike"], "option_type": opt_type,
        },
    }


# --------------------------------------------------------------------------- #
# LIVE TRACKING -- once a signal fires, keep updating its option premium /
# trailing stop in Supabase (same row, via symbol+strategy+trade_date unique
# key) until target or stop is hit.
# --------------------------------------------------------------------------- #

OPEN_POSITIONS: dict = {}


def symbol_has_open_position(symbol: str) -> bool:
    """Per-symbol exposure cap: only one open option position per underlying
    at a time, regardless of which strategy/direction fired it (see
    CHANGELOG -- previously ORB and VWAP could both fire same-direction
    signals on the same symbol same day, doubling exposure)."""
    return any(pos["symbol"] == symbol for pos in OPEN_POSITIONS.values())


def track_signal(table: str, sig: dict):
    # Every signal is a long option purchase (buy CE on a BUY breakout, buy PE
    # on a SELL breakdown) -- there is no short-option leg, so tracking only
    # ever trails upward on premium regardless of underlying direction.
    trade_date = sig.get("trade_date", datetime.now(IST).date().isoformat())
    key = (table, sig["symbol"], sig["strategy"], trade_date)
    if key in OPEN_POSITIONS:
        return
    entry = sig["price"]
    OPEN_POSITIONS[key] = {
        "table": table, "symbol": sig["symbol"], "strategy": sig["strategy"],
        "trade_date": trade_date, "entry": entry,
        "option_token": sig["details"]["option_token"],
        "extreme": entry, "target": sig["target"], "stop_loss": sig["stop_loss"],
        "trailing_stop_loss": sig["stop_loss"],
    }


def rehydrate_open_positions(table: str, trade_date: str):
    """Loads any still-OPEN rows for today from Supabase into OPEN_POSITIONS
    on startup. Without this, a process restart mid-session forgets entry
    price / trailing-stop state and the scan loop will re-fire the same
    strategy at a fresh (different) premium, overwriting the original
    signal row under the same symbol+strategy+trade_date key."""
    rows = fetch_open_positions_from_supabase(table, trade_date)
    for row in rows:
        details = row.get("details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {}
        option_token = details.get("option_token")
        if not option_token:
            log.warning(f"Skipping rehydration of {row.get('symbol')}: no option_token in details")
            continue
        key = (table, row["symbol"], row["strategy"], trade_date)
        OPEN_POSITIONS[key] = {
            "table": table, "symbol": row["symbol"], "strategy": row["strategy"],
            "trade_date": trade_date, "entry": float(row["price"]),
            "option_token": option_token,
            "extreme": float(row.get("trailing_stop_loss") and max(row["price"], row["price"])) or float(row["price"]),
            "target": float(row["target"]), "stop_loss": float(row["stop_loss"]),
            "trailing_stop_loss": float(row.get("trailing_stop_loss", row["stop_loss"])),
        }
    if OPEN_POSITIONS:
        log.info(f"Rehydrated {len(OPEN_POSITIONS)} open position(s) from Supabase for {trade_date}")


def get_option_ltp(contract: dict) -> float:
    """LTP for an already-resolved option contract (exch/token) -- used to
    track an open position's own premium. Distinct from get_ltp(), which
    resolves a *symbol* to its futures contract instead."""
    ret = SHOONYA.get_quotes(exchange=contract["exch"], token=contract["token"])
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"get_quotes failed for option token {contract['token']}: {ret}")
    return float(ret["lp"])


def update_open_signals():
    for key, pos in list(OPEN_POSITIONS.items()):
        try:
            ltp = get_option_ltp({"exch": "MCX", "token": pos["option_token"]})
        except Exception as e:
            log.warning(f"Option LTP fetch failed for {pos['symbol']}: {e}")
            continue

        status = "OPEN"
        pos["extreme"] = max(pos["extreme"], ltp)
        if pos["extreme"] >= pos["entry"] * (1 + OPTION_TRAIL_TRIGGER_PCT):
            pos["trailing_stop_loss"] = max(pos["trailing_stop_loss"], pos["extreme"] * (1 - OPTION_TRAIL_LOCK_PCT))
        if ltp <= pos["trailing_stop_loss"]:
            status = "SL_HIT"
        elif ltp >= pos["target"]:
            status = "TARGET_HIT"

        upsert_signal(pos["table"], {
            "symbol": pos["symbol"], "strategy": pos["strategy"], "signal": "BUY",
            "price": float(ltp), "stop_loss": pos["stop_loss"], "target": pos["target"],
            "trailing_stop_loss": float(pos["trailing_stop_loss"]),
            "status": status, "trade_date": pos["trade_date"],
        })

        if status != "OPEN":
            del OPEN_POSITIONS[key]


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


def is_bearish_engulfing(df: pd.DataFrame) -> bool:
    """Symmetric counterpart to is_bullish_engulfing -- previously missing,
    which was one reason compute_daily_bias() couldn't detect bearish
    confluence (see CHANGELOG)."""
    if len(df) < 2:
        return False
    prev, cur = df.iloc[-2], df.iloc[-1]
    return (
        prev["close"] > prev["open"]
        and cur["close"] < cur["open"]
        and cur["open"] >= prev["close"]
        and cur["close"] <= prev["open"]
    )


def classify_oi_signal(price_up: bool, oi_change_pct: float) -> str:
    if oi_change_pct > 0:
        return "LONG_BUILDUP" if price_up else "SHORT_BUILDUP"
    if oi_change_pct < 0:
        return "SHORT_COVERING" if price_up else "LONG_UNWINDING"
    return "FLAT"


# --------------------------------------------------------------------------- #
# STRATEGY: INTRADAY (ORB breakout + VWAP reclaim) -- generates the direction,
# then trades it as an ATM option instead of the underlying.
# --------------------------------------------------------------------------- #

def check_intraday(symbol: str, df: pd.DataFrame, contract: dict, bias: dict | None = None,
                    snapshot: dict | None = None) -> list[dict]:
    signals = []
    if df.empty:
        log.debug(f"{symbol} | no candle data returned yet")
        return signals

    orb_candles = max(1, ORB_MINUTES // CANDLE_INTERVAL_MINUTES)
    # ORB breakout only needs the opening range itself to be complete, plus
    # one more candle to break it -- it must NOT be gated behind the RVOL
    # lookback (12 candles = ~1hr), which used to delay every signal,
    # including ORB, by an hour and turn "breakout" into "still extended"
    # (see CHANGELOG). RVOL is evaluated separately once enough data exists.
    orb_min_needed = orb_candles + 1
    if len(df) < orb_min_needed:
        log.debug(f"{symbol} | only {len(df)}/{orb_min_needed} candles -- ORB window not complete yet")
        return signals

    bias = bias or {}
    htf_direction = bias.get("direction", "NEUTRAL")

    snapshot = snapshot or {}
    oi, prev_oi = snapshot.get("oi"), snapshot.get("prev_oi")
    oi_change_pct = (oi - prev_oi) / prev_oi * 100 if oi is not None and prev_oi else None

    df = df.copy()
    df["vwap"] = vwap(df)
    df["atr"] = atr(df, period=min(ATR_PERIOD, max(2, len(df) - 1)))

    latest = df.iloc[-1]
    prev_close = df["close"].iloc[-2]
    a = latest["atr"] if not pd.isna(latest["atr"]) else (latest["high"] - latest["low"])

    avg_vol = df["volume"].iloc[:-1].mean() if len(df) > 1 else latest["volume"]
    session_vol_ok = latest["volume"] > avg_vol * INTRADAY_VOLUME_MULT

    # RVOL needs its own lookback window of history. Before that much history
    # exists (i.e. within the first ~hour of the session), fall back to the
    # session-average volume check alone rather than blocking every signal.
    if len(df) - 1 >= INTRADAY_RVOL_LOOKBACK:
        rolling_avg_vol = df["volume"].iloc[:-1].tail(INTRADAY_RVOL_LOOKBACK).mean()
        rvol = latest["volume"] / rolling_avg_vol if rolling_avg_vol > 0 else 0
        rvol_ok = rvol >= INTRADAY_RVOL_MULT
    else:
        rvol = None
        rvol_ok = session_vol_ok  # fallback filter while warming up

    price_change_pct = (latest["close"] - prev_close) / prev_close * 100 if prev_close else 0
    move_ok = abs(price_change_pct) >= INTRADAY_MIN_PRICE_CHANGE_PCT
    price_up = price_change_pct > 0

    range_pct = (latest["high"] - latest["low"]) / latest["close"] * 100 if latest["close"] else 0
    range_ok = range_pct <= INTRADAY_MAX_RANGE_PCT

    recent_closes = df["close"].tail(INTRADAY_MOMENTUM_CANDLES + 1).tolist()
    up_streak = all(recent_closes[i] < recent_closes[i + 1] for i in range(len(recent_closes) - 1))
    down_streak = all(recent_closes[i] > recent_closes[i + 1] for i in range(len(recent_closes) - 1))

    oi_signal = classify_oi_signal(price_up, oi_change_pct) if oi_change_pct is not None else None
    oi_buy_ok = oi_signal != "SHORT_COVERING"
    oi_sell_ok = oi_signal != "LONG_UNWINDING"

    bid_qty, ask_qty = snapshot.get("bid_qty"), snapshot.get("ask_qty")
    if bid_qty and ask_qty:
        depth_buy_ok = bid_qty >= ask_qty * DEPTH_IMBALANCE_MULT
        depth_sell_ok = ask_qty >= bid_qty * DEPTH_IMBALANCE_MULT
    else:
        depth_buy_ok = depth_sell_ok = True

    vol_ok = session_vol_ok and rvol_ok

    log.debug(
        f"{symbol} | close={latest['close']:.2f} chg={price_change_pct:+.3f}% "
        f"vol_ok={session_vol_ok}(v={latest['volume']:.0f} avg={avg_vol:.0f}) "
        f"rvol_ok={rvol_ok}(rvol={rvol}) move_ok={move_ok} range_ok={range_ok}({range_pct:.2f}%) "
        f"up_streak={up_streak} down_streak={down_streak} htf={htf_direction} "
        f"oi_signal={oi_signal} depth_buy_ok={depth_buy_ok} depth_sell_ok={depth_sell_ok}"
    )

    common_details = {
        "volume": float(latest["volume"]), "avg_volume": float(avg_vol),
        "rvol": round(float(rvol), 2) if rvol is not None else None,
        "price_change_pct": round(float(price_change_pct), 3),
        "range_pct": round(float(range_pct), 3), "atr": float(a),
        "htf_bias": htf_direction, "htf_score": bias.get("score", 0),
        "oi_signal": oi_signal, "oi_change_pct": round(oi_change_pct, 2) if oi_change_pct is not None else None,
    }

    orb_cutoff = (df["time"].iloc[0] + timedelta(minutes=ORB_MINUTES)).time()
    orb = df[df["time"].apply(lambda t: t.time()) <= orb_cutoff]
    if not orb.empty:
        or_high, or_low = orb["high"].max(), orb["low"].min()
        if (latest["close"] > or_high and vol_ok and move_ok and range_ok and up_streak
                and htf_direction != "BEARISH" and oi_buy_ok and depth_buy_ok):
            sig = build_option_signal(symbol, contract, "BUY", "intraday_orb_breakout",
                                       float(latest["close"]),
                                       {**common_details, "or_high": float(or_high), "or_low": float(or_low)})
            if sig:
                signals.append(sig)
        elif (latest["close"] < or_low and vol_ok and move_ok and range_ok and down_streak
                and htf_direction != "BULLISH" and oi_sell_ok and depth_sell_ok):
            sig = build_option_signal(symbol, contract, "SELL", "intraday_orb_breakdown",
                                       float(latest["close"]),
                                       {**common_details, "or_high": float(or_high), "or_low": float(or_low)})
            if sig:
                signals.append(sig)

    if len(df) > orb_candles and not pd.isna(latest["vwap"]):
        prev = df.iloc[-2]
        crossed_up = prev["close"] <= prev["vwap"] and latest["close"] > latest["vwap"]
        crossed_down = prev["close"] >= prev["vwap"] and latest["close"] < latest["vwap"]
        if (crossed_up and vol_ok and move_ok and range_ok
                and htf_direction != "BEARISH" and oi_buy_ok and depth_buy_ok):
            sig = build_option_signal(symbol, contract, "BUY", "intraday_vwap_reclaim",
                                       float(latest["close"]),
                                       {**common_details, "vwap": float(latest["vwap"])})
            if sig:
                signals.append(sig)
        elif (crossed_down and vol_ok and move_ok and range_ok
                and htf_direction != "BULLISH" and oi_sell_ok and depth_sell_ok):
            sig = build_option_signal(symbol, contract, "SELL", "intraday_vwap_breakdown",
                                       float(latest["close"]),
                                       {**common_details, "vwap": float(latest["vwap"])})
            if sig:
                signals.append(sig)

    return signals


# --------------------------------------------------------------------------- #
# HIGHER-TIMEFRAME BIAS -- positional + weekly momentum logic, used once a day
# to confirm/reject intraday breakouts so intraday isn't trading against the
# daily/weekly trend. Bullish and bearish confluence are scored symmetrically.
# --------------------------------------------------------------------------- #

def compute_daily_bias(daily_df: pd.DataFrame) -> dict:
    bias = {
        "positional_breakout": False, "positional_breakdown": False,
        "bullish_engulfing": False, "bearish_engulfing": False,
        "weekly_trend_ok": False, "weekly_downtrend_ok": False,
        "weekly_momentum_ok": False, "weekly_bear_momentum_ok": False,
        "macd_cross_up": False, "macd_cross_down": False,
        "golden_cross": False, "death_cross": False,
        "direction": "NEUTRAL", "score": 0,
        "bull_score": 0, "bear_score": 0,
    }
    if daily_df.empty or len(daily_df) < WEEKLY_LOOKBACK_DAYS + 5:
        return bias

    df = daily_df.copy()
    df["atr"] = atr(df)
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50) if len(df) >= 50 else np.nan
    df["ema200"] = ema(df["close"], 200) if len(df) >= 200 else np.nan
    df["rsi14"] = rsi(df["close"], 14)
    df["roc10"] = roc(df["close"], 10)
    macd_line, signal_line, _ = macd(df["close"])
    df["macd"], df["macd_signal"] = macd_line, signal_line

    today, prev = df.iloc[-1], df.iloc[-2]
    hist = df.iloc[:-1].tail(POSITIONAL_LOOKBACK_DAYS)
    resistance = hist["high"].max()
    support = hist["low"].min()
    avg_vol = hist["volume"].mean()
    day_range = today["high"] - today["low"]
    close_strength = (today["close"] - today["low"]) / day_range if day_range > 0 else 0
    close_weakness = (today["high"] - today["close"]) / day_range if day_range > 0 else 0
    vol_ok = today["volume"] > avg_vol * INTRADAY_VOLUME_MULT

    # --- Bullish confluence ---
    bias["positional_breakout"] = bool(
        today["close"] > resistance and vol_ok and close_strength >= POSITIONAL_MIN_CLOSE_STRENGTH
    )
    bias["bullish_engulfing"] = bool(is_bullish_engulfing(df) and vol_ok)

    lookback_high = df["high"].iloc[-(WEEKLY_LOOKBACK_DAYS + 1):-1].max()
    trend_ok = today["close"] > today["ema20"]
    if not pd.isna(today["ema50"]):
        trend_ok = trend_ok and today["ema20"] > today["ema50"]
    momentum_ok = WEEKLY_RSI_LOW <= today["rsi14"] <= WEEKLY_RSI_HIGH and today["roc10"] > 0
    bias["weekly_trend_ok"] = bool(trend_ok)
    bias["weekly_momentum_ok"] = bool(momentum_ok and today["close"] > lookback_high)
    bias["macd_cross_up"] = bool(prev["macd"] <= prev["macd_signal"] and today["macd"] > today["macd_signal"])
    if not pd.isna(today["ema200"]) and not pd.isna(prev["ema200"]) and not pd.isna(prev["ema50"]):
        bias["golden_cross"] = bool(prev["ema50"] <= prev["ema200"] and today["ema50"] > today["ema200"])

    # --- Bearish confluence (symmetric counterparts) ---
    bias["positional_breakdown"] = bool(
        today["close"] < support and vol_ok and close_weakness >= POSITIONAL_MIN_CLOSE_STRENGTH
    )
    bias["bearish_engulfing"] = bool(is_bearish_engulfing(df) and vol_ok)

    lookback_low = df["low"].iloc[-(WEEKLY_LOOKBACK_DAYS + 1):-1].min()
    downtrend_ok = today["close"] < today["ema20"]
    if not pd.isna(today["ema50"]):
        downtrend_ok = downtrend_ok and today["ema20"] < today["ema50"]
    bear_momentum_ok = WEEKLY_RSI_BEAR_LOW <= today["rsi14"] <= WEEKLY_RSI_BEAR_HIGH and today["roc10"] < 0
    bias["weekly_downtrend_ok"] = bool(downtrend_ok)
    bias["weekly_bear_momentum_ok"] = bool(bear_momentum_ok and today["close"] < lookback_low)
    bias["macd_cross_down"] = bool(prev["macd"] >= prev["macd_signal"] and today["macd"] < today["macd_signal"])
    if not pd.isna(today["ema200"]) and not pd.isna(prev["ema200"]) and not pd.isna(prev["ema50"]):
        bias["death_cross"] = bool(prev["ema50"] >= prev["ema200"] and today["ema50"] < today["ema200"])

    bull_score = sum([bias["positional_breakout"], bias["bullish_engulfing"], bias["weekly_trend_ok"],
                       bias["weekly_momentum_ok"], bias["macd_cross_up"], bias["golden_cross"]])
    bear_score = sum([bias["positional_breakdown"], bias["bearish_engulfing"], bias["weekly_downtrend_ok"],
                       bias["weekly_bear_momentum_ok"], bias["macd_cross_down"], bias["death_cross"]])
    bias["bull_score"] = bull_score
    bias["bear_score"] = bear_score
    bias["score"] = max(bull_score, bear_score)

    # Direction requires both a minimum confluence score AND (optionally) the
    # matching trend leg to agree, so e.g. a single-day breakout + engulfing
    # candle alone (2 conditions from the same day's price action) can't flip
    # the bias without the multi-day trend also confirming.
    if bull_score > bear_score and bull_score >= BIAS_SCORE_MIN:
        if not REQUIRE_TREND_CONFIRMATION or bias["weekly_trend_ok"]:
            bias["direction"] = "BULLISH"
    elif bear_score > bull_score and bear_score >= BIAS_SCORE_MIN:
        if not REQUIRE_TREND_CONFIRMATION or bias["weekly_downtrend_ok"]:
            bias["direction"] = "BEARISH"

    return bias


DAILY_BIAS: dict = {}
BIAS_REFRESHED_ON = None


def refresh_daily_bias(universe: list[str]):
    global BIAS_REFRESHED_ON
    for symbol in universe:
        try:
            daily_df = get_daily_candles(symbol, days=220)
            DAILY_BIAS[symbol] = compute_daily_bias(daily_df)
        except Exception as e:
            log.warning(f"Daily bias refresh failed for {symbol}: {e}")
    BIAS_REFRESHED_ON = datetime.now(IST).date()
    log.info("Daily bias refreshed for intraday confirmation")


# --------------------------------------------------------------------------- #
# MARKET HOURS
# --------------------------------------------------------------------------- #

def is_market_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


# --------------------------------------------------------------------------- #
# MAIN LOOP
# --------------------------------------------------------------------------- #

def run_intraday_scan(universe: list[str]):
    trade_date = datetime.now(IST).date().isoformat()
    cycle_start = time_module.monotonic()
    scanned, failed, fired, skipped_exposure = 0, 0, 0, 0
    for symbol in universe:
        try:
            contract = get_contract(symbol)
            df = get_intraday_candles(symbol)
        except Exception as e:
            log.warning(f"Intraday candle fetch failed for {symbol}: {e}")
            failed += 1
            continue
        bias = DAILY_BIAS.get(symbol)
        try:
            snapshot = get_market_snapshot(symbol)
        except Exception as e:
            log.debug(f"{symbol} | market snapshot fetch failed (continuing without OI/depth): {e}")
            snapshot = None

        if symbol_has_open_position(symbol):
            # Per-symbol exposure cap -- don't stack a second option position
            # (e.g. VWAP reclaim firing on top of an already-open ORB
            # breakout) on the same underlying. See CHANGELOG.
            skipped_exposure += 1
            continue

        try:
            sigs = check_intraday(symbol, df, contract, bias, snapshot)
        except Exception as e:
            log.error(f"check_intraday failed for {symbol}: {e}")
            failed += 1
            continue
        scanned += 1
        for sig in sigs:
            key = ("mcx_intraday_signals", sig["symbol"], sig["strategy"], trade_date)
            if key in OPEN_POSITIONS:
                continue
            upsert_signal("mcx_intraday_signals", sig)
            track_signal("mcx_intraday_signals", sig)
            fired += 1
            break  # one fill per symbol per cycle even if multiple strategies fired together

    elapsed = time_module.monotonic() - cycle_start
    log.info(
        f"Cycle done in {elapsed:.1f}s | scanned={scanned}/{len(universe)} "
        f"failed={failed} signals_fired={fired} skipped_exposure_cap={skipped_exposure} "
        f"open_positions={len(OPEN_POSITIONS)}"
    )


def main():
    _lock = acquire_singleton_lock()
    log.info("Starting MCX scanner")
    universe = MCX_CONTRACTS
    log.info(f"Loaded {len(universe)} MCX contracts")

    rehydrate_open_positions("mcx_intraday_signals", datetime.now(IST).date().isoformat())

    while True:
        now = datetime.now(IST)

        if not is_market_open(now):
            log.info("Market closed. Sleeping 5 min...")
            time_module.sleep(300)
            continue

        if now.date() != BIAS_REFRESHED_ON:
            refresh_daily_bias(universe)

        try:
            run_intraday_scan(universe)
            update_open_signals()
        except Exception:
            log.error("Error in scan loop:\n" + traceback.format_exc())

        time_module.sleep(INTRADAY_POLL_SECONDS)


if __name__ == "__main__":
    if "--setup" in sys.argv:
        install_cron()
    else:
        main()