# Pro engine research report

Generated 2026-11-25T08:27+00:00 UTC · 109 NSE stocks · daily data · long only · costs 0.3% per round trip included.

Tuned on signals **before 2021-01-01**, judged on signals **after** (the out-of-sample period was never used for choosing anything).

Rules chosen from 24 combinations (in-sample only): stop 2.0×ATR, target 2.0R, breakeven after offR, breakouts on, max hold 25 days. All combinations: reports/pro_grid.csv.

## Result at the chosen minimum score (45)

- **Out-of-sample (real test):** 1633 trades · win 43% · avg +0.57% net · +0.08R · PF 1.20
- In-sample (tuning): 1846 trades · win 42% · avg +0.26% net · +0.05R · PF 1.08
- All setups, no score filter, out-of-sample: 1638 trades · win 42% · avg +0.57% net · +0.08R · PF 1.20
- NIFTY 50 buy-and-hold over the same period: 10.8% a year

Profit factor = total profit ÷ total loss. Above 1.0 makes money; 1.3+ is good; 1.6+ is strong.

## Out-of-sample by year

| Year | Result |
|---|---|
| 2021 | 400 trades · win 40% · avg +0.51% net · +0.03R · PF 1.15 |
| 2022 | 205 trades · win 39% · avg +0.04% net · -0.03R · PF 1.01 |
| 2023 | 369 trades · win 52% · avg +1.59% net · +0.33R · PF 1.80 |
| 2024 | 378 trades · win 45% · avg +1.09% net · +0.15R · PF 1.38 |
| 2025 | 191 trades · win 41% · avg -0.03% net · +0.04R · PF 0.99 |
| 2026 | 90 trades · win 18% · avg -3.10% net · -0.65R · PF 0.28 |

## Out-of-sample by setup and score

| Setup | Score | Trades | Win % | Avg net % | Avg R | Profit factor |
|---|---|---|---|---|---|---|
| Breakout | 0-50 | 7 | 29 | -1.55 | -0.20 | 0.55 |
| Breakout | 50-65 | 51 | 47 | +0.34 | +0.13 | 1.13 |
| Breakout | 65-80 | 202 | 37 | -0.26 | -0.04 | 0.92 |
| Breakout | 80-100 | 638 | 43 | +0.60 | +0.08 | 1.20 |
| Pullback | 0-50 | 24 | 46 | +1.36 | +0.22 | 1.66 |
| Pullback | 50-65 | 241 | 41 | +0.55 | +0.07 | 1.21 |
| Pullback | 65-80 | 355 | 43 | +0.36 | +0.05 | 1.12 |
| Pullback | 80-100 | 120 | 52 | +2.44 | +0.37 | 1.91 |
| All | 0-50 | 31 | 42 | +0.70 | +0.13 | 1.30 |
| All | 50-65 | 292 | 42 | +0.51 | +0.08 | 1.20 |
| All | 65-80 | 557 | 40 | +0.14 | +0.02 | 1.05 |
| All | 80-100 | 758 | 44 | +0.89 | +0.13 | 1.31 |

## In-sample by setup and score

| Setup | Score | Trades | Win % | Avg net % | Avg R | Profit factor |
|---|---|---|---|---|---|---|
| Breakout | 0-50 | 13 | 31 | -2.89 | -0.43 | 0.24 |
| Breakout | 50-65 | 94 | 41 | +0.40 | +0.05 | 1.13 |
| Breakout | 65-80 | 273 | 41 | +0.24 | +0.02 | 1.08 |
| Breakout | 80-100 | 646 | 43 | +0.09 | +0.04 | 1.03 |
| Pullback | 0-50 | 37 | 46 | +1.68 | +0.32 | 1.59 |
| Pullback | 50-65 | 271 | 41 | +0.12 | +0.07 | 1.04 |
| Pullback | 65-80 | 377 | 42 | +0.17 | +0.03 | 1.05 |
| Pullback | 80-100 | 152 | 46 | +1.20 | +0.14 | 1.38 |
| All | 0-50 | 50 | 42 | +0.49 | +0.12 | 1.16 |
| All | 50-65 | 365 | 41 | +0.19 | +0.06 | 1.06 |
| All | 65-80 | 650 | 41 | +0.20 | +0.02 | 1.06 |
| All | 80-100 | 798 | 44 | +0.30 | +0.06 | 1.09 |

## Caveats

- The stock list is today's large caps, so stocks that collapsed or were removed in the past are missing (survivorship bias) — real results may be lower.
- Entries at the next day's open; gaps and slippage are approximated by the cost figure.
- Past results do not guarantee future results.