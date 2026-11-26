# M.A.R.S. Quant — Assignment 20
## Candidate 005 Regime Validation Design
### Mandatory Comparison: Unconditional Baseline vs Regime-Filtered vs Null

**Date:** 2026-11-25  
**Phase:** Assignment 20 — Phase F Formal Specification Audit and Pre-Backtest Feasibility  
**Candidate:** XAU-VOL-REGIME-SESSION-005 (Primary)  
**Authority:** Pre-registered comparison design — **no modifications permitted after Phase G commencement**  
**Reference:** Assignment 19 Research Specification Brief §1.7, Gate E Falsification Criteria, Assignment 17 Audit

---

## Executive Summary

This document pre-registers the **mandatory three-way comparison design** for Candidate 005 as required by the Advancement Decision Report and Research Specification Brief. The comparison isolates the incremental value of the regime filter by testing:

1. **Unconditional Baseline** — Recreates XAU-SESSION-MOM-001 (rejected in Assignment 17)
2. **Regime-Filtered** — Candidate 005 specification (vol ≤ 40th pctl, spread ≤ 40th pctl, no FOMC)
3. **Null Comparison** — Randomized regime labels / permutation test

**Core Hypothesis:** The regime filter recovers the edge lost in the unconditional strategy (Assignment 17: IS net expectancy -$34.77/trade) by isolating favorable market conditions where informed flow persists across sessions.

---

## 1. Unconditional Baseline Specification (Recreate XAU-SESSION-MOM-001)

### 1.1 Strategy Logic (Frozen from Assignment 17 Config)

| Component | Specification | Source |
|-----------|---------------|--------|
| **Signal** | Asian session return > 0 (close > open) | Paper 12 baseline |
| **Entry** | 08:00 UTC (first M5 bar Europe open) | Assignment 17 config |
| **Exit** | 14:30 UTC (Europe close / US open) — time stop | Assignment 17 config |
| **Stop-Loss** | Session low (Asia or Europe) OR 200 pts, whichever tighter | Assignment 17 config |
| **Take-Profit** | None | Assignment 17 config |
| **Direction** | Long only | Assignment 17 config |
| **Position Sizing** | Fixed fractional 1% equity, min 0.01 lot | Assignment 17 config |

### 1.2 Regime Filter: **ABSENT** (Unconditional)

- No volatility filter
- No spread filter
- No FOMC filter
- Every Asian session with close > open generates a signal

### 1.3 Data and Periods (Identical to Candidate 005)

| Period | Date Range | Purpose |
|--------|------------|---------|
| Burn-in | 2021-07-16 → 2021-09-30 | N/A (no trailing window) |
| In-Sample (IS) | 2021-10-01 → 2024-12-31 | Primary comparison period |
| Out-of-Sample (OOS) | 2025-01-01 → 2025-10-09 | Frozen validation |
| Reserve | 2025-10-10 → 2026-10-09 | Future |

### 1.4 Expected Baseline Performance (from Assignment 17 Audit)

| Metric | Train (IS) | Test (Holdout) | Source |
|--------|------------|----------------|--------|
| Net Expectancy | -$32.40/trade | **-$34.77/trade** | Assignment 17 §C.2 |
| Net Profit Factor | 0.00 | 0.47 | Assignment 17 §C.2 |
| Net Sharpe | -4.26 | -1.42 | Assignment 17 §C.2 |
| Max Drawdown | -99.80% | -99.88% | Assignment 17 §C.2 |
| Win Rate (net) | 0.0% | 0.3% | Assignment 17 §C.2 |
| Trade Count | 308 | 287 | Assignment 17 §C.2 |

**Critical:** The unconditional baseline is **expected to fail** all falsification criteria. This is the control against which the regime filter's incremental value is measured.

---

## 2. Regime-Filtered Specification (Candidate 005)

### 2.1 Strategy Logic (Frozen from Research Brief §1.4)

| Component | Specification | Source |
|-----------|---------------|--------|
| **Base Signal** | Asian session return > 0 (close > open) | Paper 12 baseline |
| **Regime Filter 1: Volatility** | H1 realized vol (20-bar) ≤ 40th percentile (trailing) | Research Brief §1.4 |
| **Regime Filter 2: Spread** | Asian session avg spread ≤ 40th percentile (IS distribution) | Research Brief §1.4 |
| **Regime Filter 3: FOMC** | Exclude FOMC days (FRED calendar) | Research Brief §1.4 |
| **Entry** | 08:00 UTC (first M5 bar Europe open) | Research Brief §1.4 |
| **Exit** | 14:30 UTC (time stop) | Research Brief §1.4 |
| **Stop-Loss** | Session low (Asia or Europe) OR 200 pts, whichever tighter | Research Brief §1.4 |
| **Take-Profit** | None | Research Brief §1.4 |
| **Direction** | Long only | Research Brief §1.4 |
| **Position Sizing** | Fixed fractional 1% equity, min 0.01 lot | Research Brief §1.4 |

### 2.2 Regime Filter Logic (Operational Definition)

**Volatility Regime (H1, 20-bar trailing realized volatility):**
```
For each session date D:
  1. Compute H1 realized volatility for prior 20 H1 bars (ending at Asia close 08:00 UTC)
  2. Maintain trailing distribution of vol values (expanding window from burn-in)
  3. Vol regime = "favorable" if current vol ≤ 40th percentile of trailing distribution
  4. Vol regime = "unfavorable" if current vol > 40th percentile
```

**Spread Regime (Asian session average spread):**
```
For each session date D:
  1. Compute mean spread (points) across all M5 bars in Asia session (00:00-08:00 UTC)
  2. Build IS-period distribution (2021-10-01 to 2024-12-31) — FROZEN after IS
  3. Spread regime = "favorable" if session mean spread ≤ 40th percentile of IS distribution
  4. Spread regime = "unfavorable" if session mean spread > 40th percentile
```

**FOMC Filter:**
```
For each session date D:
  1. Check FRED FOMC calendar for meeting dates
  2. If D falls on FOMC meeting day (or day before/after per sensitivity) → exclude
  3. FOMC filter = "favorable" if not FOMC day
```

**Combined Regime Gate:**
```
Trade executed IF AND ONLY IF:
  (Asian return > 0) AND (Vol regime = favorable) AND (Spread regime = favorable) AND (FOMC filter = favorable)
```

### 2.3 Data and Periods (Identical to Baseline)

Same periods as unconditional baseline — enables direct comparison.

---

## 3. Null Comparison Specification

### 3.1 Purpose
Test whether the regime filter's apparent performance could arise by chance from random regime labeling.

### 3.2 Null Method 1: Regime Label Permutation (Primary Null)

**Procedure:**
1. Take the **regime-filtered trade set** (sessions where all 3 regime filters = favorable)
2. Randomly permute the regime labels (favorable/unfavorable) across sessions **10,000 times**
3. For each permutation, recompute net expectancy using the same trade P&L values
4. Build null distribution of net expectancy under random regime assignment
5. **Test Statistic:** Observed regime-filtered net expectancy
6. **p-value:** Proportion of permutations where null expectancy ≥ observed expectancy

**Decision Rule:**
- If p < 0.05 (one-sided): Regime filter adds statistically significant value
- If p ≥ 0.05: Cannot reject null that filter is random

### 3.3 Null Method 2: Signal Permutation (Secondary Null)

**Procedure:**
1. Take all sessions where Asian return > 0 (unconditional signal universe)
2. Randomly permute the **Asian return sign** (positive/negative) across sessions 10,000 times
3. For each permutation, apply regime filters and compute net expectancy
4. Tests whether the base signal (Asian return > 0) has predictive power beyond chance
5. **Decision Rule:** Same p < 0.05 threshold

### 3.4 Null Method 3: Synthetic Random Regimes (Tertiary Null)

