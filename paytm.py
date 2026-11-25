"""Paytm Money live prices (optional).

Yahoo Finance gives the price history; Paytm Money gives today's live price.
When you are logged in to Paytm, today's bar is replaced with live data so
levels and signals use the real current price.

Setup (once): put your API key and secret in Streamlit -> Settings -> Secrets:

    [paytm]
    api_key = "..."
    api_secret = "..."

Login (daily): press "Login to Paytm Money" in the sidebar. Paytm sends you
back to this app with a requestToken, which is exchanged for an access token
that lasts until the end of the day.
"""

from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

HOST = "https://developer.paytmmoney.com"
LOGIN_URL = "https://login.paytmmoney.com/merchant-login?apiKey={key}&state={state}"
SCRIP_URL = HOST + "/data/v1/scrips/nse_security_master.csv"
IST = ZoneInfo("Asia/Kolkata")

# Yahoo index symbol -> Paytm NSE index security id
INDEX_IDS = {"^NSEI": "13", "^NSEBANK": "25", "^CNXIT": "29", "^INDIAVIX": "21"}


# ------------------------------------------------------------------ config

def _secrets() -> dict:
    try:
        return dict(st.secrets.get("paytm", {}))
    except Exception:  # no secrets file at all
        return {}


def configured() -> bool:
    s = _secrets()
    return bool(s.get("api_key") and s.get("api_secret"))


def login_url() -> str:
    return LOGIN_URL.format(key=_secrets()["api_key"], state="market-analyser")


# --------------------------------------------------------- token handling
# The token is kept in a server-side store for the day so it survives page
# reloads. Keep the app private (Streamlit sharing settings), because anyone
# who can open the app would use this login for live prices.

@st.cache_resource
def _store() -> dict:
    return {}


def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def token() -> str | None:
    t = _store()
    if t.get("date") == _today():
        return t.get("read_access_token") or t.get("access_token")
    return None


def connected() -> bool:
    return token() is not None


def logout():
    _store().clear()


def exchange_request_token(request_token: str) -> tuple[bool, str]:
    s = _secrets()
    try:
        r = requests.post(HOST + "/accounts/v2/gettoken", timeout=20, json={
            "api_key": s["api_key"], "api_secret_key": s["api_secret"],
            "request_token": request_token})
    except Exception as e:
        return False, f"Could not reach Paytm: {e}"
    if r.status_code != 200:
        return False, f"Paytm login failed ({r.status_code}): {r.text[:200]}"
    data = r.json()
    if not (data.get("read_access_token") or data.get("access_token")):
        return False, f"Unexpected response from Paytm: {str(data)[:200]}"
    store = _store()
    store.clear()
    store.update({k: data.get(k) for k in
                  ("access_token", "read_access_token", "public_access_token")})
    store["date"] = _today()
    return True, "Connected to Paytm Money"


def handle_redirect():
    """Call once per run: picks up ?requestToken=... after Paytm login."""
    req = st.query_params.get("requestToken") or st.query_params.get("request_token")
    if not req:
        return None
    ok, msg = exchange_request_token(req)
    for k in ("requestToken", "request_token", "state", "success"):
        if k in st.query_params:
            del st.query_params[k]
    return ok, msg


# ---------------------------------------------------------------- scrips

@st.cache_data(ttl=24 * 3600, show_spinner=False)
def security_ids() -> dict[str, str]:
    """NSE cash-market symbol -> Paytm security id (EQ series)."""
    r = requests.get(SCRIP_URL, timeout=60)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text), dtype=str)
    d = d[(d["instrument_type"].isin(["ES", "ETF"])) & (d["series"].isin(["EQ", "BE"]))]
    d = d.sort_values("series")  # EQ before BE
    return dict(zip(d["symbol"].str.upper(), d["security_id"]))


def pref_for(yahoo_ticker: str) -> str | None:
    if yahoo_ticker in INDEX_IDS:
        return f"NSE:{INDEX_IDS[yahoo_ticker]}:INDEX"
    if not yahoo_ticker.endswith(".NS"):
        return None
    try:
        sid = security_ids().get(yahoo_ticker[:-3].upper())
    except Exception:
        return None
    return f"NSE:{sid}:EQUITY" if sid else None


# ---------------------------------------------------------------- quotes

@st.cache_data(ttl=20, show_spinner=False)
def _quotes(prefs: tuple[str, ...], tok: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(prefs), 50):
        part = ",".join(prefs[i:i + 50])
        r = requests.get(f"{HOST}/data/v1/price/live", timeout=20,
                         params={"mode": "QUOTE", "pref": part},
                         headers={"x-jwt-token": tok})
        if r.status_code == 401:
            raise PermissionError("Paytm session expired")
        r.raise_for_status()
        for q in r.json().get("data", []) or []:
            if q.get("found") is False:
                continue
            sid = str(q.get("security_id", ""))
            if sid:
                out[sid] = q
    return out


def quotes(yahoo_tickers: list[str]) -> dict[str, dict]:
    """Live quotes keyed by Yahoo ticker. Empty if not connected or on error."""
    tok = token()
    if not tok:
        return {}
    prefs = {t: pref_for(t) for t in yahoo_tickers}
    prefs = {t: p for t, p in prefs.items() if p}
    if not prefs:
        return {}
    try:
        raw = _quotes(tuple(sorted(set(prefs.values()))), tok)
    except PermissionError:
        logout()
        return {}
    except Exception:
        return {}
    return {t: raw[p.split(":")[1]] for t, p in prefs.items() if p.split(":")[1] in raw}


def _trade_day(q: dict) -> pd.Timestamp:
    """Trading date of a quote (IST), falling back to today."""
    ts = q.get("last_trade_time") or q.get("last_update_time")
    try:
        if isinstance(ts, (int, float)) or str(ts).isdigit():
            v = float(ts)
            # Paytm epochs are seconds; some feeds count from 1980-01-01
            dt = pd.Timestamp(v, unit="s", tz="UTC")
            if dt.year < 2015:
                dt = pd.Timestamp("1980-01-01", tz="UTC") + pd.Timedelta(seconds=v)
            return dt.tz_convert(IST).tz_localize(None).normalize()
        if ts:
            return pd.Timestamp(ts).tz_localize(None).normalize()
    except Exception:
        pass
    return pd.Timestamp(datetime.now(IST).date())


def apply_quote(df: pd.DataFrame, q: dict | None) -> pd.DataFrame:
    """Replace or append today's bar with the live quote."""
    if df.empty or not q or q.get("last_price") in (None, 0):
        return df
    ohlc = q.get("ohlc") or {}
    last = float(q["last_price"])
    day = _trade_day(q)
    o = float(ohlc.get("open") or last)
    h = max(float(ohlc.get("high") or last), last)
    lo = min(float(ohlc.get("low") or last), last)
    vol = q.get("volume_traded") or q.get("volume") or q.get("total_traded_volume")
    df = df.copy()
    if df.index[-1].normalize() == day:
        df.loc[df.index[-1], ["Open", "High", "Low", "Close"]] = [o, h, lo, last]
        if vol:
            df.loc[df.index[-1], "Volume"] = float(vol)
    elif day > df.index[-1].normalize():
        df.loc[day] = [o, h, lo, last, float(vol) if vol else float(df["Volume"].iloc[-1])]
    return df
