import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis as A  # noqa: E402
import signals as S  # noqa: E402


def frame(close, spread=1.0):
    close = np.asarray(close, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    return pd.DataFrame({"Open": close, "High": close + spread, "Low": close - spread,
                         "Close": close, "Volume": 1e6}, index=idx)


def test_registry_has_strategies():
    assert {"pullback", "breakout", "macd", "ma_cross", "bb_reversal"} <= set(S.STRATEGIES)


@pytest.mark.parametrize("key", list(S.STRATEGIES))
def test_strategy_output_shape(key):
    d = A.add_indicators(A.sample_data())
    sig = S.STRATEGIES[key].fn(d)
    assert len(sig) == len(d)
    assert set(sig.unique()) <= {-1, 0, 1}


def test_backtest_long_hits_target():
    # flat, then a steady rise: a buy on bar 30 must hit its target
    close = [100] * 31 + list(np.linspace(100, 160, 40))
    d = A.add_indicators(frame(close))
    sig = pd.Series(0, index=d.index)
    sig.iloc[30] = 1
    t = S.backtest(d, sig, S.Params(atr_mult=1.5, reward=2))
    assert len(t) == 1
    assert t.iloc[0]["Outcome"] == "Target"
    assert t.iloc[0]["R"] >= 2 - 1e-9  # gaps past target fill at the open


def test_backtest_long_hits_stop_and_short_wins():
    close = [100] * 31 + list(np.linspace(100, 60, 40))
    d = A.add_indicators(frame(close))
    sig = pd.Series(0, index=d.index)
    sig.iloc[30] = 1
    t = S.backtest(d, sig)
    assert t.iloc[0]["Outcome"] == "Stop" and t.iloc[0]["Return %"] < 0
    sig.iloc[30] = -1
    t = S.backtest(d, sig)
    assert t.iloc[0]["Outcome"] == "Target" and t.iloc[0]["Return %"] > 0


def test_backtest_no_shorts():
    close = [100] * 31 + list(np.linspace(100, 60, 40))
    d = A.add_indicators(frame(close))
    sig = pd.Series(0, index=d.index)
    sig.iloc[30] = -1
    assert S.backtest(d, sig, S.Params(allow_short=False)).empty


def test_backtest_one_position_at_a_time():
    d = A.add_indicators(A.sample_data())
    sig = pd.Series(1, index=d.index)
    t = S.backtest(d, sig)
    assert (t["Signal date"].iloc[1:].to_numpy() > t["Exit date"].iloc[:-1].to_numpy()).all()


def test_summary_empty_and_values():
    assert S.summarize(pd.DataFrame())["Trades"] == 0
    t = pd.DataFrame({"Return %": [10, -5, 5], "R": [2, -1, 1], "Days": [3, 2, 4],
                      "Outcome": ["Target", "Stop", "Time"]})
    s = S.summarize(t)
    assert s["Trades"] == 3
    assert s["Win rate %"] == pytest.approx(200 / 3)
    assert s["Profit factor"] == pytest.approx(3)


def test_trade_plan_sides():
    d = A.add_indicators(A.sample_data())
    b = S.trade_plan(d, 1)
    assert b["stop"] < b["entry"] < b["target1"] < b["target2"]
    s = S.trade_plan(d, -1)
    assert s["target2"] < s["target1"] < s["entry"] < s["stop"]


def test_position_size():
    ps = S.position_size(100000, 1, 1000, 980)
    assert ps["qty"] == 50 and ps["max_loss"] == pytest.approx(1000)
    assert S.position_size(10000, 5, 1000, 999)["qty"] == 10  # capped by capital
    assert S.position_size(10000, 1, 100, 100)["qty"] == 0


def test_evaluate_runs():
    ev = S.evaluate(A.sample_data())
    assert len(ev["results"]) == len(S.STRATEGIES)
    assert ev["side"] in (-1, 0, 1)
    assert (ev["plan"] is None) == (ev["side"] == 0)
