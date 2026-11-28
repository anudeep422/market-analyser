"""Risk Manager: the loss-control rules, enforced before every trade.

Pure functions (no Streamlit, no network) so every rule is unit-tested.
The journal is a DataFrame with JOURNAL_COLUMNS; storage lives in store.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

import pandas as pd

JOURNAL_COLUMNS = ["id", "Opened", "Symbol", "Side", "Qty", "Entry", "Stop", "Target",
                   "Mode", "Status", "Closed", "Exit", "PnL", "PnL %", "Notes"]


@dataclass
class RiskRules:
    capital: float = 100_000.0
    risk_pct: float = 1.0            # max loss per trade, % of capital
    max_trades_day: int = 3
    max_losses_day: int = 2          # stop for the day after this many losses
    monthly_loss_pct: float = 5.0    # pause if the month is down this much
    max_open: int = 5
    min_reward_risk: float = 1.5     # target must be at least this × risk
    results_days: int = 5            # avoid if results are within this many days
    require_trend: bool = True       # stock above 50 & 200 DMA for buys
    require_market: bool = True      # NIFTY not in a downtrend for buys

    @staticmethod
    def from_dict(d: dict | None) -> "RiskRules":
        if not d:
            return RiskRules()
        known = set(RiskRules.__dataclass_fields__)
        return RiskRules(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- journal

def empty_journal() -> pd.DataFrame:
    return pd.DataFrame(columns=JOURNAL_COLUMNS)


def normalize(j: pd.DataFrame | None) -> pd.DataFrame:
    j = empty_journal() if j is None else j.copy()
    for c in JOURNAL_COLUMNS:
        if c not in j.columns:
            j[c] = None
    for c in ("Opened", "Closed"):
        j[c] = pd.to_datetime(j[c], errors="coerce").astype("datetime64[ns]")
    for c in ("Qty", "Entry", "Stop", "Target", "Exit", "PnL", "PnL %"):
        j[c] = pd.to_numeric(j[c], errors="coerce")
    return j[JOURNAL_COLUMNS]


def add_trade(j: pd.DataFrame, symbol: str, side: str, qty: int, entry: float, stop: float,
              target: float | None, mode: str = "Paper", notes: str = "",
              when: datetime | None = None) -> pd.DataFrame:
    j = normalize(j)
    new_id = int(pd.to_numeric(j["id"], errors="coerce").max() + 1) if len(j) else 1
    row = {"id": new_id, "Opened": pd.Timestamp(when or datetime.now()).floor("s"),
           "Symbol": symbol.upper(),
           "Side": side, "Qty": int(qty), "Entry": float(entry), "Stop": float(stop),
           "Target": float(target) if target else None, "Mode": mode, "Status": "Open",
           "Closed": pd.NaT, "Exit": None, "PnL": None, "PnL %": None, "Notes": notes}
    return pd.concat([j, pd.DataFrame([row])], ignore_index=True)


def close_trade(j: pd.DataFrame, trade_id: int, exit_price: float, cost_pct: float = 0.1,
                when: datetime | None = None) -> pd.DataFrame:
    """Close a trade; PnL after approximate costs (round trip, % of entry value)."""
    j = normalize(j)
    m = pd.to_numeric(j["id"], errors="coerce") == int(trade_id)
    if not m.any():
        raise KeyError(f"No trade with id {trade_id}")
    i = j.index[m][0]
    side = 1 if j.at[i, "Side"] == "BUY" else -1
    qty, entry = float(j.at[i, "Qty"]), float(j.at[i, "Entry"])
    gross = side * (float(exit_price) - entry) * qty
    cost = entry * qty * cost_pct / 100
    pnl = gross - cost
    j.at[i, "Exit"] = float(exit_price)
    j.at[i, "Closed"] = pd.Timestamp(when or datetime.now()).floor("s")
    j.at[i, "Status"] = "Closed"
    j.at[i, "PnL"] = round(pnl, 2)
    j.at[i, "PnL %"] = round(pnl / (entry * qty) * 100, 3) if entry * qty else None
    return j


def day_stats(j: pd.DataFrame, today: date | None = None) -> dict:
    j = normalize(j)
    today = today or date.today()
    opened_today = j[j["Opened"].dt.date == today]
    closed_today = j[(j["Status"] == "Closed") & (j["Closed"].dt.date == today)]
    return {"trades_today": int(len(opened_today)),
            "losses_today": int((closed_today["PnL"] < 0).sum()),
            "pnl_today": float(closed_today["PnL"].sum()),
            "open_positions": int((j["Status"] == "Open").sum())}


def month_stats(j: pd.DataFrame, rules: RiskRules, today: date | None = None) -> dict:
    j = normalize(j)
    today = today or date.today()
    closed = j[(j["Status"] == "Closed") & (j["Closed"].dt.year == today.year)
               & (j["Closed"].dt.month == today.month)]
    pnl = float(closed["PnL"].sum())
    return {"pnl_month": pnl, "pnl_month_pct": pnl / rules.capital * 100 if rules.capital else 0.0,
            "closed_month": int(len(closed))}


def summary(j: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Closed-trade results per week ('W') or month ('M')."""
    j = normalize(j)
    c = j[j["Status"] == "Closed"].copy()
    if c.empty:
        return pd.DataFrame(columns=["Period", "Trades", "Wins", "Win %", "P&L (₹)", "Avg win", "Avg loss"])
    c["Period"] = c["Closed"].dt.to_period(freq).astype(str)
    out = []
    for per, g in c.groupby("Period"):
        w, l_ = g[g["PnL"] > 0], g[g["PnL"] <= 0]
        out.append({"Period": per, "Trades": len(g), "Wins": len(w),
                    "Win %": round(len(w) / len(g) * 100, 1), "P&L (₹)": round(g["PnL"].sum(), 2),
                    "Avg win": round(w["PnL"].mean(), 2) if len(w) else None,
                    "Avg loss": round(l_["PnL"].mean(), 2) if len(l_) else None})
    return pd.DataFrame(out).sort_values("Period", ascending=False)


def overall(j: pd.DataFrame) -> dict:
    j = normalize(j)
    c = j[j["Status"] == "Closed"]
    if c.empty:
        return {"closed": 0}
    w, l_ = c[c["PnL"] > 0], c[c["PnL"] <= 0]
    gl = -l_["PnL"].sum()
    return {"closed": int(len(c)), "win_rate": len(w) / len(c) * 100,
            "total_pnl": float(c["PnL"].sum()),
            "avg_win": float(w["PnL"].mean()) if len(w) else None,
            "avg_loss": float(l_["PnL"].mean()) if len(l_) else None,
            "profit_factor": float(w["PnL"].sum() / gl) if gl > 0 else None}


# ----------------------------------------------------------- trade check

def position_size(rules: RiskRules, entry: float, stop: float) -> dict:
    per_share = abs(entry - stop)
    if per_share <= 0 or entry <= 0:
        return {"qty": 0, "value": 0.0, "max_loss": 0.0, "per_share_risk": 0.0}
    budget = rules.capital * rules.risk_pct / 100
    qty = int(min(budget // per_share, rules.capital // entry))
    return {"qty": qty, "value": qty * entry, "max_loss": qty * per_share,
            "per_share_risk": per_share}


def check_trade(rules: RiskRules, journal: pd.DataFrame, side: str, entry: float,
                stop: float | None, target: float | None, qty: int | None = None,
                market: dict | None = None, today: date | None = None) -> dict:
    """Run every rule. `market` (optional) holds facts fetched by the app:
    close, sma50, sma200, nifty_regime (+1/0/-1), pro_score, days_to_results.
    Returns {"verdict": "ALLOWED"|"CAUTION"|"BLOCKED", "checks": [...], "size": {...}}.
    A failed hard rule blocks; a failed soft rule gives CAUTION."""
    market = market or {}
    checks: list[dict] = []

    def add(name, ok, detail, hard=True):
        checks.append({"rule": name, "ok": bool(ok) if ok is not None else None,
                       "detail": detail, "hard": hard})

    buy = side == "BUY"
    # 1. stop-loss
    stop_ok = stop is not None and stop > 0 and ((stop < entry) if buy else (stop > entry))
    add("Stop-loss set on the right side", stop_ok,
        f"Stop ₹{stop:,.2f}" if stop else "No stop-loss entered")
    size = position_size(rules, entry, stop) if stop_ok else {"qty": 0, "max_loss": 0.0,
                                                               "value": 0.0, "per_share_risk": 0.0}
    # 2. risk per trade
    if stop_ok:
        use_qty = qty if qty else size["qty"]
        loss = use_qty * abs(entry - stop)
        limit = rules.capital * rules.risk_pct / 100
        add(f"Max loss ≤ {rules.risk_pct:g}% of capital (₹{limit:,.0f})", loss <= limit + 1e-6,
            f"{use_qty} shares → possible loss ₹{loss:,.0f}. Allowed: up to {size['qty']} shares")
    # 3. reward : risk
    if stop_ok and target:
        rr = abs(target - entry) / abs(entry - stop)
        right_side = (target > entry) if buy else (target < entry)
        add(f"Target ≥ {rules.min_reward_risk:g}× risk", right_side and rr >= rules.min_reward_risk,
            f"Reward:risk = 1:{rr:.1f}", hard=False)
    elif stop_ok:
        add(f"Target ≥ {rules.min_reward_risk:g}× risk", None, "No target entered", hard=False)
    # 4-5. trend and market (buys)
    if buy and rules.require_trend:
        c, s50, s200 = market.get("close"), market.get("sma50"), market.get("sma200")
        if None not in (c, s50, s200):
            add("Stock in an uptrend (above 50 & 200-day avg)", c > s50 and c > s200,
                f"Price ₹{c:,.1f} · 50-day ₹{s50:,.1f} · 200-day ₹{s200:,.1f}")
        else:
            add("Stock in an uptrend (above 50 & 200-day avg)", None, "Trend data unavailable", hard=False)
    if buy and rules.require_market:
        r = market.get("nifty_regime")
        if r is not None:
            add("Market (NIFTY) not in a downtrend", r >= 0,
                {1: "NIFTY uptrend", 0: "NIFTY mixed", -1: "NIFTY downtrend"}[int(r)])
        else:
            add("Market (NIFTY) not in a downtrend", None, "NIFTY data unavailable", hard=False)
    # 6. setup quality
    ps = market.get("pro_score")
    if ps is not None:
        add("Setup quality (pro score ≥ 60)", ps >= 60, f"Score {ps:.0f}/100", hard=False)
    # 7. results day
    dr = market.get("days_to_results")
    if dr is not None:
        add(f"No results in the next {rules.results_days} days", not (0 <= dr <= rules.results_days),
            f"Results in {dr} day(s)" if dr >= 0 else "Results already out")
    elif rules.results_days:
        add(f"No results in the next {rules.results_days} days", None,
            "Results date unknown — check the company's results date yourself", hard=False)
    # 8-11. daily / monthly / open limits
    ds, ms = day_stats(journal, today), month_stats(journal, rules, today)
    add(f"Max {rules.max_trades_day} trades a day", ds["trades_today"] < rules.max_trades_day,
        f"{ds['trades_today']} taken today")
    add(f"Stop after {rules.max_losses_day} losses a day", ds["losses_today"] < rules.max_losses_day,
        f"{ds['losses_today']} losses today")
    add(f"Month not down {rules.monthly_loss_pct:g}%", ms["pnl_month_pct"] > -rules.monthly_loss_pct,
        f"This month: ₹{ms['pnl_month']:,.0f} ({ms['pnl_month_pct']:+.1f}%)")
    add(f"Max {rules.max_open} open positions", ds["open_positions"] < rules.max_open,
        f"{ds['open_positions']} open now")

    hard_fail = [c for c in checks if c["hard"] and c["ok"] is False]
    soft_fail = [c for c in checks if (not c["hard"] and c["ok"] is False) or c["ok"] is None]
    verdict = "BLOCKED" if hard_fail else "CAUTION" if soft_fail else "ALLOWED"
    return {"verdict": verdict, "checks": checks, "size": size}
