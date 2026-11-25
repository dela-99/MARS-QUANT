# Assignment 14B — Reconciliation Report

**Date:** 2026-11-25  
**Strategy:** XAU-MTF-DONCHIAN-001  
**Scope:** Forensic reconciliation of Assignment 14 backtest, Monte Carlo, and reported metrics  

---

## Executive Summary

The reconciliation uncovers a **critical discrepancy** between the Assignment 14 summary narrative and the actual computational outputs:

| Reported in Summary | Actual in Artifacts |
|---------------------|---------------------|
| "OOS trades: 3" | **2,389 OOS trades** |
| "OOS net P&L: -$73.20" | **OOS net P&L: -$1,980.51** |
| "Monte Carlo: skipped (insufficient OOS trades)" | **Monte Carlo: RAN with 2,389 trades, 2,000 simulations** |
| "IS net return: -47.6%" | **IS net return: -99.14%** (equity dropped from $10,000 to $86.46) |

**The Monte Carlo charts showing ~2,400 steps are correctly generated from the actual OOS trade series (2,389 trades), not from 3 trades.** The summary narrative was incorrect; the computational pipeline ran correctly.

**Final research decision unchanged: REJECT — NO DEFENSIBLE EDGE**  
Both in-sample (-99.1% return, PF 0.54, Sharpe -2.98) and out-of-sample (-19.8% return, PF 0.98, Sharpe 0.06) results are unprofitable. The strategy has no edge.

---

## A. Evidence Inspection — File Inventory

| File | Status | Key Findings |
|------|--------|--------------|
| `reports/assignment14/assignment14_results.json` | ✅ Exists | Complete machine-readable run record |
| `reports/assignment14/ledger/trades_in_sample.csv` | ✅ Exists | 2,226 trades, 2021-07-19 → 2024-09-10 |
| `reports/assignment14/ledger/trades_out_of_sample.csv` | ✅ Exists | **2,389 trades**, 2025-01-02 → 2026-10-09 |
| `reports/assignment14/ledger/equity_curve_in_sample.csv` | ✅ Exists | 244,470 bars, $10,000 → $86.46 |
| `reports/assignment14/ledger/equity_curve_out_of_sample.csv` | ✅ Exists | 125,502 bars, $10,000 → $8,019.49 |
| `reports/assignment14/monte_carlo_equity_fan.png` | ✅ Exists | Generated from 2,389 OOS trades |
| `reports/assignment14/monte_carlo_distributions.png` | ✅ Exists | Generated from 2,389 OOS trades |
| `mars/apps/research_lab/xau_mtf_donchian_montecarlo.py` | ✅ Inspected | Lines 246-268: MC runs if `len(oos_tf) >= 20` |
| `research/assignment14/run_assignment14.py` | ✅ Inspected | Lines 247-268: Uses `oos_res.trades_frame()` for MC input |

---

## B. Trade Count & Data Provenance Reconciliation

### Trace: Source → Input → Calculation → Output → Chart

```
M5/H1 v1.2.0 datasets (369,972 M5 bars, 30,898 H1 bars)
    │
    ├─► IS window (2021-01-01 → 2025-01-01) ──► run_window() ──► is_res (2,226 trades)
    │       │
    │       └─► parameter_comparison() ──► 9 configs tested, all unprofitable
    │       └─► frozen config = baseline (Donchian=20, ATR=2.0)
    │
    └─► OOS window (2025-01-01 → 2026-10-09) ──► run_window() ──► oos_res (2,389 trades)
            │
            ├─► oos_res.trades_frame() ──► 2,389 net_pnl values ──► Monte Carlo input
            │       │
            │       ├─► run_reshuffle() ──► 2,000 permutations ──► sequence risk fan chart
            │       └─► run_resample() ──► 2,000 bootstrap samples ──► outcome dispersion fan chart
            │
            ├─► oos_res.equity_curve ──► mark-to-market equity (125,502 bars) ──► DD calculation
            │
            └─► compute_metrics() ──► OOS metrics in JSON
```

### Exact Trade Counts

| Window | Trades | Date Range | Net P&L | Profit Factor | Win Rate |
|--------|--------|------------|---------|---------------|----------|
| **In-Sample** | **2,226** | 2021-07-19 → 2024-09-10 | **-$9,913.54** | 0.5366 | 25.20% |
| **Out-of-Sample** | **2,389** | 2025-01-02 → 2026-10-09 | **-$1,980.51** | 0.9830 | 31.27% |

**The "3 trades" claim in the summary is factually incorrect.** The OOS period 2025-01-01 through 2026-10-09 contains **2,389 executed trades** (1,367 in 2025, 1,022 in 2026).

### Monte Carlo Input Provenance

```python
# run_assignment14.py:247-256
oos_tf = oos_res.trades_frame()          # 2,389 rows
mc_cfg = MonteCarloConfig(n_simulations=2000)
mc_summary = mc_summarise(
    oos_tf["net_pnl"].to_numpy(dtype=float),  # 2,389 trade P&Ls
    frozen_params.starting_equity,             # 10,000.0
    mc_cfg,
)
```

**The Monte Carlo used the full OOS trade series (2,389 trades), not 3 trades.** The `if len(oos_tf) >= 20:` condition at line 251 was satisfied.

---

## C. Equity & Drawdown Calculation Audit

### Independent Recomputation (Verified ✅)

| Metric | JSON Reported | Independent Recompute | Match |
|--------|---------------|----------------------|-------|
| IS final equity | 86.46 | 86.46 | ✅ |
| IS net P&L | -9,913.54 | -9,913.54 | ✅ |
| IS max DD (abs) | -10,492.62 | -10,492.62 | ✅ |
| IS max DD (pct) | -99.18% | -99.18% | ✅ |
| IS profit factor | 0.5366 | 0.5366 | ✅ |
| IS Sharpe | -2.9844 | -2.9844 | ✅ |
| IS win rate | 25.20% | 25.20% | ✅ |
| OOS final equity | 8,019.49 | 8,019.49 | ✅ |
| OOS net P&L | -1,980.51 | -1,980.51 | ✅ |
| OOS max DD (abs, ledger) | -9,954.70 | -9,954.70 | ✅ |
| OOS max DD (pct, ledger) | -61.91% | -61.91% | ✅ |
| OOS profit factor | 0.9830 | 0.9830 | ✅ |
| OOS Sharpe | 0.0612 | 0.0612 | ✅ |
| OOS win rate | 31.27% | 31.27% | ✅ |

### The -$9,633 Max Drawdown Discrepancy Explained

| Source | Max DD (abs) | Max DD (pct) | Calculation Basis |
|--------|--------------|--------------|-------------------|
| **OOS ledger equity curve** (125,502 bars) | **-$9,954.70** | **-61.91%** | Mark-to-market equity at every M5 bar |
| **Monte Carlo "observed" path** (2,389 trades) | **-$9,632.81** | **-61.01%** | Trade-by-trade equity path (compounded P&Ls) |

**Root cause:** The Monte Carlo module computes drawdown on the **trade-sequence equity path** (`_equity_path()` compounds 2,389 trade P&Ls), while the backtester's ledger equity curve is **mark-to-market at every bar** (125,502 M5 bars). The trade-sequence path ignores intra-trade drawdowns and mark-to-market fluctuations between trade close and next trade open.

**This is a known methodological difference, not an error.** The Monte Carlo correctly labels its assumptions:
> "Trade outcomes are drawn i.i.d. from the observed distribution. Position sizing is proportional to equity, so each simulated trade is scaled by the equity path it occurs on."

The -$9,633 figure in the Monte Carlo output is the **trade-sequence maximum drawdown**, not the mark-to-market drawdown. Both are valid but measure different things.

---

## D. Monte Carlo Eligibility Audit

### Original Assignment 14 Specification (Section G)
> "Monte Carlo (reshuffle + resample) on the OOS trade series."
> "Minimum 20 trades for a credible series."

### Actual Execution
| Check | Result |
|-------|--------|
| OOS trade count ≥ 20? | **YES** — 2,389 trades |
| Monte Carlo ran? | **YES** — 2,000 simulations each (reshuffle + resample) |
| Charts generated? | **YES** — `monte_carlo_equity_fan.png`, `monte_carlo_distributions.png` |
| Input data | OOS trade net P&L series (2,389 trades) |
| Starting equity | $10,000 |
| Assumptions recorded | ✅ i.i.d., path-scaling, no regime clustering |

### What the Monte Carlo Can/Cannot Establish

| Can Establish | Cannot Establish |
|---------------|------------------|
| Sequence risk dispersion (reshuffle) | That the strategy has positive expectancy |
| Outcome distribution dispersion (resample) | That future trades will follow the observed distribution |
| Terminal equity distribution under i.i.d. | Regime clustering effects (known limitation, documented) |
| Max drawdown distribution under i.i.d. | Real-world path dependency beyond trade ordering |

**The Monte Carlo is valid for its stated purpose** (sequence risk and outcome dispersion under i.i.d. assumptions). It was correctly run on the eligible OOS series. The charts are correctly labeled "OOS" because they use OOS trade outcomes.

---

## E. Implementation & Test Evidence Verification

### Strategy Implementation Tested
- **File:** `mars/libs/strategies/xau_mtf_donchian.py` (compute_signals, XauMtfDonchianStrategy)
- **Version:** Frozen at baseline (Donchian=20, ATR=2.0, EMA=50/5)
- **IS/OOS Separation:** Chronological split at 2025-01-01 (IS_END / OOS_START constants)
- **Parameter Selection:** Performed on IS only; OOS never consulted

### Automated Test Results

| Test Suite | Tests | Passed | Failed | Notes |
|------------|-------|--------|--------|-------|
| `test_xau_mtf_donchian_001.py` | 51 | **51** | 0 | 13 required areas fully covered |
| `test_xauusdm_dataset_v120.py` | 31 | 30 | 1 | 1 pre-existing failure (session_break_gaps: 1033 vs 1032 expected) |

**The 1 failed test is a pre-existing data-quality expectation mismatch (1033 session-break gaps vs 1032 expected), not a strategy/backtest logic failure.** All 51 strategy/backtest tests pass.

### Dataset Provenance Verified
- M5 v1.2.0: 369,972 true M5 bars, 2021-07-16 → 2026-10-09 (daily prefix excluded)
- H1 v1.2.0: 30,898 bars resampled from M5 (removes raw H1 DST grid offset)
- Manifests with checksums, transformations, known issues preserved

---

## F. Final Research Decision

### Decision: **REJECT — NO DEFENSIBLE EDGE**

**Evidence:**
1. **In-sample:** -99.14% return, PF 0.54, Sharpe -2.98, max DD -99.18%, 2,226 trades
2. **Out-of-sample:** -19.81% return, PF 0.98, Sharpe 0.06, max DD -61.91%, 2,389 trades
3. **Parameter comparison:** All 9 predeclared variants unprofitable in-sample
4. **Cost sensitivity:** Only halving spread makes OOS profitable (+8.5%); realistic costs deepen losses
5. **Benchmarks:** Buy-and-hold +42.4% (corrected units) vastly outperforms
6. **Monte Carlo:** Under i.i.d. assumptions, 95% of resampled paths lose money (p05 terminal equity: -$4,637)

**No parameter tuning against OOS data was attempted.** The frozen baseline configuration was selected mechanically because no IS candidate was profitable.

---

## G. Deliverables Produced

| Deliverable | Path | Status |
|-------------|------|--------|
| Reconciliation Report (this file) | `reports/assignment14/ASSIGNMENT_14B_RECONCILIATION_REPORT.md` | ✅ |
| Machine-readable Reconciliation JSON | `reports/assignment14/assignment14b_reconciliation.json` | ✅ |
| Source-to-Chart Provenance Table | Section B above | ✅ |
| Verified/Unverified Test List | Section E above | ✅ |
| Updated Decision Log | Section F above | ✅ |

### Reconciliation JSON

```json
{
  "reconciliation": {
    "date": "2026-11-25",
    "strategy_id": "XAU-MTF-DONCHIAN-001",
    "discrepancy_found": true,
    "discrepancy_summary": "Summary narrative reported 3 OOS trades and skipped MC; actual artifacts contain 2,389 OOS trades and MC ran successfully",
    "trade_counts": {
      "in_sample": 2226,
      "out_of_sample": 2389,
      "summary_reported_oos": 3
    },
    "monte_carlo": {
      "ran": true,
      "n_simulations": 2000,
      "input_trades": 2389,
      "input_source": "oos_res.trades_frame() net_pnl column",
      "charts_generated": ["monte_carlo_equity_fan.png", "monte_carlo_distributions.png"]
    },
    "metrics_verified": {
      "in_sample": true,
      "out_of_sample": true,
      "all_match_json": true
    },
    "drawdown_discrepancy_explained": "MC observed DD (-$9,633) is trade-sequence path; ledger DD (-$9,955) is mark-to-market bar path",
    "final_decision": "REJECT — NO DEFENSIBLE EDGE",
    "decision_unchanged": true
  }
}
```

---

## H. Recommended Next Roadmap Action

**Do not attempt Assignment 15 on this strategy.** The hypothesis (H1 EMA regime filter + M5 Donchian 2×ATR breakout on XAUUSDm) is falsified.

**Recommended:**
1. **Archive Assignment 14** with this reconciliation
2. **Design Assignment 15** with a fundamentally different hypothesis:
   - Different instrument (e.g., EURUSD, US indices)
   - Different regime filter (volatility, correlation, macro)
   - Different entry logic (mean reversion, order flow, microstructure)
   - Different timeframe combination
3. **Reuse the production-grade infrastructure** (data pipeline, backtester, risk engine, test harness, Monte Carlo) — all validated

---

## Commit Information

```bash
# To be filled after commit
git commit -m "Assignment 14B: reconciliation report — corrects OOS trade count (2389 vs 3), documents MC provenance, verifies all metrics, retains REJECT decision"
```

**File paths for commit:**
- `reports/assignment14/ASSIGNMENT_14B_RECONCILIATION_REPORT.md`
- `reports/assignment14/assignment14b_reconciliation.json`

---

**Prepared by:** M.A.R.S. Quant Research Pipeline  
**Date:** 2026-11-25  
**Classification:** Internal — Research Reconciliation