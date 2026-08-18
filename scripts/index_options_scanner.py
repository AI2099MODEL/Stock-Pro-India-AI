import re
import json
import yaml
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from backports.zoneinfo import ZoneInfo
from NorenRestApiPy.NorenApi import NorenApi

# ---------- CONFIG ----------
CRED_PATH = '/home/ubuntu/Stock-Pro-India/cred.yaml'
IST = ZoneInfo('Asia/Kolkata')
SUPABASE_URL = 'https://gshiddtlkiihwnxvxzle.supabase.co'
SUPABASE_ANON_KEY = 'sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F'

# Risk parameters — ASSUMED, not derived from market data. Tune these.
TARGET_PCT = 0.15   # 15% target on premium
SL_PCT = 0.08        # 8% trailing stop on premium

# ---------- SETUP ----------
with open(CRED_PATH) as f:
    cred = yaml.safe_load(f)

api = NorenApi(
    host='https://api.shoonya.com/NorenWClientAPI/',
    websocket='wss://api.shoonya.com/NorenWSAPI/'
)
api.injectOAuthHeader(cred['Access_token'], cred['UID'], cred['Account_ID'])


def clean_row(row):
    import math
    cleaned = {}
    for k, v in row.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            cleaned[k] = None
        else:
            cleaned[k] = v
    return cleaned


def supabase_insert(rows):
    if not rows:
        print("No rows to insert.")
        return False
    rows = [clean_row(r) for r in rows]
    url = f"{SUPABASE_URL}/rest/v1/index_breakout_signals"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    r = requests.post(url, headers=headers, json=rows)
    if r.status_code >= 300:
        print("SUPABASE INSERT FAILED:", r.status_code, r.text[:500])
        return False
    else:
        print(f"Supabase insert confirmed OK ({r.status_code}), {len(rows)} rows sent.")
        return True


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def compute_vwap(df):
    tp = df['intc'].astype(float)
    vol = df['intv'].astype(float)
    cum_vol = vol.cumsum()
    cum_vol = cum_vol.replace(0, np.nan)
    vwap = (tp * vol).cumsum() / cum_vol
    return vwap.iloc[-1] if len(vwap) else None


def get_intraday_indicators(token, exchange='NFO'):
    """Fetch latest session's 5-min candles, compute VWAP + EMA9 + EMA21.
    Falls back up to 5 days if today has no data (weekend/holiday/pre-market)."""
    candles = None
    for days_back in range(0, 6):
        session_start = (datetime.now(IST) - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            candles = api.get_time_price_series(
                exchange=exchange, token=token,
                starttime=session_start.timestamp(), interval=5
            )
            if candles:
                break
        except Exception as e:
            print(f'Fetch attempt failed for token {token}, {days_back} days back: {e}')
            candles = None

    if not candles:
        print(f'No candle data found for token {token} in last 5 days.')
        return None

    try:
        df = pd.DataFrame(candles)
        df = df.iloc[::-1].reset_index(drop=True)  # oldest first
        df['intc'] = df['intc'].astype(float)
        vwap = compute_vwap(df)
        ema9 = ema(df['intc'], 9).iloc[-1]
        ema21 = ema(df['intc'], 21).iloc[-1] if len(df) >= 21 else ema(df['intc'], len(df)).iloc[-1]
        day_high = df['inth'].astype(float).max()
        day_low = df['intl'].astype(float).min()
        ltp = df['intc'].iloc[-1]
        return dict(vwap=vwap, ema9=ema9, ema21=ema21, day_high=day_high, day_low=day_low, ltp=ltp)
    except Exception as e:
        print(f"Indicator calc failed for token {token}: {e}")
        return None


def scan_index_options():
    """Nearest-expiry options near ATM strike. Gets spot via the correct futures
    contract, rounds to a real ATM strike, then searches narrowly for that strike
    (avoids truncated broad-search results missing near-spot strikes)."""
    targets = [
        ("NIFTY", "NFO", 50),
        ("BANKNIFTY", "NFO", 100),
        ("SENSEX", "BFO", 100),
    ]
    rows_to_insert = []

    def parse_exd(exd_str):
        return datetime.strptime(exd_str, '%d-%b-%Y')

    def extract_strike(tsym):
        digits = re.findall(r"[0-9]+", tsym)
        return float(digits[-1]) if digits else 0

    for symname, exch, strike_step in targets:
        try:
            fut_search = api.searchscrip(exchange=exch, searchtext=symname)
            if not fut_search or 'values' not in fut_search:
                print(f"No search results for {symname}")
                continue

            if exch == "NFO":
                futs = [v for v in fut_search['values']
                        if v.get('symname') == symname and v.get('instname') == 'FUTIDX']
            else:
                futs = [v for v in fut_search['values']
                        if v.get('tsym', '').startswith(symname) and v.get('instname') == 'FUTIDX']

            if not futs:
                print(f"No futures contract found for {symname} to get spot price")
                continue

            nearest_fut = sorted(futs, key=lambda x: parse_exd(x['exd']))[0]
            spot_quote = api.get_quotes(exchange=exch, token=nearest_fut['token'])
            spot_price = float(spot_quote.get('sptprc') or spot_quote.get('lp') or 0) if spot_quote else 0

            if spot_price <= 0:
                print(f"Could not determine spot price for {symname}")
                continue

            atm_strike = round(spot_price / strike_step) * strike_step

            narrow_search = api.searchscrip(exchange=exch, searchtext=f"{symname} {int(atm_strike)}")
            if not narrow_search or 'values' not in narrow_search:
                print(f"No narrow search results for {symname} strike {atm_strike}")
                continue

            atm_candidates = [v for v in narrow_search['values']
                               if v.get('tsym', '').startswith(symname)
                               and v.get('instname') == 'OPTIDX'
                               and extract_strike(v['tsym']) == atm_strike]

            if not atm_candidates:
                print(f"No exact ATM contracts found for {symname} at strike {atm_strike}")
                continue

            nearest_exd = min(parse_exd(v['exd']) for v in atm_candidates)
            nearest_exd_str = nearest_exd.strftime('%d-%b-%Y').upper()
            anchor = next(v for v in atm_candidates if v['exd'] == nearest_exd_str)

            chain_url = "https://api.shoonya.com/NorenWClientAPI/GetOptionChain"
            chain_values = {
                'uid': cred['UID'], 'exch': exch, 'tsym': anchor['tsym'],
                'strprc': str(int(atm_strike)), 'cnt': '10'
            }
            chain_payload = 'jData=' + json.dumps(chain_values) + '&jKey=' + cred['Access_token']
            chain_resp = requests.post(chain_url, data=chain_payload)
            chain = chain_resp.json() if chain_resp.status_code == 200 else None

            if not chain or chain.get('stat') != 'Ok' or 'values' not in chain:
                print(f"No option chain returned for {symname} anchor {anchor['tsym']}")
                continue

            print(f"{symname}: spot={spot_price}, ATM strike={atm_strike}, expiry={nearest_exd_str}, anchor={anchor['tsym']}")

            for c in chain['values']:
                strike_val = float(c.get('strprc', 0) or 0)
                offset = round((strike_val - atm_strike) / strike_step)
                if abs(offset) > 2:
                    continue  # only keep ATM, ATM±1, ATM±2

                opt_type = c.get('optt')
                if opt_type == 'CE':
                    moneyness = 'ATM' if offset == 0 else ('ITM' if offset < 0 else 'OTM')
                elif opt_type == 'PE':
                    moneyness = 'ATM' if offset == 0 else ('OTM' if offset < 0 else 'ITM')
                else:
                    moneyness = 'UNKNOWN'

                token = c.get('token')
                ind = get_intraday_indicators(token, exch)
                if not ind:
                    continue

                lot_size = int(c.get('ls', 0) or 0)
                entry_price = ind['ltp']
                money_required = entry_price * lot_size if lot_size else None
                target_price = entry_price * (1 + TARGET_PCT)
                trail_sl = entry_price * (1 - SL_PCT)
                potential_profit = (target_price - entry_price) * lot_size if lot_size else None

                rows_to_insert.append({
                    "exchange": exch, "symbol": c.get('tsym', symname),
                    "token": token, "strike": c.get('strprc'), "option_type": opt_type,
                    "expiry": nearest_exd_str, "atm_offset": offset, "moneyness": moneyness,
                    "lot_size": lot_size, "ltp": entry_price, "vwap": ind['vwap'],
                    "ema9": ind['ema9'], "ema21": ind['ema21'],
                    "day_high": ind['day_high'], "day_low": ind['day_low'], "signal": "NONE",
                    "money_required": money_required, "target_price": target_price,
                    "trail_sl": trail_sl, "potential_profit": potential_profit
                })
                time.sleep(0.3)
        except Exception as e:
            print(f"Error scanning options for {symname}: {e}")
    success = supabase_insert(rows_to_insert)
    if success:
        print(f"Confirmed inserted {len(rows_to_insert)} option rows.")
    else:
        print(f"FAILED to insert {len(rows_to_insert)} option rows — see error above.")


if __name__ == "__main__":
    scan_index_options()
    print("Index options scan complete.")
