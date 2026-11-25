"""Susthira Market Analyser — Indian stock market analysis dashboard.

Run locally:  streamlit run app.py
"""

from __future__ import annotations

import hashlib

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import analysis as A
import data as D

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
    return D.history(ticker, period)


def get_many(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    if st.session_state.get("demo"):
        return {t: demo_frame(t) for t in tickers}
    return D.history_many(tuple(tickers), period)


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
quick = st.sidebar.text_input("🔍 Analyse a stock", placeholder="e.g. INFY, RELIANCE")
if quick.strip() and quick != st.session_state.get("_last_quick"):
    st.session_state["_last_quick"] = quick
    st.session_state["symbol"] = quick.strip().upper()
    st.session_state["page"] = "Stock analysis"
page = st.sidebar.radio("Go to", ["Stock analysis", "Market overview", "Screener"], key="page")
st.sidebar.toggle("Demo data (offline)", key="demo",
                  help="Use generated sample prices when live data is unavailable.")
st.sidebar.caption("Data: Yahoo Finance (may be delayed ~15 min). "
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

    m = st.columns(5)
    m[0].metric("Close", fmt(last["Close"], prefix="₹"),
                f"{(last['Close'] / prev['Close'] - 1) * 100:+.2f}%")
    m[1].metric("Day range", f"{last['Low']:,.1f} – {last['High']:,.1f}")
    year = d.tail(252)
    hi, lo = year["High"].max(), year["Low"].min()
    m[2].metric("52W range", f"{lo:,.0f} – {hi:,.0f}",
                f"{(last['Close'] / hi - 1) * 100:.1f}% from high", delta_color="off")
    m[3].metric("RSI (14)", fmt(last["RSI"], 1))
    m[4].metric("ATR (14)", fmt(last["ATR"], 1, prefix="₹"),
                f"{last['ATR'] / last['Close'] * 100:.1f}% daily move", delta_color="off")

    tab_report, tab_levels, tab_chart, tab_tech, tab_fund = st.tabs(
        ["📝 Full analysis", "🎯 Support & resistance", "📊 Chart",
         "🧭 Technical signal", "🏢 Fundamentals"])

    # --- written report
    with tab_report:
        rep = A.stock_report(d, fund)
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


# ------------------------------------------------------------------------ main

{"Market overview": page_overview,
 "Stock analysis": page_stock,
 "Screener": page_screener}[page]()

st.divider()
st.caption("⚠️ For learning and research only. Not investment advice. "
           "Prices may be delayed; verify before trading.")
