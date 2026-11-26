# Candidate 005 IS Research Report
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Data:** M5 v1.2.0 / H1 v1.2.0
**IS Period:** 2021-10-01 to 2024-12-31
**Date:** 2026-11-25T14:11:34.724150+00:00

## Model A: Unconditional Baseline (XAU-SESSION-MOM-001)
- Trades: 331
- Win Rate (net): 0.0%
- Expectancy (net): $-30.15
- Profit Factor (net): 0.00
- Sharpe: -4.40
- Max DD: -99.80%

## Model B: Regime-Filtered Candidate 005
- Trades: 334
- Win Rate (net): 0.0%
- Expectancy (net): $-29.88
- Profit Factor (net): 0.00
- Sharpe: -4.13
- Max DD: -99.80%
- Base Signals: 118351
- Regime Filtered Out: 77730

## Model C: Null Permutation Test
- Permutations: 10,000
- Observed Expectancy: $-29.88
- Null Mean: $-29.88
- p-value: 0.1305
- Verdict: FAIL_TO_REJECT_NULL

## FC-005-2 Interaction Regression
- β_3: -21.7912
- p (one-sided): 1.0000
- PASS: False

## Falsification Criteria
- fc_005_1_expectancy_positive: ❌ FAIL
- fc_005_2_interaction: ❌ FAIL
- fc_005_3_oos_expectancy: ⏳ NOT RUN
- fc_005_4_cost_sensitivity: ⏳ NOT RUN
- min_trades_is: ✅ PASS
- min_trades_oos: ⏳ NOT RUN
- max_dd_is: ❌ FAIL
- min_expectancy_is: ❌ FAIL

**Overall Verdict: REJECTED — NO DEFENSIBLE EDGE**

## Sensitivity Analysis
Pre-registered one-factor-at-a-time from baseline:

### spread_multiplier (baseline: 1.0)
- spread_multiplier=1.0: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%
- spread_multiplier=1.5: trades=220, expectancy=$-45.36, PF=0.00, Sharpe=-3.61, MaxDD=-99.80%
- spread_multiplier=2.0: trades=164, expectancy=$-60.86, PF=0.00, Sharpe=-3.12, MaxDD=-99.81%

### vol_percentile_threshold (baseline: 40.0)
- vol_percentile_threshold=30: trades=335, expectancy=$-29.79, PF=0.00, Sharpe=-3.86, MaxDD=-99.80%
- vol_percentile_threshold=40: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%
- vol_percentile_threshold=50: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.44, MaxDD=-99.80%

### spread_percentile_threshold (baseline: 40.0)
- spread_percentile_threshold=30: trades=136, expectancy=$-66.47, PF=0.03, Sharpe=-1.50, MaxDD=-93.32%
- spread_percentile_threshold=40: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%
- spread_percentile_threshold=50: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%

### fomc_filter (baseline: True)
- fomc_filter=True: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%
- fomc_filter=False: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%

### sl_points (baseline: 200)
- sl_points=150: trades=260, expectancy=$-38.40, PF=0.00, Sharpe=-3.80, MaxDD=-99.85%
- sl_points=200: trades=334, expectancy=$-29.88, PF=0.00, Sharpe=-4.13, MaxDD=-99.80%
- sl_points=250: trades=458, expectancy=$-21.73, PF=0.23, Sharpe=-1.44, MaxDD=-99.61%
- sl_points=300: trades=458, expectancy=$-21.53, PF=0.31, Sharpe=-1.29, MaxDD=-98.95%