# Intraday plan — 60-day test

Generated 2026-11-26T02:03+00:00 UTC · 50 NIFTY 50 stocks · 5-minute candles · 2026-08-27 to 2026-11-25 (60 trading days) · costs 0.15% per round trip included.

Rules: opening-range breakout confirmed by VWAP, EMA 9/20, RSI and volume, with NIFTY on the same side of its VWAP; exit by 15:10.

Settings chosen on the first half (before 2026-10-12), judged on the second half.
Chosen: target 1.5R, breakeven at 1.0R, shorts off.

## Result

- **Second half (real test):** 793 trades over 30 days · win 37% · avg -0.126% net · -0.46R · PF 0.49
- First half (tuning): 621 trades over 30 days · win 30% · avg -0.190% net · -0.67R · PF 0.29
- Profitable days in the second half: 7%

## Second half by side

- BUY: 793 trades over 30 days · win 37% · avg -0.126% net · -0.46R · PF 0.49

## Second half by signal hour

- 09:00 — 257 trades over 28 days · win 44% · avg -0.075% net · -0.24R · PF 0.70
- 10:00 — 193 trades over 29 days · win 29% · avg -0.192% net · -0.67R · PF 0.32
- 11:00 — 157 trades over 29 days · win 39% · avg -0.119% net · -0.49R · PF 0.46
- 12:00 — 89 trades over 21 days · win 31% · avg -0.175% net · -0.67R · PF 0.29
- 13:00 — 56 trades over 21 days · win 41% · avg -0.119% net · -0.48R · PF 0.46
- 14:00 — 41 trades over 18 days · win 39% · avg -0.064% net · -0.33R · PF 0.60

## All settings tried

| Target R | Breakeven R | Shorts | First half | Second half |
|---|---|---|---|---|
| 1.5 | 0.0 | True | 1431 trades over 30 days · win 40% · avg -0.149% net · -0.60R · PF 0.39 | 1417 trades over 30 days · win 43% · avg -0.131% net · -0.49R · PF 0.48 |
| 1.5 | 0.0 | False | 621 trades over 30 days · win 35% · avg -0.191% net · -0.68R · PF 0.32 | 793 trades over 30 days · win 42% · avg -0.132% net · -0.48R · PF 0.50 |
| 1.5 | 1.0 | True | 1431 trades over 30 days · win 34% · avg -0.151% net · -0.60R · PF 0.35 | 1417 trades over 30 days · win 38% · avg -0.127% net · -0.48R · PF 0.46 |
| 1.5 | 1.0 | False | 621 trades over 30 days · win 30% · avg -0.190% net · -0.67R · PF 0.29 | 793 trades over 30 days · win 37% · avg -0.126% net · -0.46R · PF 0.49 |
| 2.0 | 0.0 | True | 1431 trades over 30 days · win 35% · avg -0.141% net · -0.56R · PF 0.46 | 1417 trades over 30 days · win 38% · avg -0.114% net · -0.43R · PF 0.58 |
| 2.0 | 0.0 | False | 621 trades over 30 days · win 30% · avg -0.190% net · -0.68R · PF 0.37 | 793 trades over 30 days · win 37% · avg -0.116% net · -0.43R · PF 0.59 |
| 2.0 | 1.0 | True | 1431 trades over 30 days · win 28% · avg -0.144% net · -0.57R · PF 0.41 | 1417 trades over 30 days · win 32% · avg -0.114% net · -0.43R · PF 0.54 |
| 2.0 | 1.0 | False | 621 trades over 30 days · win 23% · avg -0.190% net · -0.68R · PF 0.31 | 793 trades over 30 days · win 30% · avg -0.117% net · -0.44R · PF 0.54 |

## Caveats

- 60 days is a short sample: one market mood can dominate. Treat this as a rough check.
- Fills assume the next candle's open; real slippage on fast breakouts can be worse.
- Yahoo's 5-minute volume for NSE is approximate.