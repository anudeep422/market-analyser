"""Pure analysis functions for the Indian market analyser.

Every function takes a pandas DataFrame with columns Open, High, Low, Close,
Volume (daily bars, oldest first) and returns plain numbers or Series, so the
logic can be tested without any network access.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- pivots

def pivot_levels(high: float, low: float, close: float, method: str = "classic") -> dict:
    """Pivot point with three resistance and three support levels.

    Uses the previous session's high, low and close.
    method: "classic", "fibonacci" or "camarilla".
    """
    p = (high + low + close) / 3
    rng = high - low

    if method == "classic":
        r1, s1 = 2 * p - low, 2 * p - high
        r2, s2 = p + rng, p - rng
        r3, s3 = high + 2 * (p - low), low - 2 * (high - p)
    elif method == "fibonacci":
        r1, s1 = p + 0.382 * rng, p - 0.382 * rng
        r2, s2 = p + 0.618 * rng, p - 0.618 * rng
        r3, s3 = p + 1.000 * rng, p - 1.000 * rng
    elif method == "camarilla":
        r1, s1 = close + rng * 1.1 / 12, close - rng * 1.1 / 12
        r2, s2 = close + rng * 1.1 / 6, close - rng * 1.1 / 6
        r3, s3 = close + rng * 1.1 / 4, close - rng * 1.1 / 4
    else:
        raise ValueError(f"Unknown pivot method: {method}")

    return {"R3": r3, "R2": r2, "R1": r1, "Pivot": p, "S1": s1, "S2": s2, "S3": s3}


def swing_levels(df: pd.DataFrame, window: int = 5, lookback: int = 120,
                 tolerance: float = 0.015, max_levels: int = 4) -> dict:
    """Support/resistance from recent swing highs and lows.

    A swing high is a bar whose High is the highest within `window` bars on
    each side. Nearby swings (within `tolerance`) are merged into one zone.
    Returns the nearest levels below (support) and above (resistance) the
    last close.
    """
    data = df.tail(lookback)
    if len(data) < 2 * window + 1:
        return {"support": [], "resistance": []}

    highs, lows = data["High"].to_numpy(), data["Low"].to_numpy()
    points = []
    for i in range(window, len(data) - window):
        if highs[i] == highs[i - window:i + window + 1].max():
            points.append(highs[i])
        if lows[i] == lows[i - window:i + window + 1].min():
            points.append(lows[i])

    # merge nearby levels into zones (strength = touches)
    zones: list[list[float]] = []
    for lvl in sorted(points):
        if zones and abs(lvl - np.mean(zones[-1])) / np.mean(zones[-1]) <= tolerance:
            zones[-1].append(lvl)
        else:
            zones.append([lvl])
    merged = [(float(np.mean(z)), len(z)) for z in zones]

    last = float(df["Close"].iloc[-1])
    support = sorted([z for z in merged if z[0] < last], key=lambda z: -z[0])[:max_levels]
    resistance = sorted([z for z in merged if z[0] > last], key=lambda z: z[0])[:max_levels]
    return {"support": support, "resistance": resistance}


# ------------------------------------------------------------ indicators

def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0)          # only gains -> 100
    out = out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return out.where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"MACD": line, "Signal": sig, "Hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std()
    return pd.DataFrame({"Upper": mid + k * sd, "Mid": mid, "Lower": mid - k * sd})


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["Close"].shift()
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with all indicator columns added."""
    out = df.copy()
    c = out["Close"]
    out["SMA20"] = sma(c, 20)
    out["SMA50"] = sma(c, 50)
    out["SMA200"] = sma(c, 200)
    out["EMA20"] = ema(c, 20)
    out["RSI"] = rsi(c)
    out = out.join(macd(c))
    out = out.join(bollinger(c).add_prefix("BB_"))
    out["ATR"] = atr(out)
    out["VolAvg20"] = sma(out["Volume"], 20)
    return out


# ---------------------------------------------------------------- signal

def _num(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def technical_signal(df: pd.DataFrame) -> dict:
    """Score the latest bar from -100 (strong sell) to +100 (strong buy).

    Each rule votes +1 / -1 / 0; the score is the average vote scaled to 100.
    Returns the score, a label and the reasons, so the user can see why.
    """
    d = add_indicators(df) if "RSI" not in df.columns else df
    last, prev = d.iloc[-1], d.iloc[-2] if len(d) > 1 else d.iloc[-1]
    close = float(last["Close"])
    votes: list[tuple[int, str]] = []

    for col, name in (("SMA20", "20-day"), ("SMA50", "50-day"), ("SMA200", "200-day")):
        v = _num(last.get(col))
        if v is not None:
            votes.append((1, f"Price above {name} average (₹{v:,.0f})") if close > v
                         else (-1, f"Price below {name} average (₹{v:,.0f})"))

    s50, s200 = _num(last.get("SMA50")), _num(last.get("SMA200"))
    if s50 is not None and s200 is not None:
        votes.append((1, "50-day above 200-day (golden-cross zone)") if s50 > s200
                     else (-1, "50-day below 200-day (death-cross zone)"))

    r = _num(last.get("RSI"))
    if r is not None:
        if r < 30:
            votes.append((1, f"RSI {r:.1f}: oversold, bounce possible"))
        elif r > 70:
            votes.append((-1, f"RSI {r:.1f}: overbought, pullback possible"))
        else:
            votes.append((0, f"RSI {r:.1f}: neutral"))

    m, s = _num(last.get("MACD")), _num(last.get("Signal"))
    if m is not None and s is not None:
        pm, ps = _num(prev.get("MACD")), _num(prev.get("Signal"))
        crossed_up = pm is not None and ps is not None and pm <= ps and m > s
        crossed_dn = pm is not None and ps is not None and pm >= ps and m < s
        if crossed_up:
            votes.append((1, "MACD just crossed above signal (bullish)"))
        elif crossed_dn:
            votes.append((-1, "MACD just crossed below signal (bearish)"))
        else:
            votes.append((1, "MACD above signal line") if m > s
                         else (-1, "MACD below signal line"))

    bu, bl = _num(last.get("BB_Upper")), _num(last.get("BB_Lower"))
    if bu is not None and bl is not None:
        if close < bl:
            votes.append((1, "Below lower Bollinger band (stretched down)"))
        elif close > bu:
            votes.append((-1, "Above upper Bollinger band (stretched up)"))

    if not votes:
        return {"score": 0, "label": "Not enough data", "reasons": []}

    score = round(100 * sum(v for v, _ in votes) / len(votes))
    if score >= 50:
        label = "Strong Buy"
    elif score >= 15:
        label = "Buy"
    elif score > -15:
        label = "Neutral"
    elif score > -50:
        label = "Sell"
    else:
        label = "Strong Sell"
    return {"score": score, "label": label, "reasons": votes}


def snapshot(df: pd.DataFrame) -> dict:
    """One-row summary used by the watchlist screener."""
    d = add_indicators(df)
    last = d.iloc[-1]
    prev_close = float(d["Close"].iloc[-2]) if len(d) > 1 else float(last["Close"])
    close = float(last["Close"])
    piv = pivot_levels(float(last["High"]), float(last["Low"]), close)
    year = d.tail(252)
    sig = technical_signal(d)

    def pct(a, b):
        return None if b in (None, 0) or pd.isna(b) else (a / b - 1) * 100

    return {
        "Close": close,
        "Change %": pct(close, prev_close),
        "RSI": _num(last["RSI"]),
        "vs 50DMA %": pct(close, _num(last["SMA50"])),
        "vs 200DMA %": pct(close, _num(last["SMA200"])),
        "52W High": float(year["High"].max()),
        "52W Low": float(year["Low"].min()),
        "From 52W High %": pct(close, float(year["High"].max())),
        "Pivot": piv["Pivot"],
        "S1": piv["S1"],
        "R1": piv["R1"],
        "Vol x Avg": (float(last["Volume"]) / float(last["VolAvg20"]))
        if _num(last["VolAvg20"]) else None,
        "Score": sig["score"],
        "Signal": sig["label"],
    }


def sample_data(days: int = 400, start: float = 1500.0, seed: int = 7) -> pd.DataFrame:
    """Random-walk OHLCV data, used for demo mode and tests."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    rets = rng.normal(0, 0.015, days)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.r_[start, close[:-1]] * (1 + rng.normal(0, 0.003, days))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.007, days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.007, days)))
    vol = rng.integers(3_000_000, 12_000_000, days)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)
