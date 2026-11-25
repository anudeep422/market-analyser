import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paytm as PM  # noqa: E402


def bars(last_day="2026-11-24"):
    idx = pd.bdate_range(end=last_day, periods=5)
    return pd.DataFrame({"Open": 100.0, "High": 102.0, "Low": 98.0,
                         "Close": 101.0, "Volume": 1000.0}, index=idx)


def quote(day="2026-11-25", **kw):
    q = {"found": True, "security_id": 1594, "last_price": 1140.5,
         "ohlc": {"open": 1141.8, "high": 1151.9, "low": 1133.7, "close": 1103.4},
         "last_trade_time": day + " 11:10:00"}
    q.update(kw)
    return q


def test_apply_quote_appends_new_day():
    out = PM.apply_quote(bars(), quote())
    assert len(out) == 6
    row = out.iloc[-1]
    assert out.index[-1] == pd.Timestamp("2026-11-25")
    assert (row["Open"], row["High"], row["Low"], row["Close"]) == (1141.8, 1151.9, 1133.7, 1140.5)
    assert row["Volume"] == 1000.0  # carried over when quote has no volume


def test_apply_quote_replaces_same_day():
    out = PM.apply_quote(bars("2026-11-25"), quote(volume_traded=5_000_000))
    assert len(out) == 5
    assert out["Close"].iloc[-1] == 1140.5
    assert out["Volume"].iloc[-1] == 5_000_000


def test_apply_quote_high_low_include_last_price():
    out = PM.apply_quote(bars(), quote(last_price=1160, ohlc={"open": 1141, "high": 1150, "low": 1135}))
    assert out["High"].iloc[-1] == 1160


def test_apply_quote_ignores_old_or_empty():
    df = bars("2026-11-25")
    assert PM.apply_quote(df, None).equals(df)
    assert PM.apply_quote(df, quote(last_price=0)).equals(df)
    out = PM.apply_quote(df, quote(day="2026-11-20"))   # older than history
    assert out.equals(df)


def test_trade_day_epoch_seconds():
    ts = pd.Timestamp("2026-11-25 05:40", tz="UTC").timestamp()  # 11:10 IST
    assert PM._trade_day({"last_trade_time": int(ts)}) == pd.Timestamp("2026-11-25")


def test_pref_for(monkeypatch):
    monkeypatch.setattr(PM, "security_ids", lambda: {"INFY": "1594", "M&M": "2031"})
    assert PM.pref_for("INFY.NS") == "NSE:1594:EQUITY"
    assert PM.pref_for("M&M.NS") == "NSE:2031:EQUITY"
    assert PM.pref_for("^NSEI") == "NSE:13:INDEX"
    assert PM.pref_for("INFY.BO") is None
    assert PM.pref_for("UNKNOWN.NS") is None


def test_token_flow(monkeypatch):
    monkeypatch.setattr(PM, "_secrets", lambda: {"api_key": "k", "api_secret": "s"})

    class Resp:
        status_code = 200
        def json(self):
            return {"access_token": "A", "read_access_token": "R", "public_access_token": "P"}

    seen = {}
    def fake_post(url, json, timeout):
        seen.update(url=url, body=json)
        return Resp()
    monkeypatch.setattr(PM.requests, "post", fake_post)
    PM.logout()
    assert not PM.connected()
    ok, _ = PM.exchange_request_token("REQ")
    assert ok and PM.connected() and PM.token() == "R"
    assert seen["url"].endswith("/accounts/v2/gettoken")
    assert seen["body"] == {"api_key": "k", "api_secret_key": "s", "request_token": "REQ"}
    assert "apiKey=k" in PM.login_url()
    PM.logout()
    assert not PM.connected()


def test_quotes_maps_back_to_tickers(monkeypatch):
    monkeypatch.setattr(PM, "token", lambda: "R")
    monkeypatch.setattr(PM, "security_ids", lambda: {"INFY": "1594"})

    class Resp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": [quote(), {"found": False, "message": "bad"}]}

    calls = []
    def fake_get(url, params, headers, timeout):
        calls.append((params, headers))
        return Resp()
    monkeypatch.setattr(PM.requests, "get", fake_get)
    PM._quotes.clear()
    q = PM.quotes(["INFY.NS", "TCS.BO"])
    assert list(q) == ["INFY.NS"] and q["INFY.NS"]["last_price"] == 1140.5
    assert calls[0][0] == {"mode": "QUOTE", "pref": "NSE:1594:EQUITY"}
    assert calls[0][1] == {"x-jwt-token": "R"}


def test_not_configured_without_secrets(monkeypatch):
    monkeypatch.setattr(PM, "_secrets", lambda: {})
    assert not PM.configured()
