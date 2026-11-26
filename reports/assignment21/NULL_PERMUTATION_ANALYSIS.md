# Null Permutation Analysis Report
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Date:** 2026-11-25T14:11:34.724150+00:00

## Test Design
- Null Hypothesis: Regime filter labels are exchangeable; observed expectancy could arise by chance
- Permutation Unit: Trade P&L values (equivalent to randomizing which trades occur)
- What is Preserved: Trade P&L distribution, number of trades
- What is Randomized: Assignment of P&L values to trade positions
- Random Seed: 20261126
- Repetitions: 10,000

## Results
- Observed Expectancy: $-29.88
- Null Distribution Mean: $-29.88
- Null Distribution Std: $0.00
- p-value (one-sided): 0.1305

## Null Distribution Percentiles
| Percentile | Value |
|------------|-------|
| p5 | $-29.88 |
| p50 | $-29.88 |
| p95 | $-29.88 |
| p975 | $-29.88 |
| p99 | $-29.88 |

## Verdict: FAIL_TO_REJECT_NULL
- Cannot reject null that regime filter is random

## Limitations
- Exchangeability assumption: requires that trade P&L values are i.i.d. under null
- Serial dependence in trades may violate exchangeability
- This test complements (not replaces) the interaction regression