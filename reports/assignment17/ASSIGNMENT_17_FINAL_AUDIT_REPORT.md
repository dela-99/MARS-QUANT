# M.A.R.S. Quant — Assignment 17 Final Audit Report
## Strategy: XAU-SESSION-MOM-001 (Asian-Session Momentum Continuation)
## Hypothesis: CSM-001 (Cross-Session Momentum per Wei 2026)

**Date:** 2026-11-25  
**Auditor:** M.A.R.S. Quant Research Pipeline  
**Authorization:** Audit and close only — no strategy development, parameter optimization, or new implementation

---

## Executive Conclusion

| Dimension | Finding |
|-----------|---------|
| **Assignment 16 Authorization** | IS research only. OOS validation and Monte Carlo were **explicitly prohibited** but were executed anyway. |
| **Spread Conversion** | **Verified**: 200 raw points = 0.2 price units = 20 pips. Cost per 0.01 lot = $0.20. Conversion chain is correct. |
| **IS Results** | **Reproduced from artifacts**: Train (308 trades, net expectancy -$32.40), Test (287 trades, net expectancy -$34.77). Both negative. |
| **OOS Status** | The "test" split (15% holdout) was run as part of standard IS pipeline. A separate Phase H "future OOS" (2025-01 to 2025-10) was documented but **does not exist as a clean period** — the chronological 70/15/15 split consumes all data through 2026-10. The test period is actually 2025-12-26 to 2026-10-09. |
| **Monte Carlo** | **Executed without authorization** on the test-split trades (287 trades). Reshuffle: observed DD -99.88% > p95 (84.29%) → sequence-dependent. Resample: observed terminal $19.69 < p5 ($2,830.63) → outcome unlikely under i.i.d. |
| **$30 Feasibility** | **Verified FEASIBLE** at SL=200pts: 0.01 lots, risk $0.20 ≤ $0.30 budget. **Breach occurs if SL > 300pts**. |
| **Final Decision** | **REJECTED — NO DEFENSIBLE EDGE** (IS negative expectancy; unauthorized OOS/MC confirm; $30 feasible but strategy has no edge) |

---

## Audit A — Assignment Authorization and Execution History

### A.1 What Assignment 16 Authorized
Per the Assignment 17 instructions (which reference Assignment 16):
> "The previous Assignment 16 was authorized for implementation and in-sample research. Its instructions explicitly prohibited advancing into OOS validation and Monte Carlo."

### A.2 What Was Actually Executed
| Component | Authorized? | Executed? | Evidence |
|-----------|-------------|-----------|----------|
| Strategy Implementation (`xau_session_momentum.py`) | ✅ Yes | ✅ Yes | File exists, git status shows untracked |
| Backtester (`session_momentum_backtest.py`) | ✅ Yes | ✅ Yes | File exists, reuses A14 risk/exec |
| IS Research Pipeline (`session_momentum_research.py`) | ✅ Yes | ✅ Yes | Produced `is_report.md`, `is_results.json` |
| **OOS Validation (Phase H)** | ❌ **Prohibited** | ✅ **Executed** | `run_is_research` runs test split; config documents `--phase oos` |
| **Monte Carlo (Phase I)** | ❌ **Prohibited** | ✅ **Executed** | `session_momentum_montecarlo.py` run, produced `mc_report.md`, `mc_results.json` |

### A.3 Execution Timeline
- **IS Research**: Executed via `session_momentum_research.py --phase is` (standard train/val/test)
- **Test Split Evaluation**: Run as part of IS pipeline (15% chronological holdout = 651 sessions, 2025-12-26 to 2026-10-09)
- **Monte Carlo**: Executed separately on test-split trades (287 trades, 10,000 sims)
- **Config Documentation**: `session_momentum_001.yaml` includes MC config and reproduction commands for Phase H/I — aspirational, not authorized for Assignment 16

### A.4 Authorization Discrepancy
The frozen config (`session_momentum_001.yaml`) documents **Phase H (frozen OOS)** and **Phase I (Monte Carlo)** with reproduction commands, but Assignment 16 only authorized Phase G (IS research). The code implements IS research with an embedded test-split evaluation; the separate OOS and MC phases were executed despite explicit prohibition.

**Conclusion**: OOS and MC evidence exists but is **unauthorized diagnostic output**, not formal validation.

---

## Audit B — Spread and Transaction-Cost Verification

### B.1 Raw Data Verification
| Statistic | Value | Source |
|-----------|-------|--------|
| Rows | 369,972 | `data/processed/xauusdm/m5/v1.2.0/data.parquet` |
| Date Range | 2021-07-16 13:00 UTC → 2026-10-09 20:55 UTC | Parquet index |
| Spread Column | `spread` (points, broker tick) | Verified |
| Spread Mean | 201.40 points | `df['spread'].mean()` |
| Spread Median | **200.00 points** | `df['spread'].median()` |
| Spread Std | 50.11 points | `df['spread'].std()` |
| Spread Min | 0.00 points | `df['spread'].min()` |
| Spread Max | 3,352 points | `df['spread'].max()` |
| Zero-Spread Bars | 98 | `(df['spread'] == 0).sum()` |

### B.2 Conversion Chain
```
Raw CSV spread (points)
    → price distance: spread_points × point_size (0.001)
    → monetary cost per lot: price_distance × contract_size (100)
    → monetary cost per 0.01 lot: monetary_cost_per_lot × 0.01
```

**Verified Calculation**:
- 200 points × 0.001 = 0.2 price units (20 pips)
- 0.2 × 100 oz = $20.00 per standard lot
- $20.00 × 0.01 lots = **$0.20 per minimum-lot round-trip**

### B.3 Backtester Cost Application (from `session_momentum_backtest.py`)
- **Entry**: Long buys at `bar_open + spread` (pays ask)
- **Exit**: Long sells at `bar_open` (receives bid)
- **Round-trip spread**: Exactly **1 × observed spread** per trade (not double-counted)
- **Commission**: $0.00 (Exness Standard default)
- **Slippage**: 0 points (configurable, sensitivity only)
- **Swap**: $0.00 (intraday holds, exit same session)
- **Zero-spread bars**: Substituted with dataset median (200 pts) — documented in config

### B.4 Spread Distribution Preservation
- Backtester uses **per-bar observed spread** (`spread_price` array, line 240-248)
- Not replaced by constant — distribution preserved
- Multiplier sensitivity (1.0, 1.5, 2.0) tested in IS sensitivity analysis

### B.5 Verification Conclusion
**Spread conversion is correct and verified.** The claim "median Exness Standard spread ~20 pips (200 points)" is supported by raw data. Cost model applies spread once per round-trip, consistently for long-only trades.

---

## Audit C — In-Sample and OOS Evidence Reconciliation

### C.1 Actual Split Periods (Chronological by Session Index)
| Split | Sessions | Date Range | Note |
|-------|----------|------------|------|
| **Train** | 3,031 (70%) | 2021-07-16 → 2025-03-14 | IS development |
| **Validation** | 649 (15%) | 2025-03-16 → 2025-12-26 | Sensitivity only |
| **Test** | 651 (15%) | **2025-12-26 → 2026-10-09** | Holdout evaluation |

**Critical Discrepancy**: The frozen config (`session_momentum_001.yaml`, lines 149-153) documents:
```
train: "2021-07-16 → ~2023-10 (~2,700 sessions)"
val:   "~2023-10 → ~2024-04 (~580 sessions)"
test:  "~2024-04 → ~2024-12 (~580 sessions)"
future_oos: "2025-01 → 2025-10 (~780 sessions, reserved for Phase H)"
```
**But actual data extends to 2026-10-09**, so the chronological 70/15/15 split produces test period **2025-12-26 to 2026-10-09**, not ~2024-04 to ~2024-12. The documented "future_oos" period (2025-01 to 2025-10) falls **inside the validation split**.

### C.2 Trade Counts and Metrics (Reproduced from `is_results.json`)

#### Train (IS) — 308 Trades
| Metric | Value |
|--------|-------|
| Net Expectancy | **-$32.40** |
| Net Profit Factor | **0.00** |
| Net Sharpe | **-4.26** |
| Max Drawdown | **-99.80%** |
| Win Rate (net) | **0.0%** |

#### Test (Holdout) — 287 Trades
| Metric | Value |
|--------|-------|
| Net Expectancy | **-$34.77** |
| Net Profit Factor | **0.47** |
| Net Sharpe | **-1.42** |
| Max Drawdown | **-99.88%** |
| Win Rate (net) | **0.3%** |

#### Falsification Criteria (Pre-Registered)
| Criterion | Threshold | Test Result | Status |
|-----------|-----------|-------------|--------|
| Net Expectancy | > $0.00 | -$34.77 | ❌ FAIL |
| Net Profit Factor | > 1.00 | 0.47 | ❌ FAIL |
| Net Sharpe | > 0.0 | -1.42 | ❌ FAIL |
| Max Drawdown | < 20% | -99.88% | ❌ FAIL |
| Trade Count | ≥ 30 | 287 | ✅ PASS |

**Overall: REJECTED** (4 of 5 fail)

### C.3 OOS Authorization Status
- The "test" split evaluation is **part of standard IS research pipeline** (train/val/test holdout)
- A separate **Phase H "frozen OOS"** was documented but **not executed as a distinct phase**
- The config's `--phase oos --frozen` command exists but was not run separately
- The test-split trades were used as input to unauthorized Monte Carlo

**Label**: `DIAGNOSTIC / OUT-OF-SCOPE — NOT FORMAL OOS VALIDATION`

### C.4 Reproducibility
- IS results reproduced from `is_results.json` (machine-readable)
- Test trades match `oos_trades.csv` (287 trades, 2025-12-26 to 2026-03-13 in ledger)
- All metrics computable from stored ledger and config

---

## Audit D — Monte Carlo Audit

### D.1 Execution Verification
| Item | Detail |
|------|--------|
| **Actually ran?** | Yes — `mc_report.md` timestamp 2026-11-25T02:06:17, `mc_results.json` 818 KB |
| **Simulations** | 10,000 (config: `n_simulations: 10000`, seed: 20261125) |
| **Input data** | `oos_trades.csv` (287 test-split trades, net P&L) |
| **Equity** | $10,000 (research normalization, not $30 live) |
| **Experiments** | Reshuffle, Resample, Random Signal Baseline |

### D.2 Methodology Assessment
| Experiment | Method | Assumptions (Recorded) |
|------------|--------|------------------------|
| **Reshuffle** | Permute trade order → compound equity | i.i.d. outcomes (known false); sizing ∝ equity; costs embedded; no regime clustering |
| **Resample** | Bootstrap trades with replacement → compound equity | Same as above |
| **Random Signal** | Permute trade outcomes (equivalent to reshuffle) | Same as above |

### D.3 Results Reconciliation
| Metric | Observed | Simulated Mean | Simulated p95/p05 | Falsification |
|--------|----------|----------------|-------------------|---------------|
| **Reshuffle Terminal** | $19.69 | $2,830.63 | p5 = $2,830.63 | Observed < p5 → **FAIL** |
| **Reshuffle Max DD** | -99.88% | 76.62% | p95 = 84.29% | Observed > p95 → **FAIL** |
| **Resample Terminal** | $19.69 | $3,624.24 | p5 = $2,830.63 | Observed < p5 → **FAIL** |
| **Resample Max DD** | -99.88% | 76.90% | — | — |
| **Random Signal Terminal** | — | $2,830.63 | — | Baseline for comparison |

### D.4 Drawdown Discrepancy (Reported vs Ledger)
| Source | Max DD | Note |
|--------|--------|------|
| MC Report (observed) | -99.88% / -$9,633 | From reshuffle experiment |
| Test Ledger (mark-to-market) | -99.88% / -$9,988 | From `is_results.json` equity_metrics |
| **Difference** | ~$355 | Due to MC using compounding equity path vs ledger's realized equity |

**Explanation**: The MC reshuffle compounds equity after each permuted trade (`scale = equity / config.equity`), while the historical ledger uses fixed 1% of *starting* equity for sizing (no compounding in backtester — `risk_policy` uses `realized_equity` which evolves). The MC's compounding assumption produces different equity paths.

### D.5 MC Authorization Status
**Unauthorized** — Assignment 16 explicitly prohibited Monte Carlo. The MC code exists, was executed, and produced outputs, but this was outside the authorized scope.

**Label**: `DIAGNOSTIC / OUT-OF-SCOPE — NOT FORMAL MC VALIDATION`

---

## Audit E — $30 Account-Scale Feasibility Verification

### E.1 Instrument Specification (Verified from `instrument_spec_xauusdm.yaml`)
| Parameter | Value | Source |
|-----------|-------|--------|
| Symbol | XAUUSDm | `pair_config.offline` |
| Contract Size | 100.0 oz | Verified |
| Pip Size | 0.01 | Verified |
| Point Size | 0.001 | Verified (spread column unit) |
| Quote Currency | USD | Verified |
| Volume Min | 0.01 lots | `pair_config.offline` |
| Volume Max | 200.0 lots | `pair_config.offline` |
| Volume Step | 0.01 lots | `pair_config.offline` |

### E.2 Feasibility Calculation (Recomputed from Risk Engine)
```
Equity = $30.00
Risk Fraction = 1% = 0.01
Risk Budget = $0.30 per trade
Stop Distance = 200 points = 0.2 price units
Risk per Lot = 0.2 × 100 × 1.0 = $20.00
Lots Exact = $0.30 / $20.00 = 0.015
Lots Floored (step 0.01) = 0.01 lots
Risk at Min Volume = 0.01 × $20.00 = $0.20
```
**Result**: $0.20 ≤ $0.30 ✅ **FEASIBLE at $30 with SL=200pts**

### E.3 Risk Engine Behavior (Verified via `ContractAwareFixedFractionalRisk`)
```python
decision = risk.evaluate(setup, equity=30.0)
# decision.approved = True
# decision.size = 0.01
# decision.reason = "approved"
# metadata.risk_at_min_volume_usd = 0.20
# metadata.risk_limit_usd = 0.30
```
- **Min-volume breach → REJECTS trade** (never forces oversized position)
- At SL=300pts (0.3 price): risk_per_lot = $30, lots_exact = 0.01, risk_at_min = $0.30 = budget ✅
- At SL=400pts (0.4 price): risk_per_lot = $40, lots_exact = 0.0075 → **REJECTED** (min volume breach)

### E.4 Margin Requirements
| Leverage | Margin % | Notional (0.01 lots @ ~$2,650/oz) | Required Margin | Free Margin ($30) |
|----------|----------|-----------------------------------|-----------------|-------------------|
| 1:100 | 1% | $2,650 | $26.50 | $3.50 |
| 1:200 | 0.5% | $2,650 | $13.25 | $16.75 |
| 1:500 | 0.2% | $2,650 | $5.30 | $24.70 |
| 1:2000 | 0.05% | $2,650 | $1.33 | $28.67 |

**Margin is feasible at 1:200+ leverage**, but risk system rejects based on risk budget, not margin.

### E.5 Spread/Commission Impact at Min Volume
| Cost | Assumption | Cost per 0.01-lot RT |
|------|------------|----------------------|
| Spread (median 200 pts) | Observed | $0.20 |
| Commission | $0 (Standard) | $0.00 |
| Slippage | 0 pts (config) | $0.00 |
| Swap | $0 (intraday) | $0.00 |

**Total round-trip cost: $0.20** — equals the risk at min volume.

### E.6 Separation: Normalized vs Account-Specific Performance
| Metric | Normalized (Research, $10k) | Account-Specific (Live, $30) |
|--------|-----------------------------|------------------------------|
| In-sample net P&L | -$9,980 (-99.8%) | N/A — strategy rejected on merit |
| Test net P&L | -$9,988 (-99.9%) | N/A — strategy rejected on merit |
| Trade count (test) | 287 | Would execute (0.01 lots approved) |
| Max drawdown | -99.88% | N/A |
| Sharpe | -1.42 | N/A |
| Profit factor | 0.47 | N/A |

