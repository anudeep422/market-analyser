"""Susthira Market Analyser — Indian stock market analysis dashboard.

Run locally:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import importlib

import analysis as A
import data as D
import paytm as PM
import signals as S
import pro as PRO
import intraday as I
import riskmgr as RM
import store as STORE

# Streamlit Cloud keeps imported modules in memory between code updates.
# Reload any of our own modules whose file changed since it was loaded, so a
# new app.py never runs against an old pro.py / signals.py.
_MODS = (A, S, PRO, I, RM)
for _m in _MODS:
    try:
        _mt = Path(_m.__file__).stat().st_mtime
        if getattr(_m, "_loaded_mtime", None) not in (None, _mt):
            importlib.reload(_m)
        _m._loaded_mtime = Path(_m.__file__).stat().st_mtime
    except Exception:
        pass
A, S, PRO, I, RM = (importlib.import_module(m.__name__) for m in _MODS)

st.set_page_config(page_title="Indian Market Analyser", page_icon="📈", layout="wide")

UP, DOWN, NEUTRAL = "#16a34a", "#dc2626", "#64748b"


# ----------------------------------------------------------------- helpers

def demo_frame(ticker: str, days: int = 500) -> pd.DataFrame:
    seed = int(hashlib.md5(ticker.encode()).hexdigest()[:6], 16)
    start = 200 + seed % 3000
    return A.sample_data(days=days, start=float(start), seed=seed)


def get_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    if st.session_state.get("demo"):
        return demo_frame(ticker)
    df = D.history(ticker, period)
    if PM.connected():
        df = PM.apply_quote(df, PM.quotes([ticker]).get(ticker))
    return df


def get_many(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    if st.session_state.get("demo"):
        return {t: demo_frame(t) for t in tickers}
    frames = D.history_many(tuple(tickers), period)
    if PM.connected():
        live = PM.quotes(list(tickers))
        frames = {t: PM.apply_quote(df, live.get(t)) for t, df in frames.items()}
    return frames


def fmt(v, nd=2, prefix="", suffix=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, (int, float)):
        return f"{prefix}{v:,.{nd}f}{suffix}"
    return str(v)


def signal_color(label: str) -> str:
    return UP if "Buy" in label else DOWN if "Sell" in label else NEUTRAL


def gauge(score: int, label: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "", "font": {"size": 36}},
        title={"text": label, "font": {"size": 18, "color": signal_color(label)}},
        gauge={
            "axis": {"range": [-100, 100], "tickvals": [-100, -50, 0, 50, 100]},
            "bar": {"color": signal_color(label), "thickness": 0.3},
            "steps": [
                {"range": [-100, -50], "color": "#fecaca"},
                {"range": [-50, -15], "color": "#fee2e2"},
                {"range": [-15, 15], "color": "#f1f5f9"},
                {"range": [15, 50], "color": "#dcfce7"},
                {"range": [50, 100], "color": "#bbf7d0"},
            ],
        },
    ))
    fig.update_layout(height=230, margin=dict(l=20, r=20, t=50, b=10))
    return fig


def price_chart(d: pd.DataFrame, levels: dict | None, show: set[str], bars: int) -> go.Figure:
    d = d.tail(bars)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.13, 0.16, 0.16])
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"],
                                 low=d["Low"], close=d["Close"], name="Price",
                                 increasing_line_color=UP, decreasing_line_color=DOWN),
                  row=1, col=1)
    ma_colors = {"SMA20": "#f59e0b", "SMA50": "#2563eb", "SMA200": "#7c3aed"}
    for col, color in ma_colors.items():
        if col in show:
            fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col,
                                     line=dict(color=color, width=1.4)), row=1, col=1)
    if "Bollinger" in show:
        for col in ("BB_Upper", "BB_Lower"):
            fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col, showlegend=False,
                                     line=dict(color="#94a3b8", width=1, dash="dot")),
                          row=1, col=1)
    if levels and "Pivot levels" in show:
        for k, v in levels.items():
            color = DOWN if k.startswith("R") else UP if k.startswith("S") else "#0f172a"
            fig.add_hline(y=v, line=dict(color=color, width=1, dash="dash"),
                          annotation_text=f"{k} {v:,.1f}", annotation_position="right",
                          row=1, col=1)

    vol_colors = [UP if c >= o else DOWN for o, c in zip(d["Open"], d["Close"])]
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"], marker_color=vol_colors,
                         name="Volume", showlegend=False), row=2, col=1)

    fig.add_trace(go.Scatter(x=d.index, y=d["RSI"], name="RSI",
                             line=dict(color="#0ea5e9", width=1.4)), row=3, col=1)
    for y, c in ((70, DOWN), (30, UP)):
        fig.add_hline(y=y, line=dict(color=c, width=1, dash="dot"), row=3, col=1)

    hist_colors = [UP if h >= 0 else DOWN for h in d["Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=d.index, y=d["Hist"], marker_color=hist_colors,
                         name="MACD hist", showlegend=False), row=4, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD"], name="MACD",
                             line=dict(color="#2563eb", width=1.2)), row=4, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["Signal"], name="Signal",
                             line=dict(color="#f97316", width=1.2)), row=4, col=1)

    fig.update_layout(height=820, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=90, t=10, b=10),
                      legend=dict(orientation="h", y=1.02, x=0))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    for i, t in enumerate(["Price (₹)", "Volume", "RSI", "MACD"], start=1):
        fig.update_yaxes(title_text=t, row=i, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    return fig


# ----------------------------------------------------------------- sidebar

st.sidebar.title("📈 Market Analyser")

# --- Paytm Money live prices
_login = PM.handle_redirect() if PM.configured() else None
if _login:
    (st.sidebar.success if _login[0] else st.sidebar.error)(_login[1])
if PM.configured():
    if PM.connected():
        st.sidebar.markdown("🟢 **Paytm live prices: on**")
        if st.sidebar.button("Log out of Paytm"):
            PM.logout()
            st.rerun()
    else:
        st.sidebar.link_button("🔑 Login to Paytm Money (live prices)", PM.login_url(),
                               help="Needed once a day. Without it, prices come from "
                                    "Yahoo and can be ~15 min delayed.")

quick = st.sidebar.text_input("🔍 Analyse a stock", placeholder="e.g. INFY, RELIANCE")
if quick.strip() and quick != st.session_state.get("_last_quick"):
    st.session_state["_last_quick"] = quick
    st.session_state["symbol"] = quick.strip().upper()
    st.session_state["page"] = "Stock analysis"
page = st.sidebar.radio("Go to", ["Stock analysis", "🛡️ Risk Manager", "⭐ Pro signals", "⏱️ Intraday levels", "Buy / Sell signals", "Market overview", "Screener"], key="page")
st.sidebar.toggle("Demo data (offline)", key="demo",
                  help="Use generated sample prices when live data is unavailable.")
st.sidebar.caption(("Data: Yahoo Finance history + Paytm Money live price. "
                    if PM.connected() else "Data: Yahoo Finance (may be delayed ~15 min). ") +
                   "For education only — not investment advice.")


# ------------------------------------------------------------ market overview

def page_overview():
    st.title("Indian market overview")
    cols = st.columns(len(D.INDICES))
    for col, (name, sym) in zip(cols, D.INDICES.items()):
        df = get_history(sym, "1y")
        if df.empty or len(df) < 2:
            col.metric(name, "—")
            continue
        last, prev = df["Close"].iloc[-1], df["Close"].iloc[-2]
        col.metric(name, f"{last:,.2f}", f"{(last / prev - 1) * 100:+.2f}%")
        if len(df) > 30:
            sig = A.technical_signal(df)
            col.markdown(f"<span style='color:{signal_color(sig['label'])}'>"
                         f"● {sig['label']}</span>", unsafe_allow_html=True)

    st.subheader("NIFTY 50 movers")
    with st.spinner("Loading NIFTY 50 stocks…"):
        table = build_table(D.UNIVERSES["NIFTY 50"])
    if table.empty:
        st.warning("No data returned. Check your internet connection, or switch on demo data.")
        return
    c1, c2 = st.columns(2)
    show_cols = ["Close", "Change %", "RSI", "Signal"]
    c1.markdown("**Top gainers**")
    c1.dataframe(style(table.nlargest(10, "Change %")[show_cols]), width="stretch")
    c2.markdown("**Top losers**")
    c2.dataframe(style(table.nsmallest(10, "Change %")[show_cols]), width="stretch")

    adv = int((table["Change %"] > 0).sum())
    dec = int((table["Change %"] < 0).sum())
    a, b, c = st.columns(3)
    a.metric("Advancing", adv)
    b.metric("Declining", dec)
    c.metric("Above 200-DMA", f"{int((table['vs 200DMA %'] > 0).sum())} / {len(table)}")

    st.markdown("**Signal breakdown across NIFTY 50**")
    counts = table["Signal"].value_counts().reindex(
        ["Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell"]).fillna(0)
    fig = go.Figure(go.Bar(x=counts.index, y=counts.values,
                           marker_color=[UP, "#4ade80", NEUTRAL, "#f87171", DOWN]))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")


# ------------------------------------------------------------- stock analysis

def page_stock():
    c1, c2, c3 = st.columns([2, 1, 1])
    symbol = c1.text_input("NSE/BSE symbol", value=st.session_state.get("symbol", "INFY"),
                           help="e.g. INFY, RELIANCE, HDFCBANK, M&M, BAJAJ-AUTO").strip().upper()
    exchange = c2.selectbox("Exchange", ["NSE", "BSE"])
    period = c3.selectbox("History", ["6mo", "1y", "2y", "5y"], index=2)
    if not symbol:
        return
    st.session_state["symbol"] = symbol
    ticker = D.to_yahoo(symbol, exchange)

    with st.spinner(f"Loading {ticker}…"):
        raw = get_history(ticker, period)
    if raw.empty or len(raw) < 30:
        st.error(f"No data for **{ticker}**. Check the symbol (use the NSE code, "
                 "e.g. INFY not Infosys), or switch on demo data.")
        return

    d = A.add_indicators(raw)
    last, prev = d.iloc[-1], d.iloc[-2]
    fund = {} if st.session_state.get("demo") else D.fundamentals(ticker)
    name = fund.get("Name") or symbol

    st.title(name)
    st.caption(f"{ticker} · last bar {d.index[-1]:%d %b %Y}"
               + (f" · {fund['Sector']} / {fund['Industry']}" if fund.get("Sector") else ""))

    m = st.columns([1, 1.2, 1.2, 0.8, 0.9])
    m[0].metric("Close", fmt(last["Close"], prefix="₹"),
                f"{(last['Close'] / prev['Close'] - 1) * 100:+.2f}%")
    m[1].metric("Day range", f"{last['Low']:,.0f}–{last['High']:,.0f}")
    year = d.tail(252)
    hi, lo = year["High"].max(), year["Low"].min()
    m[2].metric("52W range", f"{lo:,.0f}–{hi:,.0f}",
                f"{(last['Close'] / hi - 1) * 100:.1f}% from high", delta_color="off")
    m[3].metric("RSI (14)", fmt(last["RSI"], 1))
    m[4].metric("ATR (14)", fmt(last["ATR"], 1, prefix="₹"),
                f"{last['ATR'] / last['Close'] * 100:.1f}% daily move", delta_color="off")

    tab_report, tab_levels, tab_chart, tab_tech, tab_fund = st.tabs(
        ["📝 Full analysis", "🎯 Support & resistance", "📊 Chart",
         "🧭 Technical signal", "🏢 Fundamentals"])

    # --- written report
    with tab_report:
        rep = A.stock_report(d, fund, name=symbol)
        color = signal_color("Buy" if rep["tech_view"] == "bullish"
                             else "Sell" if rep["tech_view"] == "bearish" else "Neutral")
        st.markdown(f"<div style='border-left:6px solid {color};padding:10px 16px;"
                    f"background:rgba(100,116,139,.08);border-radius:6px'>"
                    f"<div style='font-size:13px;opacity:.7'>VERDICT</div>"
                    f"<div style='font-size:26px;font-weight:700;color:{color}'>{rep['verdict']}</div>"
                    f"<div>{rep['headline']}</div></div>", unsafe_allow_html=True)
        st.write("")
        perf = A.returns(d)
        pc = st.columns(len(perf))
        for col, (k, v) in zip(pc, perf.items()):
            col.metric(k, fmt(v, 1, suffix="%"))
        for title, lines in rep["sections"]:
            st.markdown(f"#### {title}")
            for line in lines:
                st.markdown(f"- {line}")
        st.markdown("#### What to watch")
        for line in rep["watch"]:
            st.markdown(f"- {line}")
        report_md = (f"# {name} ({ticker}) — analysis {d.index[-1]:%d %b %Y}\n\n"
                     f"**Verdict: {rep['verdict']}** — {rep['headline']}\n\n"
                     + "\n".join(f"## {t}\n" + "\n".join(f"- {x}" for x in ls) + "\n"
                                  for t, ls in rep["sections"])
                     + "\n## What to watch\n" + "\n".join(f"- {x}" for x in rep["watch"])
                     + "\n\n_For learning only. Not investment advice._\n")
        st.download_button("Download report", report_md.encode(),
                           f"{symbol}_analysis.md", "text/markdown")

    # --- levels
    with tab_levels:
        method = st.radio("Pivot method", ["classic", "fibonacci", "camarilla"],
                          horizontal=True)
        lv = A.pivot_levels(float(last["High"]), float(last["Low"]), float(last["Close"]), method)
        st.markdown(f"Levels for the **next session**, from the {d.index[-1]:%d %b} "
                    f"high/low/close.")
        close = float(last["Close"])
        rows = [{"Level": k, "Price (₹)": round(v, 2),
                 "Distance": f"{(v / close - 1) * 100:+.2f}%"} for k, v in lv.items()]
        lc, rc = st.columns([1, 1])
        lc.dataframe(pd.DataFrame(rows).set_index("Level"), width="stretch")

        p = lv["Pivot"]
        bias = ("above the pivot — slight bullish bias; first target R1"
                if close > p else "below the pivot — slight bearish bias; watch S1")
        rc.info(f"Last close ₹{close:,.2f} is {bias}.\n\n"
                f"• Break above **R1 ₹{lv['R1']:,.1f}** → next R2 ₹{lv['R2']:,.1f}\n\n"
                f"• Break below **S1 ₹{lv['S1']:,.1f}** → next S2 ₹{lv['S2']:,.1f}")

        st.markdown("**Swing-based zones** (from recent highs/lows — useful for swing trades)")
        sw = A.swing_levels(raw)
        z1, z2 = st.columns(2)
        z1.markdown("Resistance zones")
        z1.dataframe(pd.DataFrame(
            [{"Price (₹)": round(x, 1), "Touches": n,
              "Distance": f"{(x / close - 1) * 100:+.1f}%"} for x, n in sw["resistance"]]),
            hide_index=True, width="stretch")
        z2.markdown("Support zones")
        z2.dataframe(pd.DataFrame(
            [{"Price (₹)": round(x, 1), "Touches": n,
              "Distance": f"{(x / close - 1) * 100:+.1f}%"} for x, n in sw["support"]]),
            hide_index=True, width="stretch")
        st.caption("Pivots suit intraday trading; use a stop-loss. "
                   "Levels are guides, not guarantees.")

    # --- chart
    with tab_chart:
        opts = st.multiselect("Overlays",
                              ["SMA20", "SMA50", "SMA200", "Bollinger", "Pivot levels"],
                              default=["SMA50", "SMA200", "Pivot levels"])
        bars = st.slider("Bars shown", 60, len(d), min(250, len(d)))
        lv_classic = A.pivot_levels(float(last["High"]), float(last["Low"]), float(last["Close"]))
        st.plotly_chart(price_chart(d, lv_classic, set(opts), bars), width="stretch")

    # --- technical signal
    with tab_tech:
        sig = A.technical_signal(d)
        g, r = st.columns([1, 1.4])
        g.plotly_chart(gauge(sig["score"], sig["label"]), width="stretch")
        r.markdown("**Why**")
        for v, reason in sig["reasons"]:
            icon = "🟢" if v > 0 else "🔴" if v < 0 else "⚪"
            r.markdown(f"{icon} {reason}")
        st.markdown("**Indicator values**")
        vals = {
            "SMA 20": last["SMA20"], "SMA 50": last["SMA50"], "SMA 200": last["SMA200"],
            "EMA 20": last["EMA20"], "RSI 14": last["RSI"], "MACD": last["MACD"],
            "MACD signal": last["Signal"], "Bollinger upper": last["BB_Upper"],
            "Bollinger lower": last["BB_Lower"], "ATR 14": last["ATR"],
            "Volume vs 20-day avg": (last["Volume"] / last["VolAvg20"])
            if last["VolAvg20"] else None,
        }
        st.dataframe(pd.DataFrame({"Value": {k: fmt(v) for k, v in vals.items()}}),
                     width="stretch")
        st.caption("The score averages simple rule votes (moving averages, RSI, MACD, "
                   "Bollinger). It describes the trend; it does not predict it.")

    # --- fundamentals
    with tab_fund:
        if st.session_state.get("demo"):
            st.info("Fundamentals need live data — switch off demo mode.")
        elif not fund:
            st.warning("Yahoo returned no fundamentals for this symbol.")
        else:
            keys = ["Market cap (₹ Cr)", "P/E (TTM)", "Forward P/E", "P/B", "EPS (TTM, ₹)",
                    "Book value (₹)", "ROE %", "Debt / Equity", "Dividend yield %",
                    "Profit margin %", "Revenue growth %", "Beta"]
            fc = st.columns(4)
            for i, k in enumerate(keys):
                fc[i % 4].metric(k, fmt(fund.get(k), 0 if "cap" in k else 2))
            notes = []
            pe, roe, de = fund.get("P/E (TTM)"), fund.get("ROE %"), fund.get("Debt / Equity")
            if pe:
                notes.append(f"P/E {pe:.1f}: " + ("low — value zone, check why"
                             if pe < 15 else "moderate" if pe < 30 else "high — priced for growth"))
            if roe:
                notes.append(f"ROE {roe:.1f}%: " + ("strong" if roe > 18
                             else "average" if roe > 10 else "weak"))
            if de is not None:
                notes.append(f"Debt/Equity {de:.0f}%: " + ("low debt" if de < 50
                             else "moderate debt" if de < 150 else "high debt"))
            if notes:
                st.markdown("**Quick read:** " + " · ".join(notes))
            if fund.get("About"):
                with st.expander("About the company"):
                    st.write(fund["About"])
            st.caption("Yahoo's fundamentals for Indian stocks can be incomplete or "
                       "out of date — confirm on NSE, Screener.in or the annual report.")


# -------------------------------------------------------------------- screener

def build_table(symbols: list[str]) -> pd.DataFrame:
    tickers = [D.to_yahoo(s) for s in symbols]
    frames = get_many(tickers)
    rows = []
    for sym, t in zip(symbols, tickers):
        df = frames.get(t, pd.DataFrame())
        if df.empty or len(df) < 30:
            continue
        try:
            rows.append({"Symbol": sym, **A.snapshot(df)})
        except Exception:
            continue
    return pd.DataFrame(rows).set_index("Symbol") if rows else pd.DataFrame()


def style(df: pd.DataFrame):
    def color(v):
        if isinstance(v, (int, float)) and not pd.isna(v):
            return f"color: {UP if v > 0 else DOWN if v < 0 else NEUTRAL}"
        if isinstance(v, str):
            return f"color: {signal_color(v)}; font-weight: 600"
        return ""
    cols = [c for c in ["Change %", "vs 50DMA %", "vs 200DMA %", "Score", "Signal"]
            if c in df.columns]
    return df.style.format(precision=2, na_rep="—").map(color, subset=cols)


def page_screener():
    st.title("Screener")
    c1, c2 = st.columns([1, 2])
    universe = c1.selectbox("Stocks", list(D.UNIVERSES) + ["Custom list"])
    if universe == "Custom list":
        txt = c2.text_input("Symbols, comma separated", "INFY, TCS, RELIANCE, HDFCBANK, ITC")
        symbols = [s.strip().upper() for s in txt.split(",") if s.strip()]
    else:
        symbols = D.UNIVERSES[universe]
        c2.caption(", ".join(symbols))

    with st.spinner(f"Analysing {len(symbols)} stocks…"):
        table = build_table(symbols)
    if table.empty:
        st.warning("No data returned. Check the symbols or switch on demo data.")
        return

    with st.expander("Filters", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        rsi_rng = f1.slider("RSI range", 0, 100, (0, 100))
        signals = f2.multiselect("Signal", ["Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell"])
        near = f3.number_input("Within % of S1 support (0 = off)", 0.0, 20.0, 0.0, 0.5)
        trend = f4.selectbox("Trend", ["Any", "Above 200-DMA", "Below 200-DMA"])

    t = table[(table["RSI"].fillna(50) >= rsi_rng[0]) & (table["RSI"].fillna(50) <= rsi_rng[1])]
    if signals:
        t = t[t["Signal"].isin(signals)]
    if near > 0:
        t = t[((t["Close"] / t["S1"] - 1) * 100).abs() <= near]
    if trend == "Above 200-DMA":
        t = t[t["vs 200DMA %"] > 0]
    elif trend == "Below 200-DMA":
        t = t[t["vs 200DMA %"] < 0]

    st.markdown(f"**{len(t)}** of {len(table)} stocks match")
    st.dataframe(style(t.sort_values("Score", ascending=False)),
                 width="stretch", height=min(80 + 35 * len(t), 700))
    st.download_button("Download CSV", t.to_csv().encode(), "screener.csv", "text/csv")

    q1, q2 = st.columns(2)
    q1.markdown("**Oversold (RSI < 30)**")
    q1.write(", ".join(table[table["RSI"] < 30].index) or "None")
    q2.markdown("**Overbought (RSI > 70)**")
    q2.write(", ".join(table[table["RSI"] > 70].index) or "None")

    pick = st.selectbox("Open a stock in Stock analysis", ["—"] + list(t.index))
    if pick != "—":
        st.session_state["symbol"] = pick
        st.info(f"Selected {pick}. Choose **Stock analysis** in the sidebar.")


# ------------------------------------------------------------ buy/sell signals

def signal_params() -> "S.Params":
    with st.expander("⚙️ Strategy settings"):
        c = st.columns(4)
        atr_mult = c[0].number_input("Stop-loss (× ATR)", 0.5, 5.0, 1.5, 0.25)
        reward = c[1].number_input("Target (× risk)", 1.0, 5.0, 2.0, 0.5)
        hold = c[2].number_input("Max holding days", 3, 60, 20, 1)
        short = c[3].toggle("Count SELL as short trades", True,
                            help="Off = SELL signals only mean 'exit / avoid'.")
    return S.Params(atr_mult=atr_mult, reward=reward, max_hold=int(hold), allow_short=short)


def signal_chart(d: pd.DataFrame, sig: pd.Series, plan: dict | None, bars: int = 250):
    d, sig = d.tail(bars), sig.tail(bars)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"],
                                 close=d["Close"], name="Price",
                                 increasing_line_color=UP, decreasing_line_color=DOWN))
    for col, color in (("SMA50", "#2563eb"), ("SMA200", "#7c3aed")):
        fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col, line=dict(color=color, width=1.2)))
    buys, sells = sig[sig > 0].index, sig[sig < 0].index
    fig.add_trace(go.Scatter(x=buys, y=d.loc[buys, "Low"] * 0.985, mode="markers", name="BUY",
                             marker=dict(symbol="triangle-up", size=12, color=UP)))
    fig.add_trace(go.Scatter(x=sells, y=d.loc[sells, "High"] * 1.015, mode="markers", name="SELL",
                             marker=dict(symbol="triangle-down", size=12, color=DOWN)))
    if plan:
        for k, label, color in (("entry", "Entry", "#0f172a"), ("stop", "Stop-loss", DOWN),
                                ("target1", "Target 1", UP), ("target2", "Target 2", UP)):
            fig.add_hline(y=plan[k], line=dict(color=color, width=1.2, dash="dash"),
                          annotation_text=f"{label} {plan[k]:,.1f}", annotation_position="right")
    fig.update_layout(height=520, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=100, t=10, b=10),
                      legend=dict(orientation="h", y=1.03, x=0))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def page_signals():
    st.title("Buy / Sell signals")
    st.warning("Educational tool. Signals come from fixed rules and their past results on "
               "this stock — no tool can tell exactly where a price will go. Always use the "
               "stop-loss. Not investment advice.", icon="⚠️")
    c1, c2 = st.columns([2, 1])
    symbol = c1.text_input("Stock", value=st.session_state.get("symbol", "INFY"),
                           key="sig_symbol").strip().upper()
    exchange = c2.selectbox("Exchange", ["NSE", "BSE"], key="sig_ex")
    p = signal_params()
    tab_one, tab_scan, tab_how = st.tabs(["🎯 Stock signal", "🔎 Signal scanner", "📘 Strategies"])

    with tab_one:
        if not symbol:
            return
        st.session_state["symbol"] = symbol
        ticker = D.to_yahoo(symbol, exchange)
        with st.spinner(f"Analysing {ticker}…"):
            raw = get_history(ticker, "5y")
        if raw.empty or len(raw) < 220:
            st.error(f"Not enough data for **{ticker}** (needs about a year of history).")
            return
        ev = S.evaluate(raw, p)
        d, plan = ev["data"], ev["plan"]
        close = float(d["Close"].iloc[-1])

        # --- the call
        if plan:
            color = UP if plan["side"] == "BUY" else DOWN
            fired = [r for r in ev["results"] if r["fresh"]]
            why = ", ".join(f"{r['strategy'].name} ({'BUY' if r['fresh'] > 0 else 'SELL'})"
                            for r in fired)
            st.markdown(
                f"<div style='border-left:6px solid {color};padding:12px 16px;"
                f"background:rgba(100,116,139,.08);border-radius:6px'>"
                f"<div style='font-size:13px;opacity:.7'>SIGNAL · {d.index[-1]:%d %b %Y}</div>"
                f"<div style='font-size:30px;font-weight:800;color:{color}'>{plan['side']}</div>"
                f"<div>Triggered by: {why}</div></div>", unsafe_allow_html=True)
            st.write("")
            m = st.columns(5)
            m[0].metric("Entry (around)", fmt(plan["entry"], prefix="₹"))
            m[1].metric("Stop-loss", fmt(plan["stop"], prefix="₹"),
                        f"{-plan['risk_pct'] if plan['side'] == 'BUY' else plan['risk_pct']:+.1f}%",
                        delta_color="off")
            m[2].metric("Target 1 (1R)", fmt(plan["target1"], prefix="₹"),
                        f"{(plan['target1'] / plan['entry'] - 1) * 100:+.1f}%", delta_color="off")
            m[3].metric(f"Target 2 ({plan['rr']:g}R)", fmt(plan["target2"], prefix="₹"),
                        f"{(plan['target2'] / plan['entry'] - 1) * 100:+.1f}%", delta_color="off")
            m[4].metric("Risk : Reward", f"1 : {plan['rr']:g}")
            if plan["side"] == "SELL":
                st.caption("SELL = exit if you hold it, or a short trade (intraday or via "
                           "futures/options) for experienced traders. Cash-market shorts "
                           "must be squared off the same day.")

            with st.expander("💰 Position size calculator", expanded=True):
                a, b = st.columns(2)
                capital = a.number_input("Your capital (₹)", 1000, 100_000_000, 100_000, 5000)
                risk_pct = b.slider("Max loss per trade (% of capital)", 0.25, 5.0, 1.0, 0.25)
                ps = S.position_size(capital, risk_pct, plan["entry"], plan["stop"])
                st.markdown(f"Buy/sell **{ps['qty']} shares** (≈ ₹{ps['value']:,.0f}). "
                            f"If the stop-loss is hit you lose about **₹{ps['max_loss']:,.0f}** "
                            f"({risk_pct:g}% of capital).")
        else:
            st.markdown(
                "<div style='border-left:6px solid #64748b;padding:12px 16px;"
                "background:rgba(100,116,139,.08);border-radius:6px'>"
                "<div style='font-size:13px;opacity:.7'>SIGNAL</div>"
                "<div style='font-size:30px;font-weight:800;color:#64748b'>NO TRADE</div>"
                "<div>None of the strategies has a fresh signal in the last 3 sessions. "
                "Waiting is also a position.</div></div>", unsafe_allow_html=True)

        # --- zones: always tell where buying/selling makes sense
        st.markdown("#### Where to buy and where to sell")
        sw = A.swing_levels(d)
        last = d.iloc[-1]
        piv = A.pivot_levels(float(last["High"]), float(last["Low"]), close)
        buy_zone = sw["support"][0][0] if sw["support"] else piv["S1"]
        sell_zone = sw["resistance"][0][0] if sw["resistance"] else piv["R1"]
        z1, z2 = st.columns(2)
        z1.success(f"**Buy zone: ₹{buy_zone * 0.995:,.0f} – ₹{buy_zone * 1.005:,.0f}**\n\n"
                   f"Nearest support ({(buy_zone / close - 1) * 100:+.1f}% from ₹{close:,.0f}). "
                   f"Buyers have stepped in here before. A close well below it weakens the case.")
        z2.error(f"**Sell / book-profit zone: ₹{sell_zone * 0.995:,.0f} – ₹{sell_zone * 1.005:,.0f}**\n\n"
                 f"Nearest resistance ({(sell_zone / close - 1) * 100:+.1f}%). Sellers have "
                 f"appeared here before. A close well above it is bullish.")
        trend_up = last["Close"] > last["SMA200"] if pd.notna(last["SMA200"]) else None
        if trend_up is not None:
            st.caption("Long-term trend is **up** (above 200-DMA): buying near support is the "
                       "higher-probability side." if trend_up else
                       "Long-term trend is **down** (below 200-DMA): rallies to resistance tend "
                       "to fail; buying near support is riskier — keep positions small.")

        # --- chart + per-strategy history
        st.markdown("#### Signals on the chart")
        best = max(ev["results"], key=lambda r: (r["fresh"] != 0, r["stats"]["Profit factor"] or 0))
        names = {r["strategy"].name: r for r in ev["results"]}
        pick = st.selectbox("Show markers for", list(names),
                            index=list(names).index(best["strategy"].name))
        st.plotly_chart(signal_chart(d, names[pick]["signal"], plan), width="stretch")

        st.markdown("#### How each strategy has done on this stock (last 5 years)")
        rows = []
        for r in ev["results"]:
            s = r["stats"]
            rows.append({"Strategy": r["strategy"].name,
                         "Now": {1: "BUY", -1: "SELL", 0: "—"}[r["fresh"]],
                         "Trades": s["Trades"], "Win rate %": s["Win rate %"],
                         "Avg return %": s["Avg return %"], "Total return %": s["Total return %"],
                         "Profit factor": s["Profit factor"], "Max drawdown %": s["Max drawdown %"],
                         "Avg days": s["Avg days"]})
        tbl = pd.DataFrame(rows).set_index("Strategy")
        st.dataframe(tbl.style.format(precision=1, na_rep="—"), width="stretch")
        bh = (close / float(d["Close"].iloc[0]) - 1) * 100
        st.caption(f"Buy-and-hold over the same period: {bh:+.1f}%. Profit factor above 1 means "
                   "winners outweighed losers; below 1 means the strategy lost money here. "
                   "Past results do not guarantee future results; costs and taxes not included.")
        with st.expander("All past trades for the selected strategy"):
            t = names[pick]["trades"]
            if t.empty:
                st.write("No trades.")
            else:
                st.dataframe(t.sort_values("Signal date", ascending=False)
                             .style.format(precision=2), width="stretch", hide_index=True)

    with tab_scan:
        universe = st.selectbox("Scan", list(D.UNIVERSES), key="scan_u")
        if st.button(f"Scan {len(D.UNIVERSES[universe])} stocks for fresh signals", type="primary"):
            syms = D.UNIVERSES[universe]
            frames = get_many([D.to_yahoo(s) for s in syms], period="5y")
            rows, bar = [], st.progress(0.0)
            for i, sym in enumerate(syms):
                bar.progress((i + 1) / len(syms))
                df = frames.get(D.to_yahoo(sym), pd.DataFrame())
                if df.empty or len(df) < 220:
                    continue
                try:
                    ev = S.evaluate(df, p)
                except Exception:
                    continue
                if not ev["plan"]:
                    continue
                pl = ev["plan"]
                fired = [r for r in ev["results"] if r["fresh"]]
                pfs = [r["stats"]["Profit factor"] for r in fired if r["stats"]["Profit factor"]]
                rows.append({"Symbol": sym, "Signal": pl["side"], "Entry": pl["entry"],
                             "Stop-loss": pl["stop"], "Target 1": pl["target1"],
                             "Target 2": pl["target2"], "Risk %": pl["risk_pct"],
                             "Strategies": ", ".join(r["strategy"].name for r in fired),
                             "Past profit factor": sum(pfs) / len(pfs) if pfs else None})
            bar.empty()
            if not rows:
                st.info("No fresh signals in this group right now.")
            else:
                out = pd.DataFrame(rows).set_index("Symbol").sort_values(
                    "Past profit factor", ascending=False, na_position="last")
                st.dataframe(out.style.format(precision=2, na_rep="—").map(
                    lambda v: f"color:{UP if v == 'BUY' else DOWN};font-weight:700"
                    if v in ("BUY", "SELL") else "", subset=["Signal"]), width="stretch")
                st.download_button("Download CSV", out.to_csv().encode(), "signals.csv", "text/csv")

    with tab_how:
        st.markdown("Each strategy is a plugin in `signals.py`. A signal appears at the close "
                    "of a day and is acted on at the next day's open. Stop-loss = "
                    f"{p.atr_mult:g} × ATR (adjusted to nearby swing levels), Target 1 = 1× risk, "
                    f"Target 2 = {p.reward:g}× risk. When several strategies fire, each counts "
                    "in proportion to how well it has worked on that stock before.")
        for stg in S.STRATEGIES.values():
            st.markdown(f"**{stg.name}** — {stg.description}")


# ------------------------------------------------------------------ pro page

def page_pro():
    st.title("⭐ Pro signals")
    js = PRO.load_stats()
    st.caption("Long-only, high-quality setups: trades only with the market trend, only "
               "stocks beating NIFTY, scored 0–100. Confidence numbers come from a test on "
               "~110 NSE stocks over ~10 years with costs included.")
    if js:
        s = js["out_of_sample"]["at_threshold"]
        if s.get("n"):
            c = st.columns(5)
            c[0].metric("Tested trades (after 2021)", f"{s['n']:,}")
            c[1].metric("Win rate", f"{s['win_rate']:.0f}%")
            c[2].metric("Avg profit / trade", f"{s['avg_net_pct']:+.2f}%")
            c[3].metric("Profit factor", fmt(s.get("profit_factor")))
            c[4].metric("Min score used", f"{js['threshold']:.0f}")
            st.caption(f"Research updated {js['generated'][:10]} · {js['stocks_tested']} stocks · "
                       "results on data the strategy was never tuned on. "
                       "Profit factor above 1 = made money; 1.3+ good.")
        port = js.get("portfolio_oos") or {}
        if port.get("trades_taken"):
            with st.expander(f"💰 ₹1 lakh test since 2021: ₹{port['end_capital']:,.0f} "
                             f"({port['cagr_pct']:.1f}% a year)", expanded=False):
                k = st.columns(4)
                k[0].metric("₹1 lakh became", f"₹{port['end_capital']:,.0f}",
                            f"{port['total_return_pct']:+.1f}%")
                k[1].metric("Per year", f"{port['cagr_pct']:.1f}%")
                k[2].metric("NIFTY per year", fmt(js.get("nifty_cagr_oos_pct"), 1, suffix="%"))
                k[3].metric("Worst fall", f"{port['max_drawdown_pct']:.1f}%")
                curve = pd.DataFrame(port["curve"], columns=["Date", "Account (₹)"])
                curve["Date"] = pd.to_datetime(curve["Date"])
                fig = go.Figure(go.Scatter(x=curve["Date"], y=curve["Account (₹)"],
                                           line=dict(color="#2563eb", width=2), name="Account"))
                fig.add_hline(y=port["start_capital"], line=dict(color=NEUTRAL, dash="dot"))
                fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, width="stretch")
                st.caption(f"Max {port['max_positions']} stocks at a time, risking "
                           f"{port['risk_pct']:g}% of the account per trade, costs included. "
                           "Only data the strategy was never tuned on.")
    else:
        st.info("Research results not available yet — scores are shown without "
                "historical confidence until the first research run finishes.")

    tab_one, tab_today, tab_journal, tab_report = st.tabs(
        ["🎯 Check a stock", "📋 Today's pro list", "📒 Live journal", "📑 Research report"])
    with tab_one:
        symbol = st.text_input("Stock", value=st.session_state.get("symbol", "INFY"),
                               key="pro_symbol").strip().upper()
        if symbol:
            st.session_state["symbol"] = symbol
            df = get_history(D.to_yahoo(symbol), "5y")
            nifty = get_history("^NSEI", "5y")
            if df.empty or len(df) < 260 or nifty.empty:
                st.error("Not enough data for this stock or for NIFTY right now.")
            else:
                rules = PRO.params_from_stats(js)
                ev = PRO.evaluate(df, nifty, rules, stats_json=js)
                sig = ev["signal"]
                reg = {1: "🟢 Bull", 0: "🟡 Neutral", -1: "🔴 Bear"}[ev["regime"]]
                a, b = st.columns(2)
                a.metric("NIFTY market trend", reg)
                b.metric("Quality score now", f"{ev['score_now']:.0f} / 100")
                if sig and sig["passes_threshold"]:
                    color = UP
                    title = f"BUY — {sig['setup']}"
                elif sig:
                    color = "#f59e0b"
                    title = f"Weak {sig['setup']} (score below {ev['threshold']:.0f}) — skip"
                else:
                    color = NEUTRAL
                    title = "NO PRO SETUP"
                st.markdown(f"<div style='border-left:6px solid {color};padding:12px 16px;"
                            f"background:rgba(100,116,139,.08);border-radius:6px'>"
                            f"<div style='font-size:28px;font-weight:800;color:{color}'>{title}</div>"
                            + (f"<div>Signal on {pd.Timestamp(sig['date']):%d %b} · score {sig['score']:.0f}</div>"
                               if sig else "<div>No setup passed the filters in the last 3 sessions. "
                               "Waiting is part of the strategy.</div>")
                            + "</div>", unsafe_allow_html=True)
                if sig:
                    st.write("")
                    m = st.columns(4)
                    m[0].metric("Entry (around)", fmt(sig["entry"], prefix="₹"))
                    m[1].metric("Stop-loss", fmt(sig["stop"], prefix="₹"),
                                f"-{sig['risk_pct']:.1f}%", delta_color="off")
                    m[2].metric("Target 1", fmt(sig["target1"], prefix="₹"))
                    m[3].metric(f"Target 2 ({rules.reward:g}R)", fmt(sig["target2"], prefix="₹"))
                    conf = sig["confidence"]
                    if conf:
                        st.success(f"**Similar setups in the past** ({sig['setup']}, score "
                                   f"{conf['bucket']}): {conf['n']} trades, won "
                                   f"{conf['win_rate']:.0f}%, average {conf['avg_net_pct']:+.2f}% "
                                   f"after costs ({conf['avg_R']:+.2f}R).")
                    be = (f"move stop to entry once price is +{rules.trail_after_r:g}R; "
                          if rules.trail_after_r else "")
                    st.caption(f"Rules (chosen by the research): stop {rules.atr_stop:g}×ATR; "
                               f"{be}exit at Target 2 ({rules.reward:g}R) or after "
                               f"{rules.max_hold} trading days.")
                st.markdown("#### Why this score")
                for label, pts, mx in ev["breakdown"]:
                    st.progress(min(pts / mx, 1.0), text=f"{label}: {pts:.0f} / {mx}")

    with tab_today:
        f = PRO.STATS_FILE.parent / "reports" / "daily_pro.csv"
        if f.exists():
            t = pd.read_csv(f)
            st.caption(f"From the after-close scan · file updated "
                       f"{pd.Timestamp(f.stat().st_mtime, unit='s'):%d %b %Y}")
            if t.empty:
                st.info("No pro setups in the latest scan.")
            else:
                st.dataframe(t, hide_index=True, width="stretch")
        else:
            st.info("The daily scan hasn't run yet.")

    with tab_journal:
        jf = PRO.STATS_FILE.parent / "reports" / "journal.csv"
        if not jf.exists():
            st.info("The journal starts with the first daily scan. Every pro signal that "
                    "passes the filter is recorded on the day it appears and followed "
                    "until it hits its target, stop-loss or time limit.")
        else:
            j = pd.read_csv(jf)
            sm = PRO.journal_summary(j)
            k = st.columns(4)
            k[0].metric("Signals recorded", sm["signals"])
            k[1].metric("Closed", sm["closed"])
            k[2].metric("Win rate", fmt(sm.get("win_rate"), 0, suffix="%"))
            k[3].metric("Avg result", fmt(sm.get("avg_net_pct"), 2, suffix="%"))
            st.caption("Real signals tracked forward — the honest test. "
                       "Judge it after 30+ closed trades, not a handful.")
            cols = [c for c in ["Symbol", "Setup", "Signal date", "Score", "Status",
                                "Entry price", "Stop (live)", "Target (live)", "Last price",
                                "Exit date", "Exit price", "Net %"] if c in j.columns]
            st.dataframe(j[cols].style.format(precision=2, na_rep="—"),
                         hide_index=True, width="stretch")

    with tab_report:
        f = PRO.STATS_FILE.parent / "reports" / "pro_research.md"
        st.markdown(f.read_text() if f.exists() else "Research report not available yet.")


# ------------------------------------------------------------- intraday page

def demo_intraday(ticker: str) -> pd.DataFrame:
    seed = int(hashlib.md5(ticker.encode()).hexdigest()[:6], 16)
    rng = np.random.default_rng(seed)
    parts, p = [], 200 + seed % 3000
    for day in pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=3):
        idx = pd.date_range(f"{day.date()} 09:15", periods=75, freq="5min")
        r = rng.normal(rng.normal(0, 0.0005), 0.002, 75)
        c = p * np.exp(np.cumsum(r))
        o = np.r_[p, c[:-1]]
        parts.append(pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.0008,
                                   "Low": np.minimum(o, c) * 0.9992, "Close": c,
                                   "Volume": rng.integers(10_000, 60_000, 75).astype(float)},
                                  index=idx))
        p = c[-1]
    return pd.concat(parts)


def get_intraday(ticker: str) -> pd.DataFrame:
    if st.session_state.get("demo"):
        return demo_intraday(ticker)
    return D.history_intraday(ticker)


def intraday_chart(t: pd.DataFrame, levels: dict, show: set[str]) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.62, 0.18, 0.20])
    fig.add_trace(go.Candlestick(x=t.index, open=t["Open"], high=t["High"], low=t["Low"],
                                 close=t["Close"], name="Price",
                                 increasing_line_color=UP, decreasing_line_color=DOWN), row=1, col=1)
    fig.add_trace(go.Scatter(x=t.index, y=t["VWAP"], name="VWAP",
                             line=dict(color="#f59e0b", width=2)), row=1, col=1)
    if "EMA 9/20" in show:
        fig.add_trace(go.Scatter(x=t.index, y=t["EMA9"], name="EMA 9",
                                 line=dict(color="#2563eb", width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=t.index, y=t["EMA20"], name="EMA 20",
                                 line=dict(color="#7c3aed", width=1.2)), row=1, col=1)
    styles = {"Opening range high": ("#0f172a", "dash"), "Opening range low": ("#0f172a", "dash"),
              "Prev day high": (DOWN, "dot"), "Prev day low": (UP, "dot"),
              "Prev day close": (NEUTRAL, "dot")}
    for k, v in levels.items():
        if pd.isna(v):
            continue
        if k in styles and "Day levels" in show:
            color, dash = styles[k]
        elif k.startswith(("R", "S", "Pivot")) and "Pivots" in show:
            color = DOWN if k.startswith("R") else UP if k.startswith("S") else "#0f172a"
            dash = "longdash"
        else:
            continue
        fig.add_hline(y=v, line=dict(color=color, width=1, dash=dash),
                      annotation_text=f"{k} {v:,.1f}", annotation_position="right",
                      annotation_font_size=10, row=1, col=1)
    vc = [UP if c >= o else DOWN for o, c in zip(t["Open"], t["Close"])]
    fig.add_trace(go.Bar(x=t.index, y=t["Volume"], marker_color=vc, showlegend=False,
                         name="Volume"), row=2, col=1)
    fig.add_trace(go.Scatter(x=t.index, y=t["VolAvg"], name="Vol avg",
                             line=dict(color=NEUTRAL, width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=t.index, y=t["RSI"], name="RSI",
                             line=dict(color="#0ea5e9", width=1.3)), row=3, col=1)
    for y, c in ((60, UP), (40, DOWN)):
        fig.add_hline(y=y, line=dict(color=c, width=1, dash="dot"), row=3, col=1)
    # keep the y-axis around the day's prices so far-away levels don't squash candles
    lo, hi = float(t["Low"].min()), float(t["High"].max())
    pad = (hi - lo) * 0.6 or hi * 0.01
    fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    fig.update_layout(height=760, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=130, t=10, b=10),
                      legend=dict(orientation="h", y=1.02, x=0))
    return fig


def page_intraday():
    st.title("⏱️ Intraday levels")
    st.caption("Analysis only — no buy/sell calls. In a 60-day test the intraday breakout "
               "signals lost money after costs, so use this to read the day, not as a signal.")
    c1, c2 = st.columns([2, 1])
    symbol = c1.text_input("Stock", value=st.session_state.get("symbol", "INFY"),
                           key="intra_symbol").strip().upper()
    show = c2.multiselect("Show", ["Day levels", "Pivots", "EMA 9/20"],
                          default=["Day levels", "Pivots", "EMA 9/20"])
    if not symbol:
        return
    st.session_state["symbol"] = symbol
    ticker = D.to_yahoo(symbol)

    @st.fragment(run_every="60s")
    def live():
        raw = get_intraday(ticker)
        nraw = get_intraday("^NSEI")
        if raw.empty or len(raw) < 20:
            st.error(f"No 5-minute data for **{ticker}** right now. Yahoo may be limiting "
                     "requests — try again in a minute.")
            return
        d = I.add_market(I.features(raw), nraw if not nraw.empty else None)
        day = d["Day"].iloc[-1]
        t = d[d["Day"] == day]
        last = t.iloc[-1]
        close = float(last["Close"])
        piv = (A.pivot_levels(float(last["PDH"]), float(last["PDL"]), float(last["PDC"]))
               if pd.notna(last["PDH"]) else {})
        levels = {"Opening range high": last["ORH"], "Opening range low": last["ORL"],
                  "Prev day high": last["PDH"], "Prev day low": last["PDL"],
                  "Prev day close": last["PDC"], **piv}

        today_ist = pd.Timestamp.now(tz="Asia/Kolkata").normalize().tz_localize(None)
        session = "today" if day == today_ist else f"last session ({day:%a %d %b})"
        st.caption(f"{ticker} · 5-minute candles · {session} · last candle "
                   f"{t.index[-1]:%H:%M} · refreshes every minute")

        chg = (close / last["PDC"] - 1) * 100 if pd.notna(last["PDC"]) else None
        m = st.columns(5)
        m[0].metric("Price", fmt(close, prefix="₹"), fmt(chg, 2, suffix="%") if chg is not None else None)
        m[1].metric("VWAP", fmt(last["VWAP"], prefix="₹"),
                    f"price {(close / last['VWAP'] - 1) * 100:+.2f}% from VWAP", delta_color="off")
        m[2].metric("Opening range", f"{last['ORL']:,.1f}–{last['ORH']:,.1f}"
                    if pd.notna(last["ORH"]) else "—")
        m[3].metric("RSI (5m)", fmt(last["RSI"], 1))
        nm = {1: "🟢 above VWAP", -1: "🔴 below VWAP", 0: "—"}[int(np.sign(last.get("Mkt", 0)))]
        m[4].metric("NIFTY", nm)

        # plain-language picture of the day
        pic = []
        pic.append(("Above VWAP — buyers in control today" if close > last["VWAP"]
                    else "Below VWAP — sellers in control today"))
        if pd.notna(last["ORH"]):
            if close > last["ORH"]:
                pic.append("Trading above the opening range — upside breakout so far")
            elif close < last["ORL"]:
                pic.append("Trading below the opening range — downside breakdown so far")
            else:
                pic.append("Still inside the opening range — no clear direction yet")
        pic.append("EMA 9 above EMA 20 — short-term trend up" if last["EMA9"] > last["EMA20"]
                   else "EMA 9 below EMA 20 — short-term trend down")
        if pd.notna(last["RSI"]):
            pic.append(f"RSI {last['RSI']:.0f} — " + ("strong momentum" if last["RSI"] > 60 else
                       "weak momentum" if last["RSI"] < 40 else "no strong momentum"))
        if pd.notna(last["VolAvg"]) and last["VolAvg"] > 0:
            vr = last["Volume"] / last["VolAvg"]
            pic.append(f"Last candle volume {vr:.1f}× average")
        if pd.notna(last["PDH"]):
            if close > last["PDH"]:
                pic.append("Above yesterday's high — strong day")
            elif close < last["PDL"]:
                pic.append("Below yesterday's low — weak day")
        st.markdown("**Today's picture:** " + " · ".join(pic))

        st.plotly_chart(intraday_chart(t, levels, set(show)), width="stretch")

        st.markdown("#### Levels")
        rows = [{"Level": k, "Price (₹)": round(float(v), 2),
                 "Distance": f"{(float(v) / close - 1) * 100:+.2f}%",
                 "Side": "above" if v > close else "below"}
                for k, v in levels.items() if pd.notna(v)]
        lv = pd.DataFrame(rows).sort_values("Price (₹)", ascending=False)
        st.dataframe(lv, hide_index=True, width="stretch")
        above = lv[lv["Side"] == "above"].tail(1)
        below = lv[lv["Side"] == "below"].head(1)
        if len(above) and len(below):
            st.info(f"Nearest resistance: **{above.iloc[0]['Level']} ₹{above.iloc[0]['Price (₹)']:,.1f}** · "
                    f"nearest support: **{below.iloc[0]['Level']} ₹{below.iloc[0]['Price (₹)']:,.1f}**")
        st.caption("Yahoo's 5-minute NSE data can lag the live market by a few minutes. "
                   "Check your broker's chart before acting.")

    live()


# ------------------------------------------------------------- risk manager

def rm_load():
    if "_rm_journal" not in st.session_state:
        try:
            st.session_state["_rm_journal"] = RM.normalize(STORE.load_journal())
            st.session_state["_rm_rules"] = RM.RiskRules.from_dict(STORE.load_rules())
            st.session_state["_rm_err"] = None
        except Exception as e:  # noqa: BLE001
            st.session_state["_rm_journal"] = RM.empty_journal()
            st.session_state["_rm_rules"] = RM.RiskRules()
            st.session_state["_rm_err"] = str(e)
    return st.session_state["_rm_journal"], st.session_state["_rm_rules"]


def rm_save_journal(j, msg):
    st.session_state["_rm_journal"] = RM.normalize(j)
    try:
        STORE.save_journal(j, msg)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def market_facts(symbol: str) -> dict:
    """Trend, market regime, pro score and results date for the checks."""
    if st.session_state.get("demo"):
        df, nifty, dres = demo_frame(D.to_yahoo(symbol)), demo_frame("^NSEI"), None
    else:
        df, nifty = get_history(D.to_yahoo(symbol), "2y"), get_history("^NSEI", "2y")
        dres = D.days_to_results(D.to_yahoo(symbol))
    out = {"days_to_results": dres}
    if not df.empty and len(df) > 210:
        d = A.add_indicators(df)
        last = d.iloc[-1]
        out.update(close=float(last["Close"]), sma50=float(last["SMA50"]),
                   sma200=float(last["SMA200"]), atr=float(last["ATR"]))
        if not nifty.empty and len(nifty) > 210:
            out["nifty_regime"] = int(PRO.regime(nifty).iloc[-1])
            try:
                out["pro_score"] = float(PRO.score(PRO.features(df, nifty)).iloc[-1])
            except Exception:
                pass
    return out


def page_risk():
    st.title("🛡️ Risk Manager")
    j, rules = rm_load()
    if STORE.configured():
        st.caption("Journal and rules are saved to your GitHub repo ('data' branch).")
    else:
        st.warning("Not saving yet — add a GitHub token in Streamlit Secrets (see README). "
                   "Until then trades are kept only while this page is open.", icon="💾")
    if st.session_state.get("_rm_err"):
        st.error(f"Couldn't load saved data: {st.session_state['_rm_err']}")

    ds, ms = RM.day_stats(j), RM.month_stats(j, rules)
    k = st.columns(4)
    k[0].metric("Trades today", f"{ds['trades_today']} / {rules.max_trades_day}")
    k[1].metric("Losses today", f"{ds['losses_today']} / {rules.max_losses_day}")
    k[2].metric("This month", f"₹{ms['pnl_month']:,.0f}", f"{ms['pnl_month_pct']:+.1f}%")
    k[3].metric("Open positions", f"{ds['open_positions']} / {rules.max_open}")
    if ds["losses_today"] >= rules.max_losses_day:
        st.error("🛑 Daily loss limit reached — no more trades today. Come back tomorrow.")
    elif ds["trades_today"] >= rules.max_trades_day:
        st.error("🛑 Daily trade limit reached — no more trades today.")
    if ms["pnl_month_pct"] <= -rules.monthly_loss_pct:
        st.error(f"⏸️ Down {abs(ms['pnl_month_pct']):.1f}% this month — trading paused until "
                 "next month. Review your journal.")

    t_check, t_journal, t_results, t_rules = st.tabs(
        ["✅ Check a trade", "📒 My journal", "📊 Results", "⚙️ My rules"])

    with t_check:
        a, b = st.columns([2, 1])
        symbol = a.text_input("Stock", value=st.session_state.get("symbol", "INFY"),
                              key="rm_symbol").strip().upper()
        side = b.radio("Side", ["BUY", "SELL"], horizontal=True, key="rm_side")
        facts = market_facts(symbol) if symbol else {}
        px, atr = facts.get("close"), facts.get("atr")
        if px:
            sgn = 1 if side == "BUY" else -1
            sug_stop = round(px - sgn * 1.5 * atr, 2) if atr else round(px * (1 - sgn * 0.03), 2)
            sug_tgt = round(px + sgn * 2 * abs(px - sug_stop), 2)
        else:
            sug_stop = sug_tgt = 0.0
        with st.form("rm_check"):
            c = st.columns(4)
            entry = c[0].number_input("Entry ₹", 0.0, value=float(px or 0.0), step=0.05, format="%.2f")
            stop = c[1].number_input("Stop-loss ₹", 0.0, value=float(sug_stop), step=0.05, format="%.2f",
                                     help="Suggested: 1.5 × the stock's normal daily move")
            target = c[2].number_input("Target ₹", 0.0, value=float(sug_tgt), step=0.05, format="%.2f")
            qty = c[3].number_input("Shares (0 = suggest)", 0, 1_000_000, 0, 1)
            go_ = st.form_submit_button("Check this trade", type="primary")
        if go_ and symbol and entry > 0:
            res = RM.check_trade(rules, j, side, entry, stop or None, target or None,
                                 int(qty) or None, facts)
            st.session_state["_rm_last"] = {"res": res, "symbol": symbol, "side": side,
                                            "entry": entry, "stop": stop, "target": target,
                                            "qty": int(qty) or res["size"]["qty"]}
        last = st.session_state.get("_rm_last")
        if last and last["symbol"] == symbol:
            res = last["res"]
            color = {"ALLOWED": UP, "CAUTION": "#f59e0b", "BLOCKED": DOWN}[res["verdict"]]
            icon = {"ALLOWED": "✅", "CAUTION": "⚠️", "BLOCKED": "🛑"}[res["verdict"]]
            st.markdown(f"<div style='border-left:6px solid {color};padding:10px 16px;"
                        f"background:rgba(100,116,139,.08);border-radius:6px'>"
                        f"<div style='font-size:28px;font-weight:800;color:{color}'>{icon} "
                        f"{res['verdict']}</div><div>{last['side']} {last['symbol']} · "
                        f"{last['qty']} shares · max loss ₹{last['qty'] * abs(last['entry'] - last['stop']):,.0f}"
                        f"</div></div>", unsafe_allow_html=True)
            for ch in res["checks"]:
                mark = "✅" if ch["ok"] else ("❔" if ch["ok"] is None else ("🛑" if ch["hard"] else "⚠️"))
                st.markdown(f"{mark} **{ch['rule']}** — {ch['detail']}")
            if res["verdict"] == "BLOCKED":
                st.error("This trade breaks your rules, so it can't be logged. "
                         "Fix the red items or skip it.")
            else:
                m1, m2 = st.columns([1, 2])
                mode = m1.radio("Type", ["Paper", "Real"], horizontal=True, key="rm_mode")
                notes = m2.text_input("Why this trade? (setup / reason)", key="rm_notes")
                if st.button(f"📝 Log {last['side']} {last['symbol']} in journal"):
                    nj = RM.add_trade(j, last["symbol"], last["side"], last["qty"], last["entry"],
                                      last["stop"], last["target"] or None, mode, notes)
                    ok, err = rm_save_journal(nj, f"Open {last['side']} {last['symbol']}")
                    st.session_state.pop("_rm_last", None)
                    (st.success if ok else st.warning)(
                        "Logged and saved." if ok else f"Logged for this session, but saving failed: {err}")
                    st.rerun()

    with t_journal:
        jj = st.session_state["_rm_journal"]
        open_t = jj[jj["Status"] == "Open"]
        st.markdown(f"**Open trades ({len(open_t)})**")
        if open_t.empty:
            st.caption("No open trades.")
        else:
            st.dataframe(open_t[["id", "Opened", "Symbol", "Side", "Qty", "Entry", "Stop", "Target",
                                 "Mode", "Notes"]], hide_index=True, width="stretch")
            with st.form("rm_close"):
                c = st.columns([2, 1, 1])
                labels = {f"#{int(r.id)} {r.Side} {r.Symbol} @ {r.Entry:,.2f}": int(r.id)
                          for r in open_t.itertuples()}
                pick = c[0].selectbox("Close trade", list(labels))
                exit_px = c[1].number_input("Exit ₹", 0.0, step=0.05, format="%.2f")
                cost = c[2].number_input("Costs %", 0.0, 1.0, 0.1, 0.05,
                                         help="Brokerage + taxes, round trip")
                if st.form_submit_button("Close trade") and exit_px > 0:
                    nj = RM.close_trade(jj, labels[pick], exit_px, cost)
                    ok, err = rm_save_journal(nj, f"Close {pick}")
                    if not ok:
                        st.warning(f"Closed for this session, but saving failed: {err}")
                    st.rerun()
        closed = jj[jj["Status"] == "Closed"].sort_values("Closed", ascending=False)
        st.markdown(f"**Closed trades ({len(closed)})**")
        if not closed.empty:
            st.dataframe(closed[["id", "Opened", "Closed", "Symbol", "Side", "Qty", "Entry", "Exit",
                                 "PnL", "PnL %", "Mode", "Notes"]].style.format(precision=2, na_rep="—")
                         .map(lambda v: f"color:{UP if v > 0 else DOWN}" if isinstance(v, (int, float))
                              and not pd.isna(v) else "", subset=["PnL", "PnL %"]),
                         hide_index=True, width="stretch")
            st.download_button("Download journal (CSV)", jj.to_csv(index=False).encode(),
                               "my_trades.csv", "text/csv")

    with t_results:
        jj = st.session_state["_rm_journal"]
        o = RM.overall(jj)
        if not o.get("closed"):
            st.info("Results appear after you close your first trade.")
        else:
            k = st.columns(5)
            k[0].metric("Closed trades", o["closed"])
            k[1].metric("Win rate", f"{o['win_rate']:.0f}%")
            k[2].metric("Total P&L", f"₹{o['total_pnl']:,.0f}")
            k[3].metric("Avg win / loss", f"₹{o['avg_win'] or 0:,.0f} / ₹{o['avg_loss'] or 0:,.0f}")
            k[4].metric("Profit factor", fmt(o["profit_factor"]))
            if o["avg_win"] and o["avg_loss"] and o["avg_win"] < abs(o["avg_loss"]):
                st.warning("Your average loss is bigger than your average win — "
                           "keep stops tight and let winners reach the target.")
            mode = st.radio("Show", ["All", "Paper", "Real"], horizontal=True, key="rm_res_mode")
            sub = jj if mode == "All" else jj[jj["Mode"] == mode]
            a, b = st.columns(2)
            a.markdown("**By week**")
            a.dataframe(RM.summary(sub, "W"), hide_index=True, width="stretch")
            b.markdown("**By month**")
            b.dataframe(RM.summary(sub, "M"), hide_index=True, width="stretch")

    with t_rules:
        with st.form("rm_rules"):
            c = st.columns(3)
            cap = c[0].number_input("Trading capital ₹", 1000.0, 1e9, float(rules.capital), 1000.0)
            rp = c[1].number_input("Max loss per trade %", 0.1, 5.0, float(rules.risk_pct), 0.1)
            mrr = c[2].number_input("Min reward : risk", 0.5, 5.0, float(rules.min_reward_risk), 0.5)
            c = st.columns(3)
            mtd = c[0].number_input("Max trades a day", 1, 20, int(rules.max_trades_day))
            mld = c[1].number_input("Stop after losses a day", 1, 10, int(rules.max_losses_day))
            mlp = c[2].number_input("Pause if month down %", 1.0, 50.0, float(rules.monthly_loss_pct), 0.5)
            c = st.columns(3)
            mo = c[0].number_input("Max open positions", 1, 50, int(rules.max_open))
            rd = c[1].number_input("Avoid results within days", 0, 30, int(rules.results_days))
            tr = c[2].checkbox("Buys only in uptrends", rules.require_trend)
            mk = c[2].checkbox("Buys only when NIFTY isn't falling", rules.require_market)
            if st.form_submit_button("Save rules"):
                nr = RM.RiskRules(capital=cap, risk_pct=rp, max_trades_day=int(mtd),
                                  max_losses_day=int(mld), monthly_loss_pct=mlp, max_open=int(mo),
                                  min_reward_risk=mrr, results_days=int(rd),
                                  require_trend=tr, require_market=mk)
                st.session_state["_rm_rules"] = nr
                try:
                    STORE.save_rules(nr.to_dict())
                    st.success("Rules saved.")
                except Exception as e:  # noqa: BLE001
                    st.warning(f"Rules applied for this session, but saving failed: {e}")
        st.caption("Tip: change rules only on weekends, never in the middle of a losing day.")


# ------------------------------------------------------------------------ main

{"Market overview": page_overview,
 "Stock analysis": page_stock,
 "🛡️ Risk Manager": page_risk,
 "⭐ Pro signals": page_pro,
 "⏱️ Intraday levels": page_intraday,
 "Buy / Sell signals": page_signals,
 "Screener": page_screener}[page]()

st.divider()
st.caption("⚠️ For learning and research only. Not investment advice. "
           "Prices may be delayed; verify before trading.")
