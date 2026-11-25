"""Pro engine: high-quality long setups, scored, with realistic costs.

Design goals
- Trade WITH the market: only take longs when NIFTY is not in a downtrend.
- Trade leaders: stock must be outperforming NIFTY (relative strength).
- Fewer, better trades: a setup must pass hard filters, then gets a 0-100
  quality score. Live confidence comes from how setups with a similar score
  actually performed across ~100 stocks and ~10 years (pro_stats.json).
- No look-ahead: signal at the close, entry at the next open.
- Costs included: brokerage + STT + exchange + GST + stamp + slippage.

Long-only on purpose: shorting in the Indian cash market is intraday only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import analysis as A

STATS_FILE = Path(__file__).with_name("pro_stats.json")
BUCKETS = [(0, 50), (50, 65), (65, 80), (80, 101)]


@dataclass
class ProParams:
    atr_stop: float = 1.5        # initial stop = entry - atr_stop × ATR
    reward: float = 2.0          # target = reward × risk
    max_hold: int = 25           # time exit (trading days)
    trail_after_r: float = 1.0   # once +1R, move stop to breakeven
    cost_pct: float = 0.30       # round-trip costs + slippage, % of entry
    use_breakout: bool = True    # include breakout setups


# ------------------------------------------------------------ features

def regime(nifty: pd.DataFrame) -> pd.Series:
    """+1 bull, 0 neutral, -1 bear for each NIFTY bar."""
    c = nifty["Close"]
    s50, s200 = A.sma(c, 50), A.sma(c, 200)
    bull = (c > s200) & (s50 > s200)
    bear = (c < s200) & (s50 < s200)
    out = pd.Series(0, index=nifty.index, dtype=int)
    out[bull] = 1
    out[bear] = -1
    return out.where(s200.notna(), 0)


def features(df: pd.DataFrame, nifty: pd.DataFrame) -> pd.DataFrame:
    d = A.add_indicators(df)
    n = nifty["Close"].reindex(d.index).ffill()
    d["Regime"] = regime(nifty).reindex(d.index).ffill().fillna(0)
    d["RS63"] = (d["Close"].pct_change(63) - n.pct_change(63)) * 100
    d["SMA200_up"] = d["SMA200"] > d["SMA200"].shift(20)
    d["Hi50"] = d["High"].rolling(50).max().shift()
    d["Hi120"] = d["High"].rolling(120).max().shift()
    rng = (d["High"] - d["Low"]).replace(0, np.nan)
    d["ClosePos"] = (d["Close"] - d["Low"]) / rng          # 1 = closed at high
    d["VolR"] = d["Volume"] / d["VolAvg20"]
    # room to the 120-day high, in ATRs (large if already at new highs)
    room = (d["Hi120"] - d["Close"]) / d["ATR"]
    d["RoomATR"] = room.where(d["Close"] < d["Hi120"] * 0.995, 10.0)
    return d


# ------------------------------------------------------------- setups

def _cross_up(a: pd.Series, level) -> pd.Series:
    return (a > level) & (a.shift() <= level)


def setups(d: pd.DataFrame, use_breakout: bool = True) -> pd.Series:
    """Name of the setup that fired on each bar ('' if none).
    Hard filters every setup must pass: market not bearish, stock above its
    rising 200-DMA, and outperforming NIFTY over 3 months."""
    base = (d["Regime"] >= 0) & (d["Close"] > d["SMA200"]) & d["SMA200_up"] & (d["RS63"] > 0)

    pullback = (base & (d["SMA50"] > d["SMA200"])
                & _cross_up(d["RSI"], 45)
                & (d["RSI"].rolling(5).min() < 42)        # it actually dipped
                & (d["Close"] > d["SMA50"] * 0.97))       # dip held near 50-DMA

    breakout = (base & (d["Close"] > d["Hi50"])
                & (d["VolR"] > 1.5)
                & (d["ClosePos"] > 0.6)
                & (d["RSI"] < 78))

    out = pd.Series("", index=d.index, dtype=object)
    out[pullback.fillna(False)] = "Pullback"
    if use_breakout:
        out[breakout.fillna(False) & (out == "")] = "Breakout"
    return out


def score(d: pd.DataFrame) -> pd.Series:
    """0-100 quality score from six checks."""
    parts = {
        "market": d["Regime"].map({1: 1.0, 0: 0.4, -1: 0.0}).fillna(0),
        "rel_strength": (d["RS63"] / 15).clip(0, 1),
        "trend": ((d["Close"] > d["SMA50"]).astype(float) * 0.5
                  + (d["SMA50"] > d["SMA200"]).astype(float) * 0.3
                  + d["SMA200_up"].astype(float) * 0.2),
        "volume": ((d["VolR"] - 0.8) / 1.2).clip(0, 1),
        "room": (d["RoomATR"] / 6).clip(0, 1),
        "not_stretched": (1 - ((d["Close"] / d["SMA20"] - 1) * 100 - 3).clip(0, 7) / 7),
    }
    w = {"market": 25, "rel_strength": 20, "trend": 20, "volume": 10,
         "room": 15, "not_stretched": 10}
    return sum(parts[k].fillna(0) * w[k] for k in w).round(0)


SCORE_PARTS = ["Market trend (NIFTY)", "Beating NIFTY (3 months)", "Stock trend",
               "Volume", "Room to resistance", "Not over-extended"]


def score_breakdown(row: pd.Series) -> list[tuple[str, float, float]]:
    """(label, points, max) for one bar, for display."""
    vals = [
        ({1: 1.0, 0: 0.4, -1: 0.0}.get(int(row["Regime"]), 0), 25),
        (min(max(row["RS63"] / 15, 0), 1) if pd.notna(row["RS63"]) else 0, 20),
        ((row["Close"] > row["SMA50"]) * 0.5 + (row["SMA50"] > row["SMA200"]) * 0.3
         + bool(row["SMA200_up"]) * 0.2, 20),
        (min(max((row["VolR"] - 0.8) / 1.2, 0), 1) if pd.notna(row["VolR"]) else 0, 10),
        (min(max(row["RoomATR"] / 6, 0), 1) if pd.notna(row["RoomATR"]) else 0, 15),
        (1 - min(max((row["Close"] / row["SMA20"] - 1) * 100 - 3, 0), 7) / 7, 10),
    ]
    return [(lbl, round(v * m, 1), m) for lbl, (v, m) in zip(SCORE_PARTS, vals)]


# ----------------------------------------------------------- simulate

def simulate(d: pd.DataFrame, p: ProParams = ProParams(), symbol: str = "") -> pd.DataFrame:
    """Backtest pro setups on one stock, one position at a time."""
    st_ = setups(d, p.use_breakout)
    sc = score(d)
    o, h, l, c = (d[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    atr = d["ATR"].to_numpy()
    lo10 = d["Low"].rolling(10).min().to_numpy()
    idx, n = d.index, len(d)
    trades, i = [], 0
    names = st_.to_numpy()
    while i < n - 1:
        if not names[i] or np.isnan(atr[i]):
            i += 1
            continue
        entry = o[i + 1]
        stop = entry - p.atr_stop * atr[i]
        # use the recent swing low if it gives a tighter but sane stop
        if not np.isnan(lo10[i]) and entry - atr[i] > lo10[i] > stop:
            stop = lo10[i] - 0.1 * atr[i]
        risk = entry - stop
        if risk <= 0:
            i += 1
            continue
        target = entry + p.reward * risk
        cur_stop, outcome, exit_px, j_exit = stop, None, None, None
        for j in range(i + 1, min(i + 1 + p.max_hold, n)):
            if l[j] <= cur_stop:
                exit_px = min(o[j], cur_stop)
                outcome = "Breakeven" if cur_stop >= entry else "Stop"
                j_exit = j
                break
            if h[j] >= target:
                exit_px, outcome, j_exit = max(o[j], target), "Target", j
                break
            if p.trail_after_r and h[j] >= entry + p.trail_after_r * risk:
                cur_stop = max(cur_stop, entry)
        if exit_px is None:
            j_exit = min(i + p.max_hold, n - 1)
            exit_px = c[j_exit]
            outcome = "Time" if j_exit < n - 1 else "Open"
        gross = (exit_px / entry - 1) * 100
        net = gross - p.cost_pct
        trades.append({
            "Symbol": symbol, "Setup": names[i], "Score": float(sc.iloc[i]),
            "Signal date": idx[i], "Entry date": idx[i + 1],
            "Entry": entry, "Stop": stop, "Target": target,
            "Exit date": idx[j_exit], "Exit": exit_px, "Outcome": outcome,
            "Gross %": gross, "Net %": net,
            "R": (exit_px - entry) / risk - p.cost_pct / 100 * entry / risk,
            "Days": j_exit - i,
        })
        i = j_exit + 1
    return pd.DataFrame(trades)


def stats(trades: pd.DataFrame) -> dict:
    t = trades[trades["Outcome"] != "Open"] if not trades.empty else trades
    if t.empty:
        return {"n": 0}
    win = t["Net %"] > 0
    gl = -t.loc[~win, "Net %"].sum()
    return {
        "n": int(len(t)),
        "win_rate": float(win.mean() * 100),
        "avg_net_pct": float(t["Net %"].mean()),
        "avg_R": float(t["R"].mean()),
        "profit_factor": float(t.loc[win, "Net %"].sum() / gl) if gl > 0 else None,
        "avg_days": float(t["Days"].mean()),
    }


def bucket_of(s: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= s < hi:
            return f"{lo}-{min(hi, 100)}"
    return "0-50"


def by_bucket(trades: pd.DataFrame) -> dict:
    out = {}
    if trades.empty:
        return out
    for setup in sorted(trades["Setup"].unique()) + ["All"]:
        t = trades if setup == "All" else trades[trades["Setup"] == setup]
        out[setup] = {}
        for lo, hi in BUCKETS:
            key = f"{lo}-{min(hi, 100)}"
            out[setup][key] = stats(t[(t["Score"] >= lo) & (t["Score"] < hi)])
    return out


def best_threshold(trades: pd.DataFrame, min_trades: int = 60) -> float:
    """Minimum score that maximises TOTAL profit (sum of R) while leaving
    enough trades to be meaningful. Chosen on in-sample data only.
    Maximising total R (not average R) avoids overfitting to a handful of
    very high-score trades."""
    best, best_total = 0.0, -1e9
    for th in range(0, 90, 5):
        t = trades[trades["Score"] >= th]
        s = stats(t)
        if s["n"] >= min_trades:
            total = s["avg_R"] * s["n"]
            if total > best_total + 1e-9:
                best, best_total = float(th), total
    return best


# ------------------------------------------------------------- live use

def load_stats() -> dict | None:
    try:
        return json.loads(STATS_FILE.read_text())
    except Exception:
        return None


def confidence(stats_json: dict | None, setup: str, sc: float) -> dict | None:
    """Historical result of similar setups (out-of-sample first)."""
    if not stats_json:
        return None
    key = bucket_of(sc)
    for part in ("out_of_sample", "in_sample"):
        s = stats_json.get(part, {}).get("by_bucket", {}).get(setup, {}).get(key)
        if s and s.get("n", 0) >= 20:
            return {**s, "period": part, "bucket": key}
    return None


def evaluate(df: pd.DataFrame, nifty: pd.DataFrame, p: ProParams = ProParams(),
             recent: int = 3, stats_json: dict | None = None) -> dict:
    """Latest pro setup on one stock, with plan and confidence."""
    d = features(df, nifty)
    st_ = setups(d, p.use_breakout)
    sc = score(d)
    last = d.iloc[-1]
    fired = st_.iloc[-recent:]
    fired = fired[fired != ""]
    th = (stats_json or {}).get("threshold", 0)
    res = {"data": d, "score_now": float(sc.iloc[-1]), "regime": int(last["Regime"]),
           "breakdown": score_breakdown(last), "threshold": th, "signal": None}
    if len(fired):
        day = fired.index[-1]
        s_sig = float(sc.loc[day])
        entry = float(last["Close"])
        atr = float(last["ATR"])
        stop = entry - p.atr_stop * atr
        lo10 = float(d["Low"].iloc[-10:].min())
        if entry - atr > lo10 > stop:
            stop = lo10 - 0.1 * atr
        risk = entry - stop
        res["signal"] = {
            "setup": fired.iloc[-1], "date": day, "score": s_sig,
            "passes_threshold": s_sig >= th,
            "entry": entry, "stop": stop, "target1": entry + min(1.0, p.reward) * risk,
            "target2": entry + p.reward * risk, "risk_pct": risk / entry * 100,
            "rules": p,
            "confidence": confidence(stats_json, fired.iloc[-1], s_sig),
        }
    return res


# ------------------------------------------------------------ journal

def track_trade(df: pd.DataFrame, signal_date, stop: float, target: float,
                p: ProParams = ProParams()) -> dict:
    """Follow one live signal with the same rules as the backtest.
    Entry = next open after the signal; stop/target from the signal's plan
    (shifted by the entry gap so risk stays the same)."""
    sd = pd.Timestamp(signal_date)
    after = df[df.index > sd]
    if after.empty:
        return {"Status": "Waiting"}
    entry = float(after["Open"].iloc[0])
    plan_entry = float(df.loc[df.index <= sd, "Close"].iloc[-1])
    gap = entry - plan_entry
    stop, target = stop + gap, target + gap
    risk = entry - stop
    cur_stop, status, exit_px, exit_day = stop, "Open", None, None
    for k, (day, row) in enumerate(after.iterrows()):
        if k >= p.max_hold:
            status, exit_px, exit_day = "Time", float(after["Close"].iloc[k - 1]), after.index[k - 1]
            break
        if row["Low"] <= cur_stop:
            exit_px = min(float(row["Open"]), cur_stop)
            status = "Breakeven" if cur_stop >= entry else "Stop"
            exit_day = day
            break
        if row["High"] >= target:
            status, exit_px, exit_day = "Target", max(float(row["Open"]), target), day
            break
        if p.trail_after_r and row["High"] >= entry + p.trail_after_r * risk:
            cur_stop = max(cur_stop, entry)
    last_px = float(after["Close"].iloc[-1])
    px = exit_px if exit_px is not None else last_px
    net = (px / entry - 1) * 100 - (p.cost_pct if exit_px is not None else 0)
    return {"Status": status, "Entry date": after.index[0], "Entry price": entry,
            "Stop (live)": cur_stop, "Target (live)": target,
            "Exit date": exit_day, "Exit price": exit_px, "Last price": last_px,
            "Net %": net, "R": (px - entry) / risk if risk > 0 else None,
            "Days": min(len(after), p.max_hold)}


def journal_summary(j: pd.DataFrame) -> dict:
    if j is None or j.empty:
        return {"signals": 0, "closed": 0, "open": 0}
    closed = j[~j["Status"].isin(["Open", "Waiting"])]
    out = {"signals": int(len(j)), "closed": int(len(closed)),
           "open": int(j["Status"].isin(["Open", "Waiting"]).sum())}
    if len(closed):
        win = closed["Net %"] > 0
        gl = -closed.loc[~win, "Net %"].sum()
        out.update({"win_rate": float(win.mean() * 100),
                    "avg_net_pct": float(closed["Net %"].mean()),
                    "profit_factor": float(closed.loc[win, "Net %"].sum() / gl) if gl > 0 else None})
    return out


# ---------------------------------------------------------- portfolio

def portfolio(trades: pd.DataFrame, capital: float = 100_000, max_positions: int = 5,
              risk_pct: float = 1.0) -> dict:
    """Replay trades as a real account: at most `max_positions` open at once,
    each sized so hitting the stop loses `risk_pct`% of current equity, and
    never more than equity / max_positions in one stock. Trades are taken in
    signal order; extras are skipped when the account is full.
    Equity is marked on exits (closed trades), so drawdowns between exits
    are understated."""
    if trades.empty:
        return {"trades_taken": 0}
    t = trades[trades["Outcome"] != "Open"].sort_values(["Entry date", "Score"],
                                                        ascending=[True, False])
    equity, open_pos, curve, taken, skipped = capital, [], [], 0, 0
    for _, tr in t.iterrows():
        # close everything that exited before this entry
        still = []
        for pos in open_pos:
            if pos["exit"] <= tr["Entry date"]:
                equity += pos["pnl"]
                curve.append((pos["exit"], equity))
            else:
                still.append(pos)
        open_pos = still
        if len(open_pos) >= max_positions:
            skipped += 1
            continue
        risk_per_share = tr["Entry"] - tr["Stop"]
        if risk_per_share <= 0:
            continue
        qty = min(equity * risk_pct / 100 / risk_per_share,
                  equity / max_positions / tr["Entry"])
        pnl = qty * tr["Entry"] * tr["Net %"] / 100
        open_pos.append({"exit": tr["Exit date"], "pnl": pnl})
        taken += 1
    for pos in sorted(open_pos, key=lambda x: x["exit"]):
        equity += pos["pnl"]
        curve.append((pos["exit"], equity))
    if not curve:
        return {"trades_taken": 0}
    c = pd.Series([v for _, v in curve], index=pd.to_datetime([d for d, _ in curve])).sort_index()
    start = pd.Timestamp(t["Entry date"].min())
    years = max((c.index[-1] - start).days / 365.25, 0.1)
    dd = (c / c.cummax().clip(lower=capital) - 1).min() * 100
    yearly = c.groupby(c.index.year).last()
    prev = pd.Series([capital] + yearly.tolist()[:-1], index=yearly.index)
    return {
        "start_capital": capital, "end_capital": float(c.iloc[-1]),
        "total_return_pct": float((c.iloc[-1] / capital - 1) * 100),
        "cagr_pct": float(((c.iloc[-1] / capital) ** (1 / years) - 1) * 100),
        "max_drawdown_pct": float(min(dd, 0)),
        "trades_taken": taken, "trades_skipped_full": skipped,
        "max_positions": max_positions, "risk_pct": risk_pct,
        "yearly_return_pct": {int(y): float((v / prev[y] - 1) * 100) for y, v in yearly.items()},
        "curve": [(d.strftime("%Y-%m-%d"), round(float(v), 2)) for d, v in c.items()],
    }


def params_dict(p: ProParams) -> dict:
    return asdict(p)


def params_from_stats(stats_json: dict | None) -> ProParams:
    """Use the parameters chosen by the latest research run, if any."""
    if not stats_json or "params" not in stats_json:
        return ProParams()
    known = set(ProParams.__dataclass_fields__)
    return ProParams(**{k: v for k, v in stats_json["params"].items() if k in known})
