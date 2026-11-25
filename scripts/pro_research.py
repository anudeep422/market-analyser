"""Research + daily scan for the pro engine. Runs on GitHub Actions.

    python scripts/pro_research.py research   # ~10y test on ~110 stocks
    python scripts/pro_research.py daily      # today's pro setups

Outputs (committed back to the repo by the workflow):
    pro_stats.json               live confidence numbers used by the app
    reports/pro_research.md      readable research report
    reports/pro_trades.csv       every simulated trade
    reports/daily_pro.csv/.md    latest scan
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pro as P  # noqa: E402

REPORTS = ROOT / "reports"
SPLIT = pd.Timestamp("2021-01-01")   # tune before, judge after

NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK",
    "LT", "M&M", "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC", "POWERGRID",
    "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATASTEEL",
    "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO", "TMPV",
]
LIQUID_EXTRA = [
    "DMART", "PIDILITIND", "SIEMENS", "HAVELLS", "DLF", "GODREJCP", "DABUR", "BRITANNIA",
    "TVSMOTOR", "HEROMOTOCO", "DIVISLAB", "LUPIN", "TORNTPHARM", "BANKBARODA", "PNB",
    "CANBK", "INDUSINDBK", "FEDERALBNK", "CHOLAFIN", "ICICIGI", "ICICIPRULI", "SBICARD",
    "LTIM", "PERSISTENT", "COFORGE", "MPHASIS", "NAUKRI", "TATAPOWER", "GAIL", "IOC",
    "BPCL", "HINDPETRO", "VEDL", "JINDALSTEL", "SAIL", "AMBUJACEM", "SHREECEM", "ACC",
    "UPL", "SRF", "PAGEIND", "COLPAL", "MARICO", "BERGEPAINT", "BOSCHLTD", "MOTHERSON",
    "ASHOKLEY", "CUMMINSIND", "POLYCAB", "ABB", "HAL", "BHEL", "IRCTC", "MUTHOOTFIN",
    "INDHOTEL", "ZYDUSLIFE", "AUROPHARMA", "BIOCON", "PETRONET", "IDFCFIRSTB",
]
UNIVERSE = NIFTY50 + LIQUID_EXTRA


# ------------------------------------------------------------------ data

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(-1, axis=1)
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].dropna(subset=["Close"])
    df = df[(df["Close"] > 0) & (df["Open"] > 0)]
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


def download(symbols: list[str], period: str) -> dict[str, pd.DataFrame]:
    tickers = [s if s.startswith("^") else f"{s}.NS" for s in symbols]
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), 10):
        part = tickers[i:i + 10]
        for attempt in range(3):
            try:
                raw = yf.download(part, period=period, interval="1d", group_by="ticker",
                                  auto_adjust=True, progress=False, threads=False)
                break
            except Exception as e:  # noqa: BLE001
                print("download error", part, e)
                raw = pd.DataFrame()
                time.sleep(5 * (attempt + 1))
        for t in part:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                df = pd.DataFrame()
            df = _clean(df)
            if df.empty:
                try:
                    df = _clean(yf.Ticker(t).history(period=period, auto_adjust=True))
                except Exception:  # noqa: BLE001
                    df = pd.DataFrame()
            if not df.empty:
                out[t] = df
        time.sleep(1.5)
    return out


# -------------------------------------------------------------- research

def fmt_stats(s: dict) -> str:
    if not s or s.get("n", 0) == 0:
        return "no trades"
    pf = s.get("profit_factor")
    return (f"{s['n']} trades · win {s['win_rate']:.0f}% · avg {s['avg_net_pct']:+.2f}% "
            f"net · {s['avg_R']:+.2f}R · PF {pf:.2f}" if pf else
            f"{s['n']} trades · win {s['win_rate']:.0f}% · avg {s['avg_net_pct']:+.2f}% net")


def bucket_table(bb: dict) -> str:
    rows = ["| Setup | Score | Trades | Win % | Avg net % | Avg R | Profit factor |",
            "|---|---|---|---|---|---|---|"]
    for setup, buckets in bb.items():
        for key, s in buckets.items():
            if s.get("n", 0) == 0:
                continue
            pf = s.get("profit_factor")
            rows.append(f"| {setup} | {key} | {s['n']} | {s['win_rate']:.0f} | "
                        f"{s['avg_net_pct']:+.2f} | {s['avg_R']:+.2f} | "
                        f"{pf:.2f} |" if pf else
                        f"| {setup} | {key} | {s['n']} | {s['win_rate']:.0f} | "
                        f"{s['avg_net_pct']:+.2f} | {s['avg_R']:+.2f} | — |")
    return "\n".join(rows)


GRID = [
    P.ProParams(atr_stop=a, reward=r, trail_after_r=t, use_breakout=b)
    for b in (True, False)
    for a in (1.5, 2.0)
    for r in (1.0, 1.5, 2.0)
    for t in (0.0, 1.0)
]


def run_all(feats: dict, params) -> pd.DataFrame:
    parts = [P.simulate(d, params, symbol=t.replace(".NS", "")) for t, d in feats.items()]
    parts = [x for x in parts if not x.empty]
    return pd.concat(parts, ignore_index=True).sort_values("Signal date") if parts else pd.DataFrame()


def research():
    print("Downloading NIFTY and", len(UNIVERSE), "stocks…")
    nifty = download(["^NSEI"], "15y").get("^NSEI")
    if nifty is None or nifty.empty:
        raise SystemExit("Could not download NIFTY 50 index")
    data = download(UNIVERSE, "15y")
    print("Got", len(data), "stocks")

    feats = {t: P.features(df, nifty) for t, df in data.items() if len(df) >= 300}

    # 1) choose trade rules on IN-SAMPLE data only (total R, min 150 trades)
    grid_rows, best, best_total, trades = [], None, -2e9, pd.DataFrame()
    for gp in GRID:
        tr = run_all(feats, gp)
        ins_g = tr[tr["Signal date"] < SPLIT] if not tr.empty else tr
        s_g = P.stats(ins_g)
        n_ok = s_g.get("n", 0) >= 150
        total = s_g.get("avg_R", -9) * s_g.get("n", 0) if n_ok else -1e9 + s_g.get("n", 0)
        grid_rows.append({**P.params_dict(gp), **{f"in_{k}": v for k, v in s_g.items()},
                          "in_total_R": total})
        print(gp, P.stats(ins_g))
        if total > best_total:
            best, best_total, trades = gp, total, tr
    params = best
    if trades.empty:
        raise SystemExit("No trades produced")
    REPORTS.mkdir(exist_ok=True)
    pd.DataFrame(grid_rows).to_csv(REPORTS / "pro_grid.csv", index=False)
    ins = trades[trades["Signal date"] < SPLIT]
    oos = trades[trades["Signal date"] >= SPLIT]

    th = P.best_threshold(ins)
    ins_th, oos_th = ins[ins["Score"] >= th], oos[oos["Score"] >= th]

    # yearly out-of-sample at the threshold
    yearly = {}
    for y, g in oos_th.groupby(oos_th["Signal date"].dt.year):
        yearly[int(y)] = P.stats(g)

    # NIFTY buy & hold over the out-of-sample period, for context
    n_oos = nifty[nifty.index >= SPLIT]["Close"]
    yrs = (n_oos.index[-1] - n_oos.index[0]).days / 365.25
    nifty_cagr = ((n_oos.iloc[-1] / n_oos.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else None

    # account rules chosen on pre-2021 data only (15 slots beat 5/10/20 there)
    port = P.portfolio(oos_th, max_positions=15, risk_pct=1.0)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "stocks_tested": len(data),
        "split": str(SPLIT.date()),
        "params": P.params_dict(params),
        "threshold": th,
        "in_sample": {"all": P.stats(ins), "at_threshold": P.stats(ins_th),
                      "by_bucket": P.by_bucket(ins)},
        "out_of_sample": {"all": P.stats(oos), "at_threshold": P.stats(oos_th),
                          "by_bucket": P.by_bucket(oos), "yearly": yearly},
        "nifty_cagr_oos_pct": nifty_cagr,
        "portfolio_oos": port,
    }
    (ROOT / "pro_stats.json").write_text(json.dumps(out, indent=2, default=str))
    REPORTS.mkdir(exist_ok=True)
    trades.to_csv(REPORTS / "pro_trades.csv", index=False)

    s_o = out["out_of_sample"]["at_threshold"]
    lines = [
        "# Pro engine research report",
        "",
        f"Generated {out['generated']} UTC · {len(data)} NSE stocks · daily data · "
        f"long only · costs {params.cost_pct}% per round trip included.",
        "",
        f"Tuned on signals **before {SPLIT.date()}**, judged on signals **after** "
        "(the out-of-sample period was never used for choosing anything).",
        "",
        f"Rules chosen from {len(GRID)} combinations (in-sample only): stop "
        f"{params.atr_stop}×ATR, target {params.reward}R, breakeven after "
        f"{params.trail_after_r or 'off'}R, breakouts {'on' if params.use_breakout else 'off'}, "
        f"max hold {params.max_hold} days. All combinations: reports/pro_grid.csv.",
        "",
        f"## Result at the chosen minimum score ({th:.0f})",
        "",
        f"- **Out-of-sample (real test):** {fmt_stats(s_o)}",
        f"- In-sample (tuning): {fmt_stats(out['in_sample']['at_threshold'])}",
        f"- All setups, no score filter, out-of-sample: {fmt_stats(out['out_of_sample']['all'])}",
        (f"- NIFTY 50 buy-and-hold over the same period: {nifty_cagr:.1f}% a year"
         if nifty_cagr is not None else ""),
        "",
        "Profit factor = total profit ÷ total loss. Above 1.0 makes money; "
        "1.3+ is good; 1.6+ is strong.",
        "",
        "## ₹1 lakh account simulation (out-of-sample)",
        "",
        *([f"- ₹{port['start_capital']:,.0f} → **₹{port['end_capital']:,.0f}** "
           f"({port['total_return_pct']:+.1f}% total, **{port['cagr_pct']:.1f}% a year**)",
           f"- NIFTY 50 buy-and-hold: {nifty_cagr:.1f}% a year" if nifty_cagr is not None else "",
           f"- Worst fall from a peak: {port['max_drawdown_pct']:.1f}% (on closed trades)",
           f"- Rules: max {port['max_positions']} stocks at once, risk {port['risk_pct']:g}% of the "
           f"account per trade; {port['trades_taken']} trades taken, "
           f"{port['trades_skipped_full']} skipped because the account was full",
           "",
           "| Year | Account return |", "|---|---|",
           *[f"| {y} | {v:+.1f}% |" for y, v in port["yearly_return_pct"].items()]]
          if port.get("trades_taken") else ["No trades to simulate."]),
        "",
        "## Out-of-sample by year",
        "",
        "| Year | Result |", "|---|---|",
        *[f"| {y} | {fmt_stats(s)} |" for y, s in yearly.items()],
        "",
        "## Out-of-sample by setup and score",
        "",
        bucket_table(out["out_of_sample"]["by_bucket"]),
        "",
        "## In-sample by setup and score",
        "",
        bucket_table(out["in_sample"]["by_bucket"]),
        "",
        "## Caveats",
        "",
        "- The stock list is today's large caps, so stocks that collapsed or were "
        "removed in the past are missing (survivorship bias) — real results may be lower.",
        "- Entries at the next day's open; gaps and slippage are approximated by the cost figure.",
        "- Past results do not guarantee future results.",
    ]
    (REPORTS / "pro_research.md").write_text("\n".join(lines))
    print("\n".join(lines[:16]))


# ----------------------------------------------------------------- daily

def daily():
    stats_json = P.load_stats()
    params = P.params_from_stats(stats_json)
    nifty = download(["^NSEI"], "2y").get("^NSEI")
    if nifty is None or nifty.empty:
        raise SystemExit("Could not download NIFTY 50 index")
    data = download(UNIVERSE, "2y")
    rows = []
    for t, df in data.items():
        if len(df) < 260:
            continue
        ev = P.evaluate(df, nifty, params, stats_json=stats_json)
        s = ev["signal"]
        if not s:
            continue
        c = s["confidence"] or {}
        rows.append({
            "Symbol": t.replace(".NS", ""), "Setup": s["setup"],
            "Signal date": pd.Timestamp(s["date"]).date(), "Score": s["score"],
            "Passes filter": s["passes_threshold"], "Entry": round(s["entry"], 2),
            "Stop": round(s["stop"], 2), "Target 1": round(s["target1"], 2),
            "Target 2": round(s["target2"], 2), "Risk %": round(s["risk_pct"], 2),
            "Hist win %": round(c["win_rate"], 1) if c.get("win_rate") is not None else None,
            "Hist avg R": round(c["avg_R"], 2) if c.get("avg_R") is not None else None,
            "Hist trades": c.get("n"),
        })
    REPORTS.mkdir(exist_ok=True)
    update_journal(rows, data, params)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Passes filter", "Score"], ascending=[False, False])
    df.to_csv(REPORTS / "daily_pro.csv", index=False)
    reg = int(P.regime(nifty).iloc[-1])
    head = [f"# Pro scan — {nifty.index[-1]:%d %b %Y}", "",
            f"NIFTY regime: **{ {1: 'Bull', 0: 'Neutral', -1: 'Bear'}[reg] }**", ""]
    body = df.to_markdown(index=False) if not df.empty else "No pro setups today."
    (REPORTS / "daily_pro.md").write_text("\n".join(head) + body + "\n")
    print("\n".join(head) + body)


JOURNAL = REPORTS / "journal.csv"


def update_journal(rows: list[dict], data: dict, params) -> None:
    """Add today's fresh, filter-passing signals and update every open one."""
    j = pd.read_csv(JOURNAL, parse_dates=["Signal date"]) if JOURNAL.exists() else pd.DataFrame()
    have = set() if j.empty else set(zip(j["Symbol"], j["Signal date"].dt.date))
    new = []
    for r in rows:
        t = f"{r['Symbol']}.NS"
        if t not in data or not r["Passes filter"]:
            continue
        last_day = data[t].index[-1].date()
        if r["Signal date"] != last_day or (r["Symbol"], r["Signal date"]) in have:
            continue   # only record signals on the day they appear
        new.append({"Symbol": r["Symbol"], "Setup": r["Setup"],
                    "Signal date": pd.Timestamp(r["Signal date"]), "Score": r["Score"],
                    "Plan entry": r["Entry"], "Plan stop": r["Stop"],
                    "Plan target": r["Target 2"], "Status": "Waiting"})
    if new:
        j = pd.concat([j, pd.DataFrame(new)], ignore_index=True)
    if j.empty:
        return
    for i, r in j.iterrows():
        if r["Status"] not in ("Open", "Waiting"):
            continue
        df = data.get(f"{r['Symbol']}.NS")
        if df is None or df.empty:
            continue
        res = P.track_trade(df, r["Signal date"], float(r["Plan stop"]),
                            float(r["Plan target"]), params)
        for k, v in res.items():
            j.loc[i, k] = v
    j = j.sort_values("Signal date", ascending=False)
    j.to_csv(JOURNAL, index=False)
    summ = P.journal_summary(j)
    summ["updated"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    (REPORTS / "journal_summary.json").write_text(json.dumps(summ, indent=2))
    print("Journal:", summ)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "research"
    {"research": research, "daily": daily}[mode]()
