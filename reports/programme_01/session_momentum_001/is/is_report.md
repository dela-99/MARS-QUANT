# M.A.R.S. Session Momentum IS Research Report
**Strategy:** XAU-SESSION-MOM-001
**Hypothesis:** CSM-001
**Data:** M5 v1.2.0 / H1 v1.2.0
**Date:** 2026-11-25T02:02:38.811825+00:00

## Split
- Train: 3031 sessions (70%)
- Val:   649 sessions (15%)
- Test:  651 sessions (15%)

## Baseline Configuration (Paper 12 - Frozen)
- signal_mode: direction
- threshold: 0.0
- risk_fraction: 0.01
- sl_points: 200
- spread_multiplier: 1.0
- commission_per_lot: 0.0
- slippage_points: 0.0
- block_fomc: False
- block_high_vol: False
- block_high_spread: False
- starting_equity: 10000.0
- symbol: XAUUSDm
- timeframe: m5

## Train Metrics (In-Sample)
- Trades: 308
- Win Rate (net): 0.0%
- Expectancy (net): $-32.40
- Profit Factor (net): 0.00
- Sharpe: -4.26
- Max DD: -99.80%

## Validation Sensitivity (One-Factor-at-a-Time)

### sl_points (baseline: 200)
- sl_points=200: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%
- sl_points=300: trades=368, expectancy=$-18.75, PF=0.65, Sharpe=-0.43, MaxDD=-97.16%
- sl_points=500: trades=368, expectancy=$-1.13, PF=0.99, Sharpe=-0.03, MaxDD=-88.28%

### spread_multiplier (baseline: 1.0)
- spread_multiplier=1.0: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%
- spread_multiplier=1.5: trades=281, expectancy=$-35.52, PF=0.00, Sharpe=-2.36, MaxDD=-99.80%
- spread_multiplier=2.0: trades=209, expectancy=$-47.75, PF=0.00, Sharpe=-2.05, MaxDD=-99.80%

### risk_fraction (baseline: 0.01)
- risk_fraction=0.01: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%

### signal_mode (baseline: direction)
- signal_mode=direction: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%

### threshold (baseline: 0.0)
- threshold=0.0: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%

### block_fomc (baseline: False)
- block_fomc=False: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%
- block_fomc=True: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%

### block_high_vol (baseline: False)
- block_high_vol=False: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%
- block_high_vol=True: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%

### block_high_spread (baseline: False)
- block_high_spread=False: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%
- block_high_spread=True: trades=368, expectancy=$-25.85, PF=0.09, Sharpe=-0.46, MaxDD=-98.74%

## Test Metrics (Out-of-Sample)
- Trades: 287
- Win Rate (net): 0.3%
- Expectancy (net): $-34.77
- Profit Factor (net): 0.47
- Sharpe: -1.42
- Max DD: -99.88%

## Baselines
- buy_and_hold: return=-3.76%, equity=9624.50
- flat: return=0.00%, equity=10000.00
- random_signal: return=N/A, equity=N/A

## Falsification Criteria (Pre-Registered)
- net_expectancy_positive: ❌ FAIL
- net_profit_factor_gt_1: ❌ FAIL
- net_sharpe_positive: ❌ FAIL
- max_drawdown_lt_20pct: ❌ FAIL
- trade_count_ge_30: ✅ PASS

**Overall Verdict: REJECTED**