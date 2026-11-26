import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intraday as I  # noqa: E402


def day_bars(day, path, vol=None, tz=True):
    """75 five-minute bars 09:15..15:25 following `path` (len 75)."""
    idx = pd.date_range(f"{day} 09:15", periods=75, freq="5min")
    c = np.asarray(path, float)
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.2,
                       "Low": np.minimum(o, c) - 0.2, "Close": c,
                       "Volume": vol if vol is not None else np.full(75, 1000.0)}, index=idx)
    if tz:
        df.index = df.index.tz_localize("Asia/Kolkata")
    return df


def flat(day, level=100.0):
    return day_bars(day, np.full(75, level) + np.sin(np.arange(75)) * 0.1)


def trend_day(day, start=100.0, end=106.0):
    path = np.r_[np.full(3, start) + [0, 0.3, -0.2],      # opening range ~100
                 np.linspace(start, end, 72)]
    vol = np.full(75, 1000.0)
    vol[3:20] = 3000.0                                      # breakout volume
    return day_bars(day, path, vol)


def test_features_vwap_and_opening_range():
    d = I.features(pd.concat([flat("2026-11-23"), trend_day("2026-11-24")]))
    t = d[d["Day"] == pd.Timestamp("2026-11-24")]
    assert t["ORH"].iloc[0] == pytest.approx(t[t.index.time < time(9, 30)]["High"].max())
    assert (t["VWAP"] <= t["High"].cummax() + 1e-9).all()
    assert t["PDC"].iloc[0] == pytest.approx(flat("2026-11-23")["Close"].iloc[-1])
    assert d.index.tz is None


def test_buy_signal_and_target_on_trend_day():
    stock = pd.concat([flat("2026-11-23"), trend_day("2026-11-24")])
    nifty = pd.concat([flat("2026-11-23", 20000), trend_day("2026-11-24", 20000, 20100)])
    d = I.add_market(I.features(stock), nifty)
    s = I.signals(d)
    buys = s[s == 1]
    assert len(buys) > 0 and buys.index[0].time() >= time(9, 30)
    assert (s != -1).all()
    t = I.backtest(d, I.IntraParams(breakeven_r=0), symbol="X")
    assert len(t) == 1                       # one trade per side per day
    tr = t.iloc[0]
    assert tr["Side"] == "BUY" and tr["Outcome"] == "Target" and tr["Net %"] > 0
    assert tr["Net %"] == pytest.approx(tr["Gross %"] - 0.15)


def test_no_buy_when_nifty_below_vwap():
    stock = pd.concat([flat("2026-11-23"), trend_day("2026-11-24")])
    nifty = pd.concat([flat("2026-11-23", 20000), trend_day("2026-11-24", 20100, 20000)])
    d = I.add_market(I.features(stock), nifty)
    assert (I.signals(d) != 1).all()


def test_time_exit_at_1510():
    path = np.r_[[100, 100.3, 99.8], np.linspace(100, 101.2, 72)]   # slow grind, no target
    vol = np.r_[np.full(3, 1000.0), np.linspace(1000, 5000, 72)]   # rising volume
    stock = pd.concat([flat("2026-11-23"), day_bars("2026-11-24", path, vol)])
    nifty = pd.concat([flat("2026-11-23", 20000), trend_day("2026-11-24", 20000, 20100)])
    d = I.add_market(I.features(stock), nifty)
    t = I.backtest(d, I.IntraParams(reward=10, breakeven_r=0))
    assert len(t) == 1 and t.iloc[0]["Outcome"] == "Time (15:10)"
    assert t.iloc[0]["Exit time"] == "15:10"


def test_no_short_param():
    rev = trend_day("2026-11-24", 106, 100)
    stock = pd.concat([flat("2026-11-23", 106), rev])
    nifty = pd.concat([flat("2026-11-23", 20100), trend_day("2026-11-24", 20100, 20000)])
    d = I.add_market(I.features(stock), nifty)
    assert (I.signals(d) == -1).any()
    assert (I.signals(d, I.IntraParams(allow_short=False)) == 0).all()
    t = I.backtest(d, I.IntraParams(breakeven_r=0))
    assert t.iloc[0]["Side"] == "SELL" and t.iloc[0]["Net %"] > 0
    be = I.backtest(d)                       # with breakeven: never a full loss here
    assert be.iloc[0]["Outcome"] in ("Breakeven", "Target")


def test_plan_min_risk_and_sides():
    row = pd.Series({"Close": 100.0, "VWAP": 99.99, "Low": 99.95, "High": 100.1})
    b = I.plan(row, 1)
    assert b["stop"] == pytest.approx(99.8)            # widened to 0.2%
    assert b["target2"] == pytest.approx(100.4)
    s = I.plan(row, -1)
    assert s["stop"] > 100 and s["target2"] < 100


def test_checklist_and_evaluate():
    stock = pd.concat([flat("2026-11-23"), trend_day("2026-11-24")])
    nifty = pd.concat([flat("2026-11-23", 20000), trend_day("2026-11-24", 20000, 20100)])
    ev = I.evaluate(stock.iloc[:-60], nifty.iloc[:-60])     # mid-morning view
    assert ev["signal"] and ev["signal"]["side"] == "BUY"
    assert set(ev["checklist"]) == {"BUY", "SELL"}
    assert ev["levels"]["Opening range high"] > 0


def test_stats():
    t = pd.DataFrame({"Day": ["a", "a", "b"], "Net %": [1.0, -0.5, 0.5], "R": [2, -1, 1]})
    s = I.stats(t)
    assert s["n"] == 3 and s["days"] == 2 and s["profit_factor"] == pytest.approx(3)
    assert I.stats(pd.DataFrame())["n"] == 0
    assert len(I.GRID) == 8