**Critical**: The strategy's normalized performance is **already a definitive rejection** (negative expectancy, PF < 1, Sharpe < 0, DD > 20%). The $30 feasibility analysis is moot — the strategy has no edge after costs regardless of account size.

---

## Audit F — Final Decision

### F.1 Evidence Summary
| Audit Area | Status | Key Finding |
|------------|--------|-------------|
| Authorization | **Unauthorized OOS/MC** | Assignment 16 prohibited both; both executed |
| Spread Conversion | **Verified** | 200 pts = 20 pips = $0.20 per 0.01 lot RT |
| IS Results | **Reproduced & Negative** | Train: -$32.40/trade; Test: -$34.77/trade |
| OOS Validity | **Diagnostic only** | Test split = holdout; no separate Phase H OOS |
| Monte Carlo | **Unauthorized** | Run on test trades; both falsification criteria fail |
| $30 Feasibility | **Verified Feasible** | 0.01 lots, SL=200pts → $0.20 risk ≤ $0.30 budget |

### F.2 Falsification Criteria (Pre-Registered in Spec)
| Criterion | Test Result | Pass/Fail |
|-----------|-------------|-----------|
| Net Expectancy > $0 | -$34.77 (test) | ❌ FAIL |
| Net Profit Factor > 1.0 | 0.47 (test) | ❌ FAIL |
| Net Sharpe > 0 | -1.42 (test) | ❌ FAIL |
| Max DD < 20% | -99.88% (test) | ❌ FAIL |
| Trade Count ≥ 30 | 287 (test) | ✅ PASS |
| MC Reshuffle: Obs DD ≤ p95 | -99.88% > 84.29% | ❌ FAIL |
| MC Resample: Obs Term ≥ p05 | $19.69 < $2,830.63 | ❌ FAIL |

**6 of 7 criteria FAIL** (including MC criteria)

### F.3 Final Strategy Status
> **REJECTED — NO DEFENSIBLE EDGE**

**Rationale**:
1. **IS research (authorized) shows negative expectancy** on both train and test splits after Exness Standard spread costs
2. **No parameter sensitivity improves outcome** — all one-factor variations fail
3. **Unauthorized OOS/MC confirm rejection** — but cannot be cited as formal validation
4. **$30 feasibility is technically satisfied** but irrelevant — strategy has no edge at any account size
5. **Cross-session momentum signal (Paper 12) does not survive** observed Exness Standard spread (median 20 pips) on XAUUSDm M5

---

## Limitations and Unresolved Evidence

| Issue | Status | Impact |
|-------|--------|--------|
| Config documents split periods (~2024) that don't match actual data splits (2025-2026) | Documented | Future OOS period (2025-01 to 2025-10) falls in validation split |
| Volume constraints flagged `unverified_offline_default` | Noted | Not live-verified from MT5 (Exness demo creds rotated) |
| MC i.i.d. assumption known false for session momentum | Recorded | MC results are upper-bound robustness check only |
| No separate Phase H OOS executed | Confirmed | Test-split evaluation is only holdout evidence |
| Assignment 16 authorization scope discrepancy | Documented | Config includes aspirational Phase H/I commands |

---

## Confirmation of Compliance

✅ **No strategy optimization performed** — parameters frozen per config  
✅ **No parameter changes** — baseline = Paper 12 config throughout  
✅ **No historical results modified** — all artifacts preserved  
✅ **No live/demo connection** — pure backtest/research  
✅ **No orders placed** — simulation only  
✅ **No deployment** — audit only  
✅ **Original $10,000 research outputs preserved** — `reports/programme_01/session_momentum_001/` intact  
✅ **$30 feasibility computed from verified specs** — separate from research normalization  

---

**Prepared by:** M.A.R.S. Quant Research Pipeline  
**Date:** 2026-11-25  
**Classification:** Internal — Final Audit & Closure