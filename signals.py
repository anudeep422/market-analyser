"""Buy/sell signal plugins, trade plans and a backtester.

Add a strategy by writing a function that takes an indicator DataFrame
(from analysis.add_indicators) and returns a Series of +1 (buy), -1 (sell)
or 0 for every bar, then decorating it with @strategy(...). It then shows
up automatically in the app, the scanner and the backtest.

Signals are produced at the close of a bar and acted on at the next open,
so there is no look-ahead in the backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

import analysis as A

# ---------------------------------------------------------------- registry


@dataclass
class Strategy:
    key: str
    name: str
    description: str
    fn: Callable[[pd.DataFrame], pd.Series]


STRATEGIES: dict[str, Strategy] = {}


def strategy(key: str, name: str, description: str):
    def wrap(fn):
        STRATEGIES[key] = Strategy(key, name, description, fn)
        return fn
    return wrap


def _cross_up(a: pd.Series, b) -> pd.Series:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a > b) & (a.shift() <= b.shift())


def _cross_down(a: pd.Series, b) -> pd.Series:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a < b) & (a.shift() >= b.shift())


def _combine(buy: pd.Series, sell: pd.Series) -> pd.Series:
    out = pd.Series(0, index=buy.index, dtype=int)
    out[buy.fillna(False)] = 1
    out[sell.fillna(False) & ~buy.fillna(False)] = -1
    return out


# -------------------------------------------------------------- strategies

@strategy("pullback", "Trend pullback",
          "Buy when an uptrending stock (price > 50-DMA > 200-DMA) dips and RSI "
          "turns back up through 40. Sell when a downtrending stock bounces and "
          "RSI turns back down through 60.")
def trend_pullback(d: pd.DataFrame) -> pd.Series:
    up = (d["Close"] > d["SMA200"]) & (d["SMA50"] > d["SMA200"])
    dn = (d["Close"] < d["SMA200"]) & (d["SMA50"] < d["SMA200"])
    return _combine(up & _cross_up(d["RSI"], 40), dn & _cross_down(d["RSI"], 60))


@strategy("breakout", "20-day breakout",
          "Buy when price closes above its highest high of the previous 20 days "
          "on above-average volume. Sell when it closes below the 20-day low on "
          "above-average volume.")
def breakout(d: pd.DataFrame) -> pd.Series:
    hi20 = d["High"].rolling(20).max().shift()
    lo20 = d["Low"].rolling(20).min().shift()
    vol = d["Volume"] > 1.3 * d["VolAvg20"]
    return _combine((d["Close"] > hi20) & vol, (d["Close"] < lo20) & vol)


@strategy("macd", "MACD crossover with trend",
          "Buy when MACD crosses above its signal line while price is above the "
          "200-DMA. Sell when it crosses below while price is under the 200-DMA.")
def macd_trend(d: pd.DataFrame) -> pd.Series:
    return _combine(_cross_up(d["MACD"], d["Signal"]) & (d["Close"] > d["SMA200"]),
                    _cross_down(d["MACD"], d["Signal"]) & (d["Close"] < d["SMA200"]))


@strategy("ma_cross", "20/50 moving-average cross",
          "Buy when the 20-day average crosses above the 50-day. "
          "Sell when it crosses below.")
def ma_cross(d: pd.DataFrame) -> pd.Series:
    return _combine(_cross_up(d["SMA20"], d["SMA50"]), _cross_down(d["SMA20"], d["SMA50"]))


@strategy("bb_reversal", "Bollinger reversal",
          "Buy when price closes back inside the lower Bollinger band with RSI "
          "below 35 (oversold bounce). Sell when it closes back inside the upper "
          "band with RSI above 65.")
def bb_reversal(d: pd.DataFrame) -> pd.Series:
    back_in_low = (d["Close"] > d["BB_Lower"]) & (d["Close"].shift() < d["BB_Lower"].shift())
    back_in_up = (d["Close"] < d["BB_Upper"]) & (d["Close"].shift() > d["BB_Upper"].shift())
    return _combine(back_in_low & (d["RSI"] < 35), back_in_up & (d["RSI"] > 65))


# ------------------------------------------------------------------ plans

@dataclass
class Params:
    atr_mult: float = 1.5      # stop distance in ATRs
    reward: float = 2.0        # target = reward × risk
    max_hold: int = 20         # exit after this many days if neither hit
    allow_short: bool = True   # backtest sell signals as short trades


def trade_plan(d: pd.DataFrame, side: int, p: Params = Params()) -> dict:
    """Entry, stop-loss and targets for acting on the latest bar."""
    last = d.iloc[-1]
    entry = float(last["Close"])
    atr = float(last["ATR"])
    risk = p.atr_mult * atr
    # tighten/loosen the stop to the nearest swing level if it is close by
    sw = A.swing_levels(d)
    if side > 0:
        stop = entry - risk
        sup = [x for x, _ in sw["support"] if entry - 2.5 * atr < x < entry]
        if sup:
            stop = min(stop, sup[0] - 0.25 * atr)
        r = entry - stop
        t1, t2 = entry + r, entry + p.reward * r
    else:
        stop = entry + risk
        res = [x for x, _ in sw["resistance"] if entry < x < entry + 2.5 * atr]
        if res:
            stop = max(stop, res[0] + 0.25 * atr)
        r = stop - entry
        t1, t2 = entry - r, entry - p.reward * r
    return {"side": "BUY" if side > 0 else "SELL", "entry": entry, "stop": stop,
            "target1": t1, "target2": t2, "risk": r,
            "risk_pct": r / entry * 100, "rr": p.reward}


def position_size(capital: float, risk_pct: float, entry: float, stop: float) -> dict:
    """Shares to buy so that hitting the stop loses only risk_pct of capital."""
    per_share = abs(entry - stop)
    if per_share <= 0 or entry <= 0:
        return {"qty": 0, "value": 0.0, "max_loss": 0.0}
    budget = capital * risk_pct / 100
    qty = int(min(budget // per_share, capital // entry))
    return {"qty": qty, "value": qty * entry, "max_loss": qty * per_share}


# --------------------------------------------------------------- backtest

def backtest(d: pd.DataFrame, sig: pd.Series, p: Params = Params()) -> pd.DataFrame:
    """Simulate one position at a time. Entry at next open; stop and target
    from ATR at the signal bar. If stop and target fall in the same bar the
    stop is assumed first (conservative)."""
    o, h, l, c = (d[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    atr = d["ATR"].to_numpy()
    s = sig.to_numpy()
    idx = d.index
    trades = []
    i, n = 0, len(d)
    while i < n - 1:
        side = s[i]
        if side == 0 or np.isnan(atr[i]) or (side < 0 and not p.allow_short):
            i += 1
            continue
        entry = o[i + 1]
        risk = p.atr_mult * atr[i]
        stop = entry - side * risk
        target = entry + side * p.reward * risk
        exit_px, exit_j, outcome = None, None, None
        for j in range(i + 1, min(i + 1 + p.max_hold, n)):
            hit_stop = l[j] <= stop if side > 0 else h[j] >= stop
            hit_tgt = h[j] >= target if side > 0 else l[j] <= target
            if hit_stop:
                # a gap through the stop fills at the open
                exit_px = min(o[j], stop) if side > 0 else max(o[j], stop)
                exit_j, outcome = j, "Stop"
                break
            if hit_tgt:
                exit_px = max(o[j], target) if side > 0 else min(o[j], target)
                exit_j, outcome = j, "Target"
                break
        if exit_px is None:
            exit_j = min(i + p.max_hold, n - 1)
            exit_px, outcome = c[exit_j], ("Time" if exit_j < n - 1 else "Open")
        ret = side * (exit_px / entry - 1) * 100
        trades.append({"Signal date": idx[i], "Side": "BUY" if side > 0 else "SELL",
                       "Entry": entry, "Stop": stop, "Target": target,
                       "Exit date": idx[exit_j], "Exit": exit_px, "Outcome": outcome,
                       "Return %": ret, "R": side * (exit_px - entry) / risk,
                       "Days": exit_j - i})
        i = exit_j + 1
    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame) -> dict:
    closed = trades[trades["Outcome"] != "Open"] if not trades.empty else trades
    if closed.empty:
        return {"Trades": 0, "Win rate %": None, "Avg return %": None,
                "Total return %": None, "Profit factor": None, "Avg R": None,
                "Max drawdown %": None, "Avg days": None}
    wins = closed[closed["Return %"] > 0]
    losses = closed[closed["Return %"] <= 0]
    gross_loss = -losses["Return %"].sum()
    equity = (1 + closed["Return %"] / 100).cumprod()
    dd = (equity / equity.cummax() - 1).min() * 100
    return {
        "Trades": len(closed),
        "Win rate %": len(wins) / len(closed) * 100,
        "Avg return %": closed["Return %"].mean(),
        "Total return %": (equity.iloc[-1] - 1) * 100,
        "Profit factor": (wins["Return %"].sum() / gross_loss) if gross_loss > 0 else None,
        "Avg R": closed["R"].mean(),
        "Max drawdown %": dd,
        "Avg days": closed["Days"].mean(),
    }


# ---------------------------------------------------------- current status

def evaluate(df: pd.DataFrame, p: Params = Params(), recent: int = 3) -> dict:
    """Run every strategy on one stock.

    Returns per-strategy signals, backtest stats and, if any strategy fired
    in the last `recent` bars, a trade plan. The overall call weighs each
    fresh signal by that strategy's historical profit factor on this stock,
    so strategies that never worked here count for less.
    """
    d = A.add_indicators(df) if "RSI" not in df.columns else df
    results = []
    for st in STRATEGIES.values():
        sig = st.fn(d).fillna(0).astype(int)
        trades = backtest(d, sig, p)
        stats = summarize(trades)
        tail = sig.iloc[-recent:]
        nz = tail[tail != 0]
        fresh = int(nz.iloc[-1]) if len(nz) else 0
        fresh_date = nz.index[-1] if len(nz) else None
        results.append({"strategy": st, "signal": sig, "trades": trades,
                        "stats": stats, "fresh": fresh, "fresh_date": fresh_date})

    vote = 0.0
    for r in results:
        if r["fresh"]:
            pf = r["stats"]["Profit factor"]
            weight = 0.5 if pf is None else max(0.0, min(pf, 3.0))
            vote += r["fresh"] * weight
    if vote > 0.25:
        side = 1
    elif vote < -0.25:
        side = -1
    else:
        side = 0
    plan = trade_plan(d, side, p) if side else None
    return {"results": results, "vote": vote, "side": side, "plan": plan, "data": d}
