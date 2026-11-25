# M.A.R.S. Session Momentum Monte Carlo Report
**Strategy:** XAU-SESSION-MOM-001
**Trades Source:** reports/programme_01/session_momentum_001/oos/oos_trades.csv
**Config:** 10,000 sims, seed=20261125, equity=$10000
**Date:** 2026-11-25T02:06:17.664469+00:00

## Assumptions (Recorded)
- i.i.d. trade outcomes (known false for session momentum - upper bound on robustness)
- Position sizing proportional to equity
- Costs embedded in observed net P&L (not re-sampled)
- No regime/clustering modelled

## Reshuffle Experiment (Sequence Risk)
- Observed Terminal Equity: $19.69
- Simulated Mean: $2830.63 (σ=$0.00)
- Observed Max DD: -99.88%
- Simulated Mean Max DD: 76.62% (σ=4.66%)

### Percentiles (Terminal Equity)
- p1: $2830.63
- p5: $2830.63
- p10: $2830.63
- p25: $2830.63
- p50: $2830.63
- p75: $2830.63
- p90: $2830.63
- p95: $2830.63
- p99: $2830.63

### Percentiles (Max Drawdown)
- p1: 71.69%
- p5: 71.69%
- p10: 71.69%
- p25: 71.69%
- p50: 75.96%
- p75: 80.93%
- p90: 83.49%
- p95: 84.29%
- p99: 84.90%

## Resample Experiment (Outcome Dispersion)
- Observed Terminal Equity: $19.69
- Simulated Mean: $3624.24 (σ=$3873.83)
- Observed Max DD: -99.88%
- Simulated Mean Max DD: 76.90% (σ=9.48%)

## Random Signal Baseline
- Mean Terminal Equity: $2830.63
- Mean Sharpe: -17.77
- Mean Max DD: 76.61%

## Falsification Criteria (MC)
- observed_dd_gt_p95_reshuffle: ✅ PASS
- observed_terminal_lt_p05_resample: ❌ FAIL (Falsified)

**Overall Verdict: REJECTED (MC)**
*Observed DD > p95 of reshuffle = sequence-dependent. Observed terminal < p05 of resample = outcome unlikely under i.i.d.*