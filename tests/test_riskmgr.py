import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import riskmgr as R  # noqa: E402

TODAY = date(2026, 11, 30)
GOOD = {"close": 1200, "sma50": 1150, "sma200": 1100, "nifty_regime": 1,
        "pro_score": 75, "days_to_results": 40}


def verdict(**kw):
    args = dict(rules=R.RiskRules(), journal=R.empty_journal(), side="BUY", entry=1000.0,
                stop=980.0, target=1040.0, market=GOOD, today=TODAY)
    args.update(kw)
    return R.check_trade(**args)


def failed(res):
    return [c["rule"] for c in res["checks"] if c["ok"] is False]


def test_good_trade_allowed_and_sized():
    res = verdict()
    assert res["verdict"] == "ALLOWED", failed(res)
    assert res["size"]["qty"] == 50            # ₹1,000 risk / ₹20 per share
    assert res["size"]["max_loss"] == pytest.approx(1000)


def test_no_stop_blocks():
    assert verdict(stop=None)["verdict"] == "BLOCKED"
    assert verdict(stop=1010.0)["verdict"] == "BLOCKED"   # stop above entry on a buy


def test_too_many_shares_blocks():
    res = verdict(qty=80)
    assert res["verdict"] == "BLOCKED"
    assert any("Max loss" in r for r in failed(res))


def test_downtrend_stock_and_market_block():
    assert verdict(market={**GOOD, "close": 1050})["verdict"] == "BLOCKED"
    assert verdict(market={**GOOD, "nifty_regime": -1})["verdict"] == "BLOCKED"
    rules = R.RiskRules(require_trend=False, require_market=False)
    assert verdict(rules=rules, market={**GOOD, "close": 1050, "nifty_regime": -1})["verdict"] == "ALLOWED"


def test_results_soon_blocks():
    assert verdict(market={**GOOD, "days_to_results": 2})["verdict"] == "BLOCKED"


def test_soft_rules_give_caution():
    assert verdict(target=1010.0)["verdict"] == "CAUTION"          # 1:0.5 reward
    assert verdict(target=None)["verdict"] == "CAUTION"
    assert verdict(market={**GOOD, "pro_score": 40})["verdict"] == "CAUTION"
    assert verdict(market={})["verdict"] == "CAUTION"               # data missing


def test_sell_side():
    res = verdict(side="SELL", entry=1000.0, stop=1020.0, target=960.0)
    assert res["verdict"] == "ALLOWED", failed(res)


def j_with(trades):
    j = R.empty_journal()
    for t in trades:
        j = R.add_trade(j, t["sym"], "BUY", t.get("qty", 10), 100, 95, 110,
                        when=t["opened"])
        if "exit" in t:
            j = R.close_trade(j, int(j["id"].max()), t["exit"], cost_pct=0, when=t["closed"])
    return j


def test_daily_limits():
    now = datetime(2026, 11, 30, 10, 0)
    j = j_with([{"sym": "A", "opened": now, "exit": 95, "closed": now},
                {"sym": "B", "opened": now, "exit": 94, "closed": now}])
    res = verdict(journal=j)
    assert res["verdict"] == "BLOCKED"
    assert any("losses a day" in r for r in failed(res))
    j3 = j_with([{"sym": s, "opened": now} for s in "ABC"])
    assert any("trades a day" in r for r in failed(verdict(journal=j3)))
    # yesterday's trades don't count
    y = datetime(2026, 11, 27, 10, 0)
    jy = j_with([{"sym": s, "opened": y, "exit": 90, "closed": y} for s in "ABC"])
    assert verdict(journal=jy)["verdict"] == "ALLOWED"


def test_monthly_limit_and_open_positions():
    d = datetime(2026, 11, 10, 10, 0)
    j = j_with([{"sym": "A", "qty": 1100, "opened": d, "exit": 95, "closed": d}])   # -5,500 = -5.5%
    res = verdict(journal=j)
    assert any("Month not down" in r for r in failed(res))
    old = datetime(2026, 10, 10, 10, 0)
    j_old = j_with([{"sym": "A", "qty": 1100, "opened": old, "exit": 95, "closed": old}])
    assert verdict(journal=j_old)["verdict"] == "ALLOWED"
    j_open = j_with([{"sym": s, "opened": old} for s in "ABCDE"])
    assert any("open positions" in r for r in failed(verdict(journal=j_open)))


def test_close_trade_pnl_and_summaries():
    j = R.add_trade(R.empty_journal(), "infy", "BUY", 10, 1000, 980, 1040,
                    when=datetime(2026, 11, 2, 10))
    j = R.add_trade(j, "tcs", "SELL", 5, 2500, 2550, 2400, when=datetime(2026, 11, 3, 10))
    j = R.close_trade(j, 1, 1040, cost_pct=0.1, when=datetime(2026, 11, 4, 14))
    j = R.close_trade(j, 2, 2550, cost_pct=0.1, when=datetime(2026, 11, 12, 14))
    r1 = j[j["id"] == 1].iloc[0]
    assert r1["Symbol"] == "INFY" and r1["PnL"] == pytest.approx(400 - 10)
    r2 = j[j["id"] == 2].iloc[0]
    assert r2["PnL"] == pytest.approx(-250 - 12.5)
    o = R.overall(j)
    assert o["closed"] == 2 and o["win_rate"] == 50
    assert o["profit_factor"] == pytest.approx(390 / 262.5)
    w = R.summary(j, "W")
    assert len(w) == 2 and w["Trades"].sum() == 2
    assert len(R.summary(j, "M")) == 1
    with pytest.raises(KeyError):
        R.close_trade(j, 99, 1)


def test_normalize_roundtrip_csv(tmp_path):
    j = R.add_trade(R.empty_journal(), "SBIN", "BUY", 10, 800, 780, 840)
    f = tmp_path / "j.csv"
    j.to_csv(f, index=False)
    back = R.normalize(pd.read_csv(f))
    assert list(back.columns) == R.JOURNAL_COLUMNS
    assert back.iloc[0]["Symbol"] == "SBIN" and pd.notna(back.iloc[0]["Opened"])


def test_rules_from_dict():
    r = R.RiskRules.from_dict({"capital": 50000, "risk_pct": 0.5, "junk": 1})
    assert r.capital == 50000 and r.risk_pct == 0.5
    assert R.RiskRules.from_dict(None) == R.RiskRules()
    assert R.RiskRules.from_dict(r.to_dict()) == r


def test_open_and_close_with_current_time_and_csv_reload(tmp_path):
    j = R.add_trade(R.empty_journal(), "INFY", "BUY", 5, 1000, 980, 1040)   # when=None -> now
    f = tmp_path / "j.csv"
    j.to_csv(f, index=False)
    j = R.normalize(pd.read_csv(f))          # Closed column is all empty after reload
    j = R.close_trade(j, 1, 1010)             # when=None -> now
    r = j.iloc[0]
    assert r["Status"] == "Closed" and pd.notna(r["Closed"]) and r["PnL"] > 0
    assert R.day_stats(j, date.today())["trades_today"] == 1
