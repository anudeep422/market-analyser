"""60-day intraday test of the ORB + VWAP plan on NIFTY 50 stocks.
Runs on GitHub Actions (Yahoo serves ~60 days of 5-minute data).

Rules are chosen on the FIRST half of the days and judged on the SECOND half.
Outputs: intraday_stats.json, reports/intraday_research.md, reports/intraday_trades.csv
"""

from __future__ import annotations

import json
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import intraday as I  # noqa: E402
from scripts.pro_research import NIFTY50  # noqa: E402

REPORTS = ROOT / "reports"


def download_5m(tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for i in range(0, len(tickers), 10):
        part = tickers[i:i + 10]
        raw = pd.DataFrame()
        for attempt in range(3):
            try:
                raw = yf.download(part, period="60d", interval="5m", group_by="ticker",
                                  auto_adjust=False, progress=False, threads=False)
                break
            except Exception as e:  # noqa: BLE001
                print("download error", part, e)
                _time.sleep(5 * (attempt + 1))
        for t in part:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            if len(df) > 500:
                out[t] = df
        _time.sleep(1.5)
    return out


def fmt(s: dict) -> str:
    if not s.get("n"):
        return "no trades"
    pf = s.get("profit_factor")
    return (f"{s['n']} trades over {s['days']} days · win {s['win_rate']:.0f}% · "
            f"avg {s['avg_net_pct']:+.3f}% net · {s['avg_R']:+.2f}R · "
            f"PF {pf:.2f}" if pf else f"{s['n']} trades · win {s['win_rate']:.0f}%")


def main():
    tickers = [f"{s}.NS" for s in NIFTY50]
    nifty = download_5m(["^NSEI"]).get("^NSEI")
    data = download_5m(tickers)
    print("stocks:", len(data), "nifty bars:", 0 if nifty is None else len(nifty))
    if nifty is None or not data:
        raise SystemExit("No intraday data")

    feats = {t: I.add_market(I.features(df), nifty) for t, df in data.items()}
    all_days = sorted({d for f in feats.values() for d in f["Day"].unique()})
    split = all_days[len(all_days) // 2]

    rows, best, best_total, best_trades = [], None, -1e9, pd.DataFrame()
    for p in I.GRID:
        parts = [I.backtest(f, p, t.replace(".NS", "")) for t, f in feats.items()]
        tr = pd.concat([x for x in parts if not x.empty], ignore_index=True) if parts else pd.DataFrame()
        if tr.empty:
            continue
        tr["Day"] = pd.to_datetime(tr["Day"])
        first = tr[tr["Day"] < split]
        s1, s2 = I.stats(first), I.stats(tr[tr["Day"] >= split])
        total = s1["avg_R"] * s1["n"] if s1.get("n", 0) >= 40 else -1e9
        rows.append({**I.params_dict(p), "first_half": fmt(s1), "second_half": fmt(s2)})
        print(I.params_dict(p), "|", fmt(s1), "|", fmt(s2))
        if total > best_total:
            best, best_total, best_trades = p, total, tr
    if best is None:
        raise SystemExit("No trades")

    tr = best_trades
    first, second = tr[tr["Day"] < split], tr[tr["Day"] >= split]
    by_side = {k: I.stats(g) for k, g in second.groupby("Side")}
    tr["Hour"] = tr["Signal time"].str[:2]
    by_hour = {k: I.stats(g) for k, g in tr[tr["Day"] >= split].groupby("Hour")}
    per_day = second.groupby("Day")["Net %"].sum()

    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "stocks": len(data), "days": len(all_days),
           "first_day": str(all_days[0].date()), "split_day": str(pd.Timestamp(split).date()),
           "last_day": str(all_days[-1].date()), "params": I.params_dict(best),
           "first_half": I.stats(first), "second_half": I.stats(second),
           "second_half_by_side": by_side,
           "second_half_green_days_pct": float((per_day > 0).mean() * 100) if len(per_day) else None}
    (ROOT / "intraday_stats.json").write_text(json.dumps(out, indent=2, default=str))
    REPORTS.mkdir(exist_ok=True)
    tr.drop(columns=["Hour"]).to_csv(REPORTS / "intraday_trades.csv", index=False)

    lines = [
        "# Intraday plan — 60-day test",
        "",
        f"Generated {out['generated']} UTC · {len(data)} NIFTY 50 stocks · 5-minute candles · "
        f"{out['first_day']} to {out['last_day']} ({len(all_days)} trading days) · "
        f"costs {best.cost_pct}% per round trip included.",
        "",
        "Rules: opening-range breakout confirmed by VWAP, EMA 9/20, RSI and volume, "
        "with NIFTY on the same side of its VWAP; exit by 15:10.",
        "",
        f"Settings chosen on the first half (before {out['split_day']}), judged on the second half.",
        f"Chosen: target {best.reward}R, breakeven {'at ' + str(best.breakeven_r) + 'R' if best.breakeven_r else 'off'}, "
        f"shorts {'on' if best.allow_short else 'off'}.",
        "",
        "## Result",
        "",
        f"- **Second half (real test):** {fmt(out['second_half'])}",
        f"- First half (tuning): {fmt(out['first_half'])}",
        (f"- Profitable days in the second half: {out['second_half_green_days_pct']:.0f}%"
         if out["second_half_green_days_pct"] is not None else ""),
        "",
        "## Second half by side",
        "",
        *[f"- {k}: {fmt(v)}" for k, v in by_side.items()],
        "",
        "## Second half by signal hour",
        "",
        *[f"- {k}:00 — {fmt(v)}" for k, v in by_hour.items()],
        "",
        "## All settings tried",
        "",
        "| Target R | Breakeven R | Shorts | First half | Second half |",
        "|---|---|---|---|---|",
        *[f"| {r['reward']} | {r['breakeven_r']} | {r['allow_short']} | {r['first_half']} | {r['second_half']} |"
          for r in rows],
        "",
        "## Caveats",
        "",
        "- 60 days is a short sample: one market mood can dominate. Treat this as a rough check.",
        "- Fills assume the next candle's open; real slippage on fast breakouts can be worse.",
        "- Yahoo's 5-minute volume for NSE is approximate.",
    ]
    (REPORTS / "intraday_research.md").write_text("\n".join(lines))
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
