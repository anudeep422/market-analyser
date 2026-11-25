# Pro engine research report

Generated 2026-11-25T08:23+00:00 UTC · 109 NSE stocks · daily data · long only · costs 0.3% per round trip included.

Tuned on signals **before 2021-01-01**, judged on signals **after** (the out-of-sample period was never used for choosing anything).

## Result at the chosen minimum score (80)

- **Out-of-sample (real test):** 858 trades · win 29% · avg +0.11% net · -0.00R · PF 1.05
- In-sample (tuning): 912 trades · win 30% · avg +0.03% net · -0.00R · PF 1.01
- All setups, no score filter, out-of-sample: 1789 trades · win 31% · avg +0.14% net · +0.01R · PF 1.07
- NIFTY 50 buy-and-hold over the same period: 10.8% a year

Profit factor = total profit ÷ total loss. Above 1.0 makes money; 1.3+ is good; 1.6+ is strong.

## Out-of-sample by year

| Year | Result |
|---|---|
| 2021 | 242 trades · win 31% · avg +0.39% net · +0.05R · PF 1.16 |
| 2022 | 78 trades · win 26% · avg -0.22% net · -0.08R · PF 0.90 |
| 2023 | 189 trades · win 32% · avg +0.39% net · +0.10R · PF 1.23 |
| 2024 | 236 trades · win 31% · avg +0.11% net · -0.01R · PF 1.05 |
| 2025 | 72 trades · win 26% · avg -0.18% net · -0.06R · PF 0.90 |
| 2026 | 41 trades · win 10% · avg -1.73% net · -0.48R · PF 0.30 |

## Out-of-sample by setup and score

| Setup | Score | Trades | Win % | Avg net % | Avg R | Profit factor |
|---|---|---|---|---|---|---|
| Breakout | 0-50 | 7 | 14 | -1.42 | -0.38 | 0.33 |
| Breakout | 50-65 | 57 | 28 | -0.39 | -0.08 | 0.83 |
| Breakout | 65-80 | 208 | 29 | -0.03 | -0.04 | 0.99 |
| Breakout | 80-100 | 733 | 28 | -0.10 | -0.04 | 0.95 |
| Pullback | 0-50 | 24 | 38 | +1.11 | +0.21 | 1.62 |
| Pullback | 50-65 | 259 | 36 | +0.43 | +0.12 | 1.21 |
| Pullback | 65-80 | 376 | 32 | +0.17 | +0.01 | 1.07 |
| Pullback | 80-100 | 125 | 38 | +1.35 | +0.24 | 1.65 |
| All | 0-50 | 31 | 32 | +0.54 | +0.08 | 1.29 |
| All | 50-65 | 316 | 34 | +0.29 | +0.08 | 1.13 |
| All | 65-80 | 584 | 31 | +0.10 | -0.01 | 1.04 |
| All | 80-100 | 858 | 29 | +0.11 | -0.00 | 1.05 |

## In-sample by setup and score

| Setup | Score | Trades | Win % | Avg net % | Avg R | Profit factor |
|---|---|---|---|---|---|---|
| Breakout | 0-50 | 13 | 23 | -1.25 | -0.24 | 0.49 |
| Breakout | 50-65 | 95 | 26 | -0.25 | -0.06 | 0.90 |
| Breakout | 65-80 | 302 | 24 | -0.46 | -0.15 | 0.80 |
| Breakout | 80-100 | 756 | 28 | -0.14 | -0.03 | 0.94 |
| Pullback | 0-50 | 38 | 39 | +1.08 | +0.27 | 1.51 |
| Pullback | 50-65 | 289 | 32 | +0.22 | +0.08 | 1.10 |
| Pullback | 65-80 | 397 | 28 | -0.25 | -0.05 | 0.90 |
| Pullback | 80-100 | 156 | 37 | +0.83 | +0.12 | 1.32 |
| All | 0-50 | 51 | 35 | +0.49 | +0.14 | 1.22 |
| All | 50-65 | 384 | 31 | +0.11 | +0.05 | 1.05 |
| All | 65-80 | 699 | 26 | -0.34 | -0.09 | 0.86 |
| All | 80-100 | 912 | 30 | +0.03 | -0.00 | 1.01 |

## Caveats

- The stock list is today's large caps, so stocks that collapsed or were removed in the past are missing (survivorship bias) — real results may be lower.
- Entries at the next day's open; gaps and slippage are approximated by the cost figure.
- Past results do not guarantee future results.