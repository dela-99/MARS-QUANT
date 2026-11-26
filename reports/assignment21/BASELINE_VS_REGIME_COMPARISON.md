# Baseline vs Regime-Filtered Comparison
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Date:** 2026-11-25T14:11:34.724150+00:00

## Performance Comparison

| Metric | Unconditional Baseline (Model A) | Regime-Filtered (Model B) | Difference |
|--------|----------------------------------|---------------------------|------------|
| Trades | 331 | 334 | +3 |
| Win Rate (net) | 0.0% | 0.0% | +0.00% |
| Expectancy (net) | $-30.15 | $-29.88 | $+0.27 |
| Profit Factor (net) | 0.00 | 0.00 | +0.00 |
| Sharpe | -4.40 | -4.13 | +0.28 |
| Max DD | -99.80% | -99.80% | -0.00% |
| Total Net P&L | $-9980.15 | $-9980.38 | $-0.22 |

## Regime Filter Effectiveness
- Base Signals (Model A trades): 331
- Regime-Filtered Signals (Model B trades): 334
- Signals Filtered Out: 77730
- Filter Rate: 23483.4%

## Cost Sensitivity Comparison
Both models tested at 1.0×, 1.5×, 2.0× spread multiplier.
Regime-filtered model should maintain positive expectancy at higher costs.

## Statistical Significance
See FC005_2_INTERACTION_REGRESSION.md and NULL_PERMUTATION_ANALYSIS.md