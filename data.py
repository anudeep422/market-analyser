"""Market data for NSE/BSE via Yahoo Finance (yfinance).

NSE symbols get a ".NS" suffix and BSE symbols ".BO" (e.g. INFY -> INFY.NS).
Index symbols start with "^" and are used as-is.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf

INDICES = {
    "NIFTY 50": "^NSEI",
    "NIFTY BANK": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTY IT": "^CNXIT",
    "INDIA VIX": "^INDIAVIX",
}

# Constituents change a few times a year. Edit these lists if a symbol stops
# returning data (e.g. after a merger, demerger or index rebalance).
UNIVERSES = {
    "NIFTY 50": [
        "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
        "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
        "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM",
        "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO", "HINDUNILVR",
        "ICICIBANK", "INDIGO", "INFY", "ITC", "JIOFIN", "JSWSTEEL",
        "KOTAKBANK", "LT", "M&M", "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC",
        "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
        "SUNPHARMA", "TATACONSUM", "TATASTEEL", "TCS", "TECHM",
        "TITAN", "TRENT", "ULTRACEMCO", "WIPRO", "TMPV",
    ],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "PERSISTENT",
           "COFORGE", "MPHASIS", "OFSS"],
    "Banks": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK",
              "INDUSINDBK", "BANKBARODA", "PNB", "FEDERALBNK", "IDFCFIRSTB",
              "AUBANK", "CANBK"],
    "Pharma": ["SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN",
               "AUROPHARMA", "TORNTPHARM", "ZYDUSLIFE", "ALKEM", "MANKIND"],
    "Auto": ["MARUTI", "M&M", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO",
             "TVSMOTOR", "TMPV", "ASHOKLEY", "BOSCHLTD", "MOTHERSON"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "TATACONSUM",
             "DABUR", "GODREJCP", "MARICO", "COLPAL", "VBL"],
}


def to_yahoo(symbol: str, exchange: str = "NSE") -> str:
    s = symbol.strip().upper()
    if s.startswith("^") or s.endswith((".NS", ".BO")):
        return s
    return f"{s}.{'BO' if exchange == 'BSE' else 'NS'}"


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(-1, axis=1) if df.columns.nlevels > 1 else df
    df = df[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]]
    df = df.dropna(subset=["Close"])
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def history(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Daily OHLCV for one ticker. Cached for 5 minutes."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    return _clean(df)


@st.cache_data(ttl=300, show_spinner=False)
def history_many(tickers: tuple[str, ...], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Download many tickers in one request; returns {ticker: DataFrame}."""
    out: dict[str, pd.DataFrame] = {}
    if not tickers:
        return out
    try:
        raw = yf.download(list(tickers), period=period, interval="1d",
                          group_by="ticker", auto_adjust=False,
                          progress=False, threads=True)
    except Exception:
        raw = pd.DataFrame()
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            df = pd.DataFrame()
        df = _clean(df)
        if df.empty:          # fall back to a single request
            df = history(t, period)
        out[t] = df
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def fundamentals(ticker: str) -> dict:
    """Key fundamentals. Yahoo's coverage of Indian stocks has gaps,
    so any value may be missing."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}

    def g(k):
        v = info.get(k)
        return None if v in (None, "Infinity", "NaN") else v

    roe = g("returnOnEquity")
    dy = g("dividendYield")
    # yfinance has reported dividend yield both as a fraction and as a %.
    if dy is not None and dy < 1:
        dy *= 100
    mcap = g("marketCap")
    return {
        "Name": g("longName") or g("shortName"),
        "Sector": g("sector"),
        "Industry": g("industry"),
        "Market cap (₹ Cr)": mcap / 1e7 if mcap else None,
        "P/E (TTM)": g("trailingPE"),
        "Forward P/E": g("forwardPE"),
        "P/B": g("priceToBook"),
        "EPS (TTM, ₹)": g("trailingEps"),
        "Book value (₹)": g("bookValue"),
        "ROE %": roe * 100 if roe is not None else None,
        "Debt / Equity": g("debtToEquity"),
        "Dividend yield %": dy,
        "Profit margin %": g("profitMargins") * 100 if g("profitMargins") is not None else None,
        "Revenue growth %": g("revenueGrowth") * 100 if g("revenueGrowth") is not None else None,
        "Beta": g("beta"),
        "52W High": g("fiftyTwoWeekHigh"),
        "52W Low": g("fiftyTwoWeekLow"),
        "Website": g("website"),
        "About": g("longBusinessSummary"),
    }
