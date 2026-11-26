"""Intraday engine: Opening Range Breakout confirmed by VWAP, EMA 9/20,
RSI and volume, on 5-minute candles (NSE cash market, IST).

Rules (long; short is the mirror image)
  * no trades before 9:30 (opening range = 9:15-9:30) or after 14:30
  * NIFTY above its VWAP (market on our side)
  * stock closes above the opening-range high, above VWAP, EMA9 > EMA20,
    RSI(14) > rsi_long, volume > 20-bar average
  * entry next candle's open; stop = nearer of VWAP / signal-candle low;
    target = reward x risk; stop to breakeven at +1R; exit 15:10
  * one trade per stock per day; costs included
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import time

import numpy as np
import pandas as pd

import analysis as A


@dataclass
class IntraParams:
    reward: float = 2.0
    breakeven_r: float = 1.0      # 0 = off
    rsi_long: float = 55.0
    rsi_short: float = 45.0
    allow_short: bool = True
    min_risk_pct: float = 0.20    # never risk less than this % (noise)
    cost_pct: float = 0.15        # round trip: brokerage+STT+charges+slippage
    last_entry: time = time(14, 30)
    exit_time: time = time(15, 10)


# --------------------------------------------------------------- features

def to_ist(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
    return df[(df.index.time >= time(9, 15)) & (df.index.time < time(15, 30))]


def features(df: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP, EMAs, RSI, volume average and opening range per day."""
    d = to_ist(df)
    d["Day"] = d.index.normalize()
    tp = (d["High"] + d["Low"] + d["Close"]) / 3
    pv = (tp * d["Volume"]).groupby(d["Day"]).cumsum()
    vv = d["Volume"].groupby(d["Day"]).cumsum().replace(0, np.nan)
    d["VWAP"] = (pv / vv).fillna(tp)
    d["EMA9"] = A.ema(d["Close"], 9)
    d["EMA20"] = A.ema(d["Close"], 20)
    d["RSI"] = A.rsi(d["Close"], 14)
    d["VolAvg"] = d["Volume"].rolling(20, min_periods=10).mean().shift()
    first = d[d.index.time < time(9, 30)]
    orh = first.groupby("Day")["High"].max()
    orl = first.groupby("Day")["Low"].min()
    d["ORH"] = d["Day"].map(orh)
    d["ORL"] = d["Day"].map(orl)
    daily = d.groupby("Day").agg(H=("High", "max"), L=("Low", "min"), C=("Close", "last"))
    prev = daily.shift()
    d["PDH"] = d["Day"].map(prev["H"])
    d["PDL"] = d["Day"].map(prev["L"])
    d["PDC"] = d["Day"].map(prev["C"])
    return d


def add_market(d: pd.DataFrame, nifty: pd.DataFrame | None) -> pd.DataFrame:
    """Mark whether NIFTY was above (+1) or below (-1) its VWAP on each bar."""
    d = d.copy()
    if nifty is None or nifty.empty:
        d["Mkt"] = 0
        return d
    n = features(nifty)
    side = np.sign(n["Close"] - n["VWAP"]).rename("Mkt")
    d["Mkt"] = side.reindex(d.index).ffill().fillna(0)
    return d


# ------------------------------------------------------------------ rules

def checklist(row: pd.Series, p: IntraParams = IntraParams()) -> dict:
    """The six conditions for each side, for one bar (used live)."""
    vol_ok = pd.notna(row["VolAvg"]) and row["Volume"] > row["VolAvg"]
    t = row.name.time() if hasattr(row.name, "time") else time(12, 0)
    in_window = time(9, 30) <= t <= p.last_entry
    return {
        "BUY": {
            "Time window (9:30–14:30)": in_window,
            "NIFTY above its VWAP": row.get("Mkt", 0) > 0,
            "Above opening-range high": pd.notna(row["ORH"]) and row["Close"] > row["ORH"],
            "Above VWAP": row["Close"] > row["VWAP"],
            "EMA 9 above EMA 20": row["EMA9"] > row["EMA20"],
            f"RSI above {p.rsi_long:g}": pd.notna(row["RSI"]) and row["RSI"] > p.rsi_long,
            "Volume above average": vol_ok,
        },
        "SELL": {
            "Time window (9:30–14:30)": in_window,
            "NIFTY below its VWAP": row.get("Mkt", 0) < 0,
            "Below opening-range low": pd.notna(row["ORL"]) and row["Close"] < row["ORL"],
            "Below VWAP": row["Close"] < row["VWAP"],
            "EMA 9 below EMA 20": row["EMA9"] < row["EMA20"],
            f"RSI below {p.rsi_short:g}": pd.notna(row["RSI"]) and row["RSI"] < p.rsi_short,
            "Volume above average": vol_ok,
        },
    }


def signals(d: pd.DataFrame, p: IntraParams = IntraParams()) -> pd.Series:
    """+1 / -1 on the bar where all conditions are met (first per day/side)."""
    t = pd.Series(d.index.time, index=d.index)
    window = (t >= time(9, 30)) & (t <= p.last_entry)
    vol = d["Volume"] > d["VolAvg"]
    buy = (window & (d["Mkt"] > 0) & (d["Close"] > d["ORH"]) & (d["Close"] > d["VWAP"])
           & (d["EMA9"] > d["EMA20"]) & (d["RSI"] > p.rsi_long) & vol)
    sell = (window & (d["Mkt"] < 0) & (d["Close"] < d["ORL"]) & (d["Close"] < d["VWAP"])
            & (d["EMA9"] < d["EMA20"]) & (d["RSI"] < p.rsi_short) & vol)
    if not p.allow_short:
        sell[:] = False
    out = pd.Series(0, index=d.index, dtype=int)
    out[buy.fillna(False)] = 1
    out[sell.fillna(False) & ~buy.fillna(False)] = -1
    return out


def plan(row: pd.Series, side: int, p: IntraParams = IntraParams()) -> dict:
    """Entry/stop/target from a signal bar (entry ≈ its close)."""
    entry = float(row["Close"])
    if side > 0:
        stop = max(float(row["VWAP"]), float(row["Low"]))
        stop = min(stop, entry * (1 - p.min_risk_pct / 100))
    else:
        stop = min(float(row["VWAP"]), float(row["High"]))
        stop = max(stop, entry * (1 + p.min_risk_pct / 100))
    risk = abs(entry - stop)
    return {"side": "BUY" if side > 0 else "SELL", "entry": entry, "stop": stop,
            "target1": entry + side * risk, "target2": entry + side * p.reward * risk,
            "risk": risk, "risk_pct": risk / entry * 100}


# --------------------------------------------------------------- backtest

def backtest(d: pd.DataFrame, p: IntraParams = IntraParams(), symbol: str = "") -> pd.DataFrame:
    sig = signals(d, p)
    trades = []
    for day, g in d.groupby("Day"):
        s = sig.loc[g.index]
        done = set()
        k = 0
        idx = g.index
        while k < len(g) - 1:
            side = int(s.iloc[k])
            if side == 0 or side in done:
                k += 1
                continue
            done.add(side)
            pl = plan(g.iloc[k], side, p)
            entry = float(g["Open"].iloc[k + 1])
            gap = entry - pl["entry"]
            stop, target = pl["stop"] + gap, pl["target2"] + gap
            risk = abs(entry - stop)
            cur = stop
            outcome, px, j_exit = None, None, None
            for j in range(k + 1, len(g)):
                bar = g.iloc[j]
                if idx[j].time() >= p.exit_time:
                    outcome, px, j_exit = "Time (15:10)", float(bar["Open"]), j
                    break
                hit_stop = bar["Low"] <= cur if side > 0 else bar["High"] >= cur
                hit_tgt = bar["High"] >= target if side > 0 else bar["Low"] <= target
                if hit_stop:
                    px = min(float(bar["Open"]), cur) if side > 0 else max(float(bar["Open"]), cur)
                    outcome = "Breakeven" if (cur - entry) * side >= 0 else "Stop"
                    j_exit = j
                    break
                if hit_tgt:
                    px = max(float(bar["Open"]), target) if side > 0 else min(float(bar["Open"]), target)
                    outcome, j_exit = "Target", j
                    break
                if p.breakeven_r:
                    fav = bar["High"] - entry if side > 0 else entry - bar["Low"]
                    if fav >= p.breakeven_r * risk:
                        cur = max(cur, entry) if side > 0 else min(cur, entry)
            if px is None:
                j_exit = len(g) - 1
                px, outcome = float(g["Close"].iloc[-1]), "Day end"
            gross = side * (px / entry - 1) * 100
            trades.append({"Symbol": symbol, "Day": day.date(), "Side": "BUY" if side > 0 else "SELL",
                           "Signal time": idx[k].strftime("%H:%M"), "Entry": entry, "Stop": stop,
                           "Target": target, "Exit time": idx[j_exit].strftime("%H:%M"),
                           "Exit": px, "Outcome": outcome, "Gross %": gross,
                           "Net %": gross - p.cost_pct,
                           "R": (side * (px - entry) - p.cost_pct / 100 * entry) / risk if risk else 0.0})
            k = j_exit + 1
    return pd.DataFrame(trades)


def stats(t: pd.DataFrame) -> dict:
    if t is None or t.empty:
        return {"n": 0}
    win = t["Net %"] > 0
    gl = -t.loc[~win, "Net %"].sum()
    days = t["Day"].nunique()
    return {"n": int(len(t)), "days": int(days),
            "win_rate": float(win.mean() * 100),
            "avg_net_pct": float(t["Net %"].mean()),
            "avg_R": float(t["R"].mean()),
            "profit_factor": float(t.loc[win, "Net %"].sum() / gl) if gl > 0 else None,
            "trades_per_day": float(len(t) / days) if days else 0.0}


# ------------------------------------------------------------------- live

def evaluate(df5: pd.DataFrame, nifty5: pd.DataFrame | None, p: IntraParams = IntraParams()) -> dict:
    """Everything the Intraday page needs for one stock, on today's data."""
    d = add_market(features(df5), nifty5)
    today = d[d["Day"] == d["Day"].iloc[-1]]
    last = today.iloc[-1]
    sig = signals(d, p).loc[today.index]
    fired = sig[sig != 0]
    first = {}
    for side in (1, -1):
        hits = fired[fired == side]
        if len(hits):
            first[side] = hits.index[0]
    sig_info = None
    if first:
        t0 = min(first.values())
        side = 1 if first.get(1) == t0 else -1
        sig_info = {"time": t0, **plan(today.loc[t0], side, p)}
    return {"data": d, "today": today, "last": last,
            "checklist": checklist(last, p), "signal": sig_info,
            "levels": {"Opening range high": last["ORH"], "Opening range low": last["ORL"],
                       "VWAP": last["VWAP"], "Prev day high": last["PDH"],
                       "Prev day low": last["PDL"], "Prev day close": last["PDC"]}}


def params_dict(p: IntraParams) -> dict:
    d = asdict(p)
    d["last_entry"] = p.last_entry.strftime("%H:%M")
    d["exit_time"] = p.exit_time.strftime("%H:%M")
    return d


GRID = [replace(IntraParams(), reward=r, breakeven_r=b, allow_short=s)
        for r in (1.5, 2.0) for b in (0.0, 1.0) for s in (True, False)]
