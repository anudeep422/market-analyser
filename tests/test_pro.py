import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis as A  # noqa: E402
import pro as P  # noqa: E402


def trend_frame(n=400, start=100, end=200, wiggle=6, seed=0, vol=1e6):
    """Trend + swings + noise, with volume spikes on strong up days."""
    rng = np.random.default_rng(seed)
    base = np.linspace(start, end, n) + np.sin(np.arange(n) / 6) * wiggle
    close = base + rng.normal(0, 0.5, n)
    up = np.r_[0, np.diff(close)] > 0
    high = close + np.where(up, 0.2, 1.5)      # up days close near the high
    low = close - np.where(up, 1.5, 0.2)
    volume = vol * (1 + rng.random(n)) * np.where(up & (rng.random(n) < 0.3), 2.5, 1.0)
    idx = pd.bdate_range("2018-01-01", periods=n)
    return pd.DataFrame({"Open": close - 0.3, "High": high, "Low": low,
                         "Close": close, "Volume": volume}, index=idx)


def test_regime_values():
    up, down = trend_frame(), trend_frame(start=200, end=100)
    assert P.regime(up).iloc[-1] == 1
    assert P.regime(down).iloc[-1] == -1
    assert P.regime(up).iloc[:150].eq(0).all()   # no 200-DMA yet


def test_no_longs_in_bear_market():
    stock = trend_frame(seed=1)
    bear = trend_frame(start=200, end=100, seed=2)
    d = P.features(stock, bear)
    s = P.setups(d)
    assert (s[d["Regime"] < 0] == "").all()


def test_outperformer_gets_setups_and_scores():
    stock = trend_frame(start=100, end=260, wiggle=14, seed=3)
    nifty = trend_frame(start=100, end=130, wiggle=2, seed=4)
    d = P.features(stock, nifty)
    s = P.setups(d)
    assert (s != "").sum() > 0
    sc = P.score(d)
    assert sc.between(0, 100).all()
    fired = sc[s != ""]
    assert fired.mean() > 40


def test_score_breakdown_sums_to_score():
    stock = trend_frame(start=100, end=260, wiggle=14, seed=3)
    nifty = trend_frame(start=100, end=130, wiggle=2, seed=4)
    d = P.features(stock, nifty)
    row = d.iloc[-1]
    total = sum(p for _, p, _ in P.score_breakdown(row))
    assert total == pytest.approx(P.score(d).iloc[-1], abs=1.0)
    assert sum(m for _, _, m in P.score_breakdown(row)) == 100


def test_simulate_costs_and_no_overlap():
    stock = trend_frame(start=100, end=260, wiggle=14, seed=3)
    nifty = trend_frame(start=100, end=130, wiggle=2, seed=4)
    d = P.features(stock, nifty)
    t = P.simulate(d, symbol="X")
    assert not t.empty
    assert np.allclose(t["Net %"], t["Gross %"] - 0.30)
    assert (t["Signal date"].iloc[1:].to_numpy() > t["Exit date"].iloc[:-1].to_numpy()).all()
    assert set(t["Outcome"]) <= {"Target", "Stop", "Breakeven", "Time", "Open"}
    assert (t["Entry"] > t["Stop"]).all() and (t["Target"] > t["Entry"]).all()


def test_breakeven_stop_after_1R():
    # entry, rally to +1.2R, then collapse: must exit at breakeven, not full stop
    n = 260
    close = np.r_[np.linspace(100, 150, 250), [150, 156, 140, 130, 120, 110, 100, 95, 90, 85]]
    idx = pd.bdate_range("2019-01-01", periods=n)
    df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                       "Close": close, "Volume": 1e6}, index=idx)
    d = A.add_indicators(df)
    d["Regime"], d["RS63"], d["SMA200_up"] = 1, 5.0, True
    d["Hi50"], d["Hi120"], d["ClosePos"], d["VolR"], d["RoomATR"] = 0, 0, 1, 2, 10
    # force a single setup on bar 249
    orig = P.setups
    P.setups = lambda dd: pd.Series(["" if i != 249 else "Pullback" for i in range(n)], index=dd.index)
    try:
        t = P.simulate(d)
    finally:
        P.setups = orig
    assert len(t) == 1
    assert t.iloc[0]["Outcome"] in ("Breakeven", "Target")
    assert t.iloc[0]["Gross %"] >= -0.01


def test_stats_and_buckets():
    t = pd.DataFrame({"Setup": ["Pullback"] * 4 + ["Breakout"] * 2,
                      "Score": [40, 55, 70, 85, 70, 90],
                      "Net %": [-1.0, 2.0, 3.0, -0.5, 4.0, -1.0],
                      "R": [-1, 1, 2, -0.3, 2, -1], "Days": [3] * 6,
                      "Outcome": ["Stop", "Target", "Target", "Breakeven", "Target", "Stop"]})
    s = P.stats(t)
    assert s["n"] == 6 and s["win_rate"] == pytest.approx(50)
    assert s["profit_factor"] == pytest.approx(9 / 2.5)
    b = P.by_bucket(t)
    assert b["Pullback"]["65-80"]["n"] == 1 and b["All"]["80-100"]["n"] == 2
    assert P.bucket_of(72) == "65-80" and P.bucket_of(100) == "80-100"


def test_best_threshold_prefers_expectancy():
    rng = np.random.default_rng(0)
    sc = rng.integers(0, 100, 2000)
    r = np.where(sc >= 60, 0.5, -0.2) + rng.normal(0, 0.1, 2000)
    t = pd.DataFrame({"Score": sc, "R": r, "Net %": r, "Days": 5, "Outcome": "Target"})
    assert 55 <= P.best_threshold(t) <= 70


def test_confidence_lookup():
    js = {"threshold": 60, "out_of_sample": {"by_bucket": {"Pullback": {"65-80": {"n": 40, "win_rate": 58, "avg_R": 0.3}}}},
          "in_sample": {"by_bucket": {"Pullback": {"50-65": {"n": 100, "win_rate": 52, "avg_R": 0.1}}}}}
    c = P.confidence(js, "Pullback", 70)
    assert c["period"] == "out_of_sample" and c["win_rate"] == 58
    assert P.confidence(js, "Pullback", 55)["period"] == "in_sample"
    assert P.confidence(js, "Breakout", 70) is None
    assert P.confidence(None, "Pullback", 70) is None


def test_evaluate_runs():
    stock = trend_frame(start=100, end=260, wiggle=14, seed=3)
    nifty = trend_frame(start=100, end=130, wiggle=2, seed=4)
    ev = P.evaluate(stock, nifty, recent=400)
    assert 0 <= ev["score_now"] <= 100
    assert ev["signal"] is not None
    s = ev["signal"]
    assert s["stop"] < s["entry"] < s["target1"] < s["target2"]
