import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis as A  # noqa: E402


def test_classic_pivot_textbook():
    lv = A.pivot_levels(110, 90, 100)
    assert lv["Pivot"] == pytest.approx(100)
    assert lv["R1"] == pytest.approx(110)
    assert lv["S1"] == pytest.approx(90)
    assert lv["R2"] == pytest.approx(120)
    assert lv["S2"] == pytest.approx(80)
    assert lv["R3"] == pytest.approx(130)
    assert lv["S3"] == pytest.approx(70)


@pytest.mark.parametrize("method", ["classic", "fibonacci", "camarilla"])
def test_pivot_order(method):
    lv = A.pivot_levels(1132, 1100.4, 1103.4, method)
    vals = [lv[k] for k in ("R3", "R2", "R1", "S1", "S2", "S3")]
    assert vals == sorted(vals, reverse=True)


def test_pivot_bad_method():
    with pytest.raises(ValueError):
        A.pivot_levels(1, 1, 1, "magic")


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert A.rsi(up).iloc[-1] == pytest.approx(100)
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert A.rsi(down).iloc[-1] == pytest.approx(0)
    df = A.sample_data()
    r = A.rsi(df["Close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()
    assert A.rsi(df["Close"]).iloc[:13].isna().all()


def test_rsi_flat_is_50():
    assert A.rsi(pd.Series([100.0] * 40)).iloc[-1] == pytest.approx(50)


def test_macd_hist():
    m = A.macd(A.sample_data()["Close"]).dropna()
    assert np.allclose(m["Hist"], m["MACD"] - m["Signal"])


def test_indicators_columns():
    d = A.add_indicators(A.sample_data())
    for c in ["SMA20", "SMA50", "SMA200", "RSI", "MACD", "Signal", "BB_Upper", "ATR"]:
        assert c in d.columns
    assert not np.isnan(d["SMA200"].iloc[-1])


def test_signal_uptrend_and_downtrend():
    n = 300
    idx = pd.bdate_range("2025-01-01", periods=n)
    up = pd.Series(np.linspace(100, 300, n), index=idx)
    noise = np.sin(np.arange(n)) * 0.5
    df_up = pd.DataFrame({"Open": up, "High": up + 1 + noise, "Low": up - 1,
                          "Close": up + noise, "Volume": 1e6}, index=idx)
    assert A.technical_signal(df_up)["score"] > 0

    dn = up[::-1].to_numpy()
    df_dn = pd.DataFrame({"Open": dn, "High": dn + 1, "Low": dn - 1 + noise,
                          "Close": dn + noise, "Volume": 1e6}, index=idx)
    assert A.technical_signal(df_dn)["score"] < 0


def test_signal_short_history():
    sig = A.technical_signal(A.sample_data(days=10))
    assert sig["label"] == "Not enough data"


def test_swing_levels_sides():
    df = A.sample_data()
    lv = A.swing_levels(df)
    last = df["Close"].iloc[-1]
    assert all(p < last for p, _ in lv["support"])
    assert all(p > last for p, _ in lv["resistance"])


def test_snapshot_keys():
    s = A.snapshot(A.sample_data())
    assert s["S1"] < s["Pivot"] < s["R1"]
    assert s["52W Low"] <= s["Close"] <= s["52W High"]
    assert -100 <= s["Score"] <= 100


def test_returns_periods():
    r = A.returns(A.sample_data())
    assert set(r) == {"1 week", "1 month", "3 months", "6 months", "1 year"}
    assert all(v is not None for v in r.values())


def test_report_downtrend_good_business():
    n = 300
    idx = pd.bdate_range("2025-01-01", periods=n)
    dn = np.linspace(300, 100, n) + np.sin(np.arange(n)) * 0.5
    df = pd.DataFrame({"Open": dn, "High": dn + 1, "Low": dn - 1,
                       "Close": dn, "Volume": 1e6}, index=idx)
    fund = {"Name": "TestCo", "P/E (TTM)": 14, "ROE %": 30, "Debt / Equity": 10}
    rep = A.stock_report(df, fund)
    assert rep["tech_view"] == "bearish"
    assert rep["fund_view"] == "strong"
    assert rep["verdict"] == "Good business, weak chart"
    assert "TestCo" in rep["headline"]
    titles = [t for t, _ in rep["sections"]]
    assert titles[0] == "Performance" and titles[-1] == "Overall view"
    assert "Fundamentals" in titles


def test_report_without_fundamentals():
    rep = A.stock_report(A.sample_data())
    assert rep["fund_view"] is None
    assert "Fundamentals" not in [t for t, _ in rep["sections"]]
    assert rep["watch"]


def test_report_short_history():
    rep = A.stock_report(A.sample_data(days=40))
    assert rep["verdict"]
