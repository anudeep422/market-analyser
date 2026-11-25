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


def returns(df: pd.DataFrame) -> dict:
    """Price change over standard periods (trading days)."""
    c = df["Close"]
    out = {}
    for name, n in (("1 week", 5), ("1 month", 21), ("3 months", 63),
                    ("6 months", 126), ("1 year", 252)):
        out[name] = (c.iloc[-1] / c.iloc[-n - 1] - 1) * 100 if len(c) > n else None
    return out


def stock_report(df: pd.DataFrame, fund: dict | None = None, name: str | None = None) -> dict:
    """Plain-language analysis of one stock.

    Returns {"verdict", "score", "headline", "sections": [(title, [lines])],
    "watch": [lines]} built only from the numbers, so it is reproducible.
    """
    fund = fund or {}
    d = add_indicators(df) if "RSI" not in df.columns else df
    last = d.iloc[-1]
    close = float(last["Close"])
    sig = technical_signal(d)
    ret = returns(d)
    year = d.tail(252)
    hi, lo = float(year["High"].max()), float(year["Low"].min())
    piv = pivot_levels(float(last["High"]), float(last["Low"]), close)
    sw = swing_levels(d)
    s50, s200 = _num(last.get("SMA50")), _num(last.get("SMA200"))
    r = _num(last.get("RSI"))
    sections: list[tuple[str, list[str]]] = []

    # 1. performance
    perf = [f"{k}: {v:+.1f}%" for k, v in ret.items() if v is not None]
    pos = (close - lo) / (hi - lo) * 100 if hi > lo else 50
    perf.append(f"Trading at ₹{close:,.2f}, {abs(close / hi - 1) * 100:.1f}% below the "
                f"52-week high (₹{hi:,.0f}) and {(close / lo - 1) * 100:+.1f}% from the "
                f"low (₹{lo:,.0f}) — {pos:.0f}% of the way up its yearly range.")
    sections.append(("Performance", perf))

    # 2. trend
    trend = []
    if s200 is not None and s50 is not None:
        if close > s50 > s200:
            trend_word = "an uptrend"
            trend.append("Strong uptrend: price is above the 50-day, and the 50-day is above the 200-day.")
        elif close < s50 < s200:
            trend_word = "a downtrend"
            trend.append("Clear downtrend: price is below the 50-day, and the 50-day is below the 200-day. "
                         "Bounces often get sold until this changes.")
        elif close > s200:
            trend_word = "a mixed trend (long-term up)"
            trend.append("Long-term trend is up (above the 200-day), but short-term momentum is mixed.")
        else:
            trend_word = "a mixed trend (long-term down)"
            trend.append("Long-term trend is down (below the 200-day); a short-term recovery is being attempted.")
        trend.append(f"50-day average ₹{s50:,.0f} ({(close / s50 - 1) * 100:+.1f}%), "
                     f"200-day average ₹{s200:,.0f} ({(close / s200 - 1) * 100:+.1f}%).")
    elif s50 is not None:
        trend_word = "a short-term uptrend" if close > s50 else "a short-term downtrend"
        trend.append(f"Not enough history for a 200-day average; price is "
                     f"{'above' if close > s50 else 'below'} the 50-day (₹{s50:,.0f}).")
    else:
        trend_word = "an unclear trend"
        trend.append("Not enough history to judge the trend.")
    sections.append(("Trend", trend))

    # 3. momentum
    mom = []
    if r is not None:
        if r < 30:
            mom.append(f"RSI {r:.0f} — oversold. Selling may be overdone; a bounce is possible, "
                       "but oversold stocks can stay oversold in a downtrend.")
        elif r > 70:
            mom.append(f"RSI {r:.0f} — overbought. Strong buying, but a pause or pullback is common from here.")
        elif r >= 50:
            mom.append(f"RSI {r:.0f} — neutral with buyers slightly in control.")
        else:
            mom.append(f"RSI {r:.0f} — neutral with sellers slightly in control.")
    m, s = _num(last.get("MACD")), _num(last.get("Signal"))
    if m is not None and s is not None:
        mom.append("MACD is above its signal line — momentum improving." if m > s
                   else "MACD is below its signal line — momentum weakening.")
    vr = (float(last["Volume"]) / float(last["VolAvg20"])) if _num(last.get("VolAvg20")) else None
    if vr is not None:
        if vr > 1.5:
            mom.append(f"Volume was {vr:.1f}× the 20-day average — the last move had strong participation.")
        elif vr < 0.6:
            mom.append(f"Volume was only {vr:.1f}× the 20-day average — the last move lacked conviction.")
    sections.append(("Momentum", mom))

    # 4. levels
    lv = [f"Next session pivot ₹{piv['Pivot']:,.1f}. Resistance R1 ₹{piv['R1']:,.1f}, "
          f"R2 ₹{piv['R2']:,.1f}. Support S1 ₹{piv['S1']:,.1f}, S2 ₹{piv['S2']:,.1f}.",
          ("Close is above the pivot — slight bullish bias for the day." if close > piv["Pivot"]
           else "Close is below the pivot — slight bearish bias for the day.")]
    if sw["support"]:
        lv.append("Swing support zones: " + ", ".join(f"₹{p:,.0f}" for p, _ in sw["support"][:3]) + ".")
    if sw["resistance"]:
        lv.append("Swing resistance zones: " + ", ".join(f"₹{p:,.0f}" for p, _ in sw["resistance"][:3]) + ".")
    a = _num(last.get("ATR"))
    if a is not None:
        lv.append(f"Typical daily move (ATR) is about ₹{a:,.1f} ({a / close * 100:.1f}%) — "
                  f"a stop-loss tighter than this tends to get hit by normal noise.")
    sections.append(("Support & resistance", lv))

    # 5. fundamentals
    fl = []
    pe, pb, roe = fund.get("P/E (TTM)"), fund.get("P/B"), fund.get("ROE %")
    de, dy, rg = fund.get("Debt / Equity"), fund.get("Dividend yield %"), fund.get("Revenue growth %")
    val_score = 0
    if pe:
        if pe < 15:
            fl.append(f"P/E {pe:.1f} — inexpensive. Check whether the market expects slower growth.")
            val_score += 1
        elif pe < 30:
            fl.append(f"P/E {pe:.1f} — reasonably valued.")
        else:
            fl.append(f"P/E {pe:.1f} — expensive; the price assumes strong future growth.")
            val_score -= 1
    if pb:
        fl.append(f"P/B {pb:.1f}.")
    if roe is not None:
        if roe > 18:
            fl.append(f"ROE {roe:.1f}% — high-quality, efficient business.")
            val_score += 1
        elif roe < 10:
            fl.append(f"ROE {roe:.1f}% — weak returns on shareholder money.")
            val_score -= 1
        else:
            fl.append(f"ROE {roe:.1f}% — average.")
    if de is not None:
        if de < 50:
            fl.append(f"Debt/equity {de:.0f}% — low debt, strong balance sheet.")
            val_score += 1
        elif de > 150:
            fl.append(f"Debt/equity {de:.0f}% — heavily borrowed; riskier if rates rise or profits fall.")
            val_score -= 1
        else:
            fl.append(f"Debt/equity {de:.0f}% — moderate debt.")
    if rg is not None:
        fl.append(f"Revenue growth {rg:+.1f}% year on year" + (" — slow." if rg < 5 else "."))
        val_score += 1 if rg > 12 else -1 if rg < 0 else 0
    if dy:
        fl.append(f"Dividend yield {dy:.2f}%.")
    if fl:
        sections.append(("Fundamentals", fl))

    # verdict
    score = sig["score"]
    tech_view = ("bullish" if score >= 15 else "bearish" if score <= -15 else "neutral")
    if fl:
        fund_view = "strong" if val_score >= 2 else "weak" if val_score <= -1 else "average"
    else:
        fund_view = None

    if tech_view == "bullish" and fund_view in ("strong", None):
        verdict = "Positive"
        view = ("Price trend and momentum are supportive"
                + (" and the business looks solid." if fund_view else ".")
                + " Buying on dips towards support is safer than chasing strength.")
    elif tech_view == "bearish" and fund_view == "strong":
        verdict = "Good business, weak chart"
        view = ("The fundamentals look solid but the price trend is down. Long-term investors may "
                "accumulate slowly in parts; traders usually wait for the price to reclaim the "
                "50-day average before buying.")
    elif tech_view == "bearish":
        verdict = "Negative"
        view = ("The trend is down and the numbers give no strong reason to step in yet. "
                "Wait for the price to stabilise above support and the 50-day average.")
    elif tech_view == "bullish":
        verdict = "Positive chart, check fundamentals"
        view = ("The chart is strong but the fundamentals are not convincing — fine for a short-term "
                "trade with a stop-loss, riskier as a long-term holding.")
    else:
        verdict = "Neutral / wait"
        view = ("Signals are mixed. Wait for a break above resistance (bullish) or below support "
                "(bearish) before acting.")
    sections.append(("Overall view", [view]))

    watch = [f"A daily close above ₹{piv['R1']:,.0f} (R1) would show short-term strength."]
    if s50 is not None:
        watch.append(f"Reclaiming the 50-day average (₹{s50:,.0f}) would improve the trend."
                     if close < s50 else
                     f"Holding above the 50-day average (₹{s50:,.0f}) keeps the trend intact.")
    watch.append(f"A close below ₹{piv['S2']:,.0f} (S2) would signal further weakness.")
    if r is not None and r < 30:
        watch.append("RSI moving back above 30 would confirm the oversold bounce.")

    name = fund.get("Name") or name or "This stock"
    headline = (f"{name} is in {trend_word} with a {tech_view} technical score of {score:+d}"
                + (f" and {fund_view} fundamentals." if fund_view else "."))
    return {"verdict": verdict, "score": score, "tech_view": tech_view,
            "fund_view": fund_view, "headline": headline,
            "sections": sections, "watch": watch}


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
