# 📈 Indian Market Analyser

A free dashboard for analysing NSE/BSE stocks, built with Python + Streamlit.

## Features

| Page | What it does |
|---|---|
| **Buy / Sell signals** | BUY / SELL / NO TRADE call with entry, stop-loss, targets and risk:reward · buy zone & sell zone · position-size calculator · chart markers · 5-year backtest of every strategy on that stock · scanner for fresh signals |
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

## Symbols

Use NSE codes: `INFY`, `RELIANCE`, `HDFCBANK`, `M&M`, `BAJAJ-AUTO`.
The app adds `.NS` (NSE) or `.BO` (BSE) for Yahoo Finance.
Stock lists for the screener are in `data.py` (`UNIVERSES`) — edit them when index constituents change.

## Project layout

```
app.py          Streamlit pages and charts
analysis.py     Pivots, swing levels, SMA/EMA, RSI, MACD, Bollinger, ATR, signal score
data.py         Yahoo Finance data, stock lists, fundamentals
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
