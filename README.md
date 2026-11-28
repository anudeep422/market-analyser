# 📈 Indian Market Analyser

A free dashboard for analysing NSE/BSE stocks, built with Python + Streamlit.

## Features

| Page | What it does |
|---|---|
| **Buy / Sell signals** | BUY / SELL / NO TRADE call with entry, stop-loss, targets and risk:reward · buy zone & sell zone · position-size calculator · chart markers · 5-year backtest of every strategy on that stock · scanner for fresh signals |
| **🛡️ Risk Manager** | Checks every trade against your rules before you take it — stop-loss, max 1% loss with exact share count, reward:risk, trend, NIFTY, setup score, results date, daily trade/loss limits, monthly loss pause, open positions — and gives ALLOWED / CAUTION / BLOCKED. Trade journal (paper/real) with weekly and monthly results, saved to the repo's `data` branch |
| **⭐ Pro signals** | Long-only, quality-filtered setups (market trend + relative strength + trend + volume + room), 0–100 score with breakdown, confidence from a ~10-year test on ~110 stocks with costs, today's pro list, research report |
| **⏱️ Intraday levels** | Live 5-minute chart (refreshes every minute) with VWAP, EMA 9/20, opening range, previous-day high/low/close, pivots, RSI and volume; plain-language picture of the day; levels table. Analysis only — the intraday breakout signals lost money in a 60-day test (reports/intraday_research.md) |
| **Market overview** | NIFTY 50, Bank Nifty, Sensex, Nifty IT, India VIX · top gainers/losers · advance/decline · signal breakdown |
| **Stock analysis** (opens first) | Type any NSE/BSE stock — in the sidebar search or on the page |
| ↳ Full analysis | Written report: verdict, performance (1W–1Y), trend, momentum, levels, fundamentals, overall view, what to watch · downloadable |
| ↳ Support & resistance | Pivot levels (classic / Fibonacci / Camarilla) for the next session + swing-based zones |
| ↳ Chart | Candlesticks with SMA 20/50/200, Bollinger bands, pivot lines, volume, RSI, MACD |
| ↳ Technical signal | Score from −100 (Strong Sell) to +100 (Strong Buy) with the reasons behind it |
| ↳ Fundamentals | Market cap, P/E, P/B, EPS, ROE, debt/equity, dividend yield, margins, growth |
| **Screener** | Scan NIFTY 50, IT, Banks, Pharma, Auto, FMCG or your own list · filter by RSI, signal, trend, nearness to support · CSV download |

**Demo data** switch in the sidebar runs the whole app on generated prices when there's no internet.

## Run on your computer

```bash
git clone https://github.com/anudeep422/market-analyser.git
cd market-analyser
pip install -r requirements.txt
streamlit run app.py
```

It opens at http://localhost:8501.

## Put it online for free (Streamlit Community Cloud)

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** → choose this repo, branch `main`, file `app.py`.
3. Click **Deploy**. In a minute or two you get a link like `https://<name>.streamlit.app`.

Every push to `main` updates the live app automatically.

## Live prices with Paytm Money (optional, free)

Yahoo gives the history; Paytm Money gives today's live price.

1. Create an app at developer.paytmmoney.com (Redirect URL = this app's `.streamlit.app` link).
2. In Streamlit → your app → ⋮ → Settings → **Secrets**, add:
   ```toml
   [paytm]
   api_key = "YOUR_API_KEY"
   api_secret = "YOUR_API_SECRET"
   ```
3. Each trading day, press **Login to Paytm Money** in the sidebar. The sidebar shows 🟢 when live prices are on.

Keep the Streamlit app private — anyone who can open it would use your Paytm login for prices.

## Saving your trade journal (Risk Manager)

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Repository access: **Only select repositories** → `market-analyser`. Permissions → Repository → **Contents: Read and write**. Generate and copy it.
3. Streamlit → your app → ⋮ → Settings → **Secrets**, add below the Paytm section:
   ```toml
   [github]
   token = "github_pat_..."
   ```
Trades and rules are saved on a separate `data` branch, so saving never restarts the app.

## Symbols

Use NSE codes: `INFY`, `RELIANCE`, `HDFCBANK`, `M&M`, `BAJAJ-AUTO`.
The app adds `.NS` (NSE) or `.BO` (BSE) for Yahoo Finance.
Stock lists for the screener are in `data.py` (`UNIVERSES`) — edit them when index constituents change.

## Project layout

```
app.py          Streamlit pages and charts
analysis.py     Pivots, swing levels, SMA/EMA, RSI, MACD, Bollinger, ATR, signal score
data.py         Yahoo Finance data, stock lists, fundamentals
paytm.py        Paytm Money login + live quotes (overrides today's bar)
pro.py          Pro engine: filters, score, cost-aware backtest
scripts/        pro_research.py — research (10y, ~110 stocks) and daily scan, run by GitHub Actions
signals.py      Strategy plugins (pullback, breakout, MACD, MA cross, Bollinger), trade plans, backtester
tests/          Unit tests for analysis.py  (python -m pytest)
```

## Adding your own strategy

In `signals.py`, write a function that returns +1 (buy), -1 (sell) or 0 per day and decorate it:

```python
@strategy("rsi30", "RSI 30 bounce", "Buy when RSI crosses up through 30.")
def rsi30(d):
    return _combine(_cross_up(d["RSI"], 30), _cross_down(d["RSI"], 70))
```

It appears automatically in the signal page, scanner and backtest.

## Ideas for next versions

- Option chain + PCR and max pain (NSE)
- Price alerts on Telegram/WhatsApp
- Backtesting a strategy on past data
- Portfolio tracker with P&L
- Telugu language mode

## Disclaimer

For learning and research only. Not investment advice. Yahoo Finance data can be delayed
or incomplete — verify prices before trading.