**Procedure:**
1. Generate synthetic regime labels with same marginal probability as observed (e.g., 40% favorable)
2. Apply to unconditional signal universe
3. Repeat 10,000 times
4. Tests whether the specific regime definition matters vs. any 40% filter

**Pre-Registration:** All three null methods will be run. Primary inference from Method 1 (regime label permutation).

---

## 4. Statistical Test Design for Regime Interaction (FC-005-2)

### 4.1 Primary Test: Interaction Regression

**Model Specification:**
```
PnL_i = β_0 + β_1 × Signal_i + β_2 × Regime_i + β_3 × (Signal_i × Regime_i) + ε_i
```

Where:
- `Signal_i` = 1 if Asian return > 0, 0 otherwise
- `Regime_i` = 1 if all regime filters favorable, 0 otherwise
- `Signal_i × Regime_i` = interaction term (the regime-filtered trades)
- `PnL_i` = net P&L per trade (after costs)

**Hypothesis:**
- H₀: β_3 ≤ 0 (regime filter does not improve signal)
- H₁: β_3 > 0 (regime filter adds positive incremental expectancy)

**Test:** One-sided t-test on β_3 coefficient
**Pass Threshold:** β_3 > 0 AND p < 0.05 (one-sided)
**Indeterminate:** 0.05 ≤ p < 0.10
**Fail:** β_3 ≤ 0 OR p ≥ 0.05

### 4.2 Secondary Test: Conditional Expectancy Comparison

**Comparison:**
- E[PnL | Signal=1, Regime=1] vs E[PnL | Signal=1, Regime=0]
- One-sided t-test (Welch's, unequal variance)
- **Pass:** Mean(Regime=1) > Mean(Regime=0) with p < 0.05

### 4.3 Tertiary Test: Regime Filter Efficiency

**Metric:** Ratio of regime-filtered trades to unconditional trades that are profitable
- Tests whether filter selectively removes losing trades
- **Pass:** Filtered win rate > unconditional win rate with statistical significance

---

## 5. Sensitivity Analyses (Pre-Registered from Research Brief §1.7)

| # | Sensitivity | Values Tested | Base Value | Purpose |
|---|-------------|---------------|------------|---------|
| 1 | **Spread Multiplier** | 1.0×, 1.5×, 2.0× | 1.0× | Cost robustness (FC-005-4) |
| 2 | **Vol Percentile Threshold** | 30th, 40th, 50th | 40th | Regime threshold stability |
| 3 | **Spread Percentile Threshold** | 30th, 40th, 50th | 40th | Regime threshold stability |
| 4 | **FOMC Filter** | ON, OFF | ON | Calendar dependency |
| 5 | **SL Distance** | 150, 200, 250, 300 pts | 200 pts | Risk-reward sensitivity |
| 6 | **DST-Adjusted Sessions** | ±1 hour shift | Fixed UTC | Seasonal robustness |

**Execution Protocol:**
- Each sensitivity runs **full IS period** with frozen OOS parameters
- OOS validation uses **base parameters only** (no sensitivity optimization)
- Results reported as: expectancy, trade count, max DD, Sharpe
- **No parameter selection** based on sensitivity results — purely diagnostic

---

## 6. Comparison Execution Protocol

### 6.1 Run Order (Pre-Registered)

1. **Unconditional Baseline** — Full IS + OOS (establishes control)
2. **Regime-Filtered (Base)** — Full IS + OOS (primary candidate)
3. **Null Method 1** — 10,000 permutations on regime-filtered trades
4. **Null Method 2** — 10,000 permutations on signal
5. **Null Method 3** — 10,000 synthetic regime draws
6. **Interaction Regression** — On full session panel
7. **Sensitivity Analyses** — 6 dimensions × base parameters
8. **OOS Validation** — Frozen base parameters on 2025-01-01 to 2025-10-09

### 6.2 Output Requirements (Per Run)

| Output | Format | Contents |
|--------|--------|----------|
| Trade Ledger | JSON + CSV | Every trade: entry/exit, P&L, regime labels, costs |
| Equity Curve | JSON | Timestamped equity points |
| Summary Metrics | JSON | Expectancy, PF, Sharpe, DD, trade count, win rate |
| Falsification Status | JSON | PASS/FAIL/INDETERMINATE for each FC |
| Regime Diagnostics | JSON | Regime distribution, filter rates, conditional stats |

### 6.3 Decision Rules for Phase K Advancement

| Criterion | Must Pass | Source |
|-----------|-----------|--------|
| FC-005-1: IS Conditional Expectancy > $0.00 | ✅ YES | Research Brief §1.6 |
| FC-005-2: Regime Interaction β_3 > 0, p < 0.05 | ✅ YES | Research Brief §1.6 |
| FC-005-3: OOS Expectancy > $0.00 | ✅ YES | Research Brief §1.6 |
| FC-005-4: Cost Sensitivity PASS at 1.0× AND 1.5× | ✅ YES | Research Brief §1.6 |
| IS Trades ≥ 50 (after filter) | ✅ YES | Research Brief §1.8 |
| OOS Trades ≥ 20 | ✅ YES | Research Brief §1.8 |
| IS Max DD < 30% | ✅ YES | Research Brief §1.8 |
| IS Net Expectancy > $0.05/trade | ✅ YES | Research Brief §1.8 |

**All 8 criteria must PASS.** Any FAIL → Candidate 005 REJECTED at Phase K.

---

## 7. Pre-Registered Comparison Metrics Table

| Metric | Unconditional Baseline | Regime-Filtered | Null (Permutation) | Comparison |
|--------|------------------------|-----------------|-------------------|------------|
| IS Net Expectancy | -$34.77 (expected) | Target > $0.05 | Distribution p5/p50/p95 | Filter value |
| IS Trade Count | ~287 | Target ≥ 50 | N/A | Filter selectivity |
| IS Win Rate | ~0.3% | Target > 50% | N/A | Filter efficiency |
| IS Max DD | -99.88% | Target < 30% | N/A | Risk control |
| OOS Net Expectancy | N/A | Target > $0.00 | N/A | Persistence |
| Regime Interaction p | N/A | Target < 0.05 | N/A | Statistical rigor |
| Null p-value (Method 1) | N/A | N/A | Target < 0.05 | Chance exclusion |

---

## 8. Risk Register for Comparison Design

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Insufficient IS trades after filter | MEDIUM | HIGH | Minimum 50 trades required; if < 50, candidate fails FC-005-1 |
| Regime filter overfit to IS | MEDIUM | HIGH | Pre-specified thresholds; OOS validation; null permutation test |
| FOMC calendar data unavailable | LOW | MEDIUM | Sensitivity with FOMC OFF; not core to regime filter |
| DST distortion in 2021-2024 | LOW | LOW | Sensitivity test ±1 hour; not core |
| Spread regime threshold unstable | MEDIUM | MEDIUM | Test 30th/40th/50th; report stability |

---

## 9. Reproducibility Requirements

| Requirement | Specification |
|-------------|---------------|
| Random Seeds | IS: 20261125, Null Permutations: 20261126, OOS: 20261127 |
| Data Version | M5 v1.2.0, H1 v1.2.0 (pinned) |
| Code Version | Git commit hash recorded at Phase G start |
| Environment | Python 3.11+, pandas, numpy, scipy (requirements.txt) |
| Config | Frozen YAML committed before Phase G |

---

## 10. Sign-Off

**Comparison Design Pre-Registered:** 2026-11-25  
**Author:** M.A.R.S. Quant Research Pipeline  
**Authorization:** This design is **frozen**. No modifications permitted after Phase G commencement. All comparisons must execute per this specification.

> **Key Principle:** The unconditional baseline is expected to fail (Assignment 17 evidence). The regime filter must demonstrate **statistically significant incremental value** over both the unconditional baseline AND the null permutation distribution. FC-005-2 (interaction p < 0.05) is the primary gate.

---

*End of Candidate 005 Regime Validation Design*  
*Deliverable 2 of 8 — Assignment 20*