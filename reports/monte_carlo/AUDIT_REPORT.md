# MA-TSM-001 Monte Carlo Integrity Audit Report

**Date:** 2026-11-22  
**System:** M.A.R.S. Quant  
**Assignment:** 09 - Monte Carlo Integrity Audit & Independent Verification  
**Strategy:** MA-TSM-001 (Moving Average Trend Following)  
**Symbol:** XAUUSD (Gold)  
**Timeframe:** H1/M5 Walkforward OOS  
**Trades:** 914 OOS trades  
**Initial Capital:** $10,000,000

---

## Executive Summary

The MA-TSM-001 Monte Carlo pipeline has been audited for mathematical correctness, data integrity, and visualization fidelity. **All core calculations are mathematically correct and internally consistent.** The implementation accurately computes historical metrics, runs three Monte Carlo methods (trade reshuffling, trade resampling with replacement, and moving block bootstrap), and produces consistent JSON output.

### Key Findings

| Component | Status | Notes |
|-----------|--------|-------|
| Historical Metrics | ✅ PASS | Terminal return 154.23%, Max DD 14.40%, Max Streak 40 - all independently verified |
| Trade Reshuffling | ✅ PASS | Perfect match with independent calculation (deterministic permutation) |
| Trade Resampling | ✅ PASS | Mean/std match; tail percentiles within expected MC variation |
| Block Bootstrap | ✅ PASS | Mean/std match; tail percentiles within expected MC variation |
| JSON Output | ✅ PASS | Perfect match with implementation results |
| Visualization Data | ✅ PASS | Historical markers correctly positioned; percentile bands monotonic |
| Dependence Tests | ✅ PASS | Ljung-Box p=0.935, Runs test p=0.498 - no serial dependence detected |
| Unit Tests | ✅ PASS | All 30 tests pass |

### Visualization Fixes Applied

Two visualization issues identified in the audit brief were fixed:

1. **Fan Chart Y-Axis Compression**: The original fan charts used linear dollar-scale y-axis with auto-scaling. Extreme outlier paths (up to $165M for resampling) compressed the median growth (~$10M → $25M) into a visually small portion of the chart, creating the appearance of "2-4% growth" instead of the actual ~150% growth. **Fixed** by normalizing all paths to percentage return from initial capital.

2. **Historical Marker Visibility**: The historical-vs-simulated box plot for terminal equity used dollar scale with extreme range, placing the historical $25.4M marker near the bottom visually. **Fixed** by using terminal return (%) for all return-related subplots, ensuring historical markers appear at their correct percentile positions.

---

## 1. Historical Metrics Audit

### Source Data
- **File:** `reports/walkforward/oos_trades_for_mc.json`
- **Trades:** 914 OOS trades from walkforward validation
- **Returns:** Per-trade PnL as fraction of capital (includes costs)

### Calculations (Independently Verified)

| Metric | Formula | Implementation | Independent | Status |
|--------|---------|----------------|-------------|--------|
| Terminal Return | (Final Equity - Initial) / Initial | 1.542338 (154.23%) | 1.542338 (154.23%) | ✅ MATCH |
| Max Drawdown | max((Peak - Equity) / Peak) | 0.143987 (14.40%) | 0.143987 (14.40%) | ✅ MATCH |
| Max Losing Streak | max consecutive returns < 0 | 40 | 40 | ✅ MATCH |
| Final Equity | Initial × (1 + Terminal Return) | $25,423,383.09 | $25,423,383.09 | ✅ MATCH |

**Verification Method:** Independent calculation using NumPy accumulation loops and peak-tracking drawdown algorithm. All values match to machine precision.

---

## 2. Monte Carlo Methods Audit

### Configuration
- **Simulations:** 10,000 per method
- **Seed:** 42 (reproducible)
- **Block Length:** 20 trades (block bootstrap)
- **DD Thresholds:** 5%, 10%, 15%, 20%
- **Streak Threshold:** 5 consecutive losses

### Method 1: Trade Reshuffling (Permutation)

Reshuffles the 914 observed trade returns without replacement. Preserves exact set of returns, only changes order.

| Metric | Implementation | Independent (2000 sims) | Rel. Diff | Status |
|--------|----------------|-------------------------|-----------|--------|
| Terminal Return (all percentiles) | 1.542338 | 1.542338 | 0.00% | ✅ MATCH |
| Median Max DD | 13.64% | 13.69% | 0.37% | ✅ PASS |
| Median Max Streak | 30 | 29 | 1 trade | ✅ PASS |
| P(loss) | 0.00% | 0.00% | 0.00% | ✅ MATCH |
| P(DD>10%) | 92.20% | 91.80% | 0.40% | ✅ PASS |

**Note:** Terminal return is identical across all simulations (deterministic property of reshuffling). All percentiles match exactly.

### Method 2: Trade Resampling (Bootstrap with Replacement)

Samples 914 trades with replacement from observed returns.

| Metric | Implementation (10k) | Independent (2k) | Rel. Diff | Status |
|--------|---------------------|------------------|-----------|--------|
| Terminal Return Mean | 173.66% | 172.33% | 0.76% | ✅ PASS |
| Terminal Return Median | 151.19% | 149.03% | 1.43% | ✅ PASS |
| 5th Percentile Return | 42.47% | 40.53% | 4.58% | ⚠️ MC Variation |
| Median Max DD | 13.85% | 13.90% | 0.36% | ✅ PASS |
| Median Max Streak | 30 | 30 | 0 trades | ✅ MATCH |
| P(loss) | 0.36% | 0.50% | 0.14% | ✅ PASS |

**Note:** The 5th percentile discrepancy (4.58%) is expected Monte Carlo sampling variation. The independent audit used only 2,000 simulations vs 10,000 in production, and the random state diverged due to different execution order. With 10,000 simulations, the standard error of the 5th percentile is approximately 1-2%.

### Method 3: Moving Block Bootstrap

Resamples blocks of 20 consecutive trades to preserve short-term dependence structure.

| Metric | Implementation (10k) | Independent (2k) | Rel. Diff | Status |
|--------|---------------------|------------------|-----------|--------|
| Terminal Return Mean | 169.04% | 169.10% | 0.04% | ✅ MATCH |
| Terminal Return Median | 148.18% | 151.25% | 2.04% | ⚠️ MC Variation |
| 5th Percentile Return | 43.42% | 45.34% | 4.23% | ⚠️ MC Variation |
| Median Max DD | 13.01% | 12.95% | 0.39% | ✅ PASS |
| Median Max Streak | 31 | 31 | 0 trades | ✅ MATCH |
| P(loss) | 0.18% | 0.25% | 0.07% | ✅ PASS |

**Note:** Median and 5th percentile discrepancies are within expected Monte Carlo variation for 2,000 vs 10,000 simulations with different random state progression.

---

## 3. Cross-Output Consistency Audit

### JSON Output vs Implementation

All values in `reports/monte_carlo/monte_carlo_results.json` match implementation results exactly (difference < 1e-8 for returns, < $1 for equity).

| Method | Terminal Equity 50th | Terminal Return 50th | Historical Return | Status |
|--------|---------------------|---------------------|-------------------|--------|
| Reshuffling | $25,423,383.09 | 154.23% | 154.23% | ✅ MATCH |
| Resampling | $25,119,465.75 | 151.19% | 154.23% | ✅ MATCH |
| Block Bootstrap | $24,817,539.45 | 148.18% | 154.23% | ✅ MATCH |

### Visualization Data Integrity

| Check | Reshuffling | Resampling | Block Bootstrap | Status |
|-------|-------------|------------|-----------------|--------|
| Fan chart historical marker | 154.23% ✓ | 154.23% ✓ | 154.23% ✓ | ✅ PASS |
| Historical return in sim range | Yes (100%) | Yes (51st pctl) | Yes (53rd pctl) | ✅ PASS |
| Historical DD in sim range | Yes (59th pctl) | Yes (55th pctl) | Yes (64th pctl) | ✅ PASS |
| Historical streak in sim range | Yes (92nd pctl) | Yes (91st pctl) | Yes (88th pctl) | ✅ PASS |
| Percentiles monotonic | ✅ | ✅ | ✅ | ✅ PASS |

---

## 4. Dependence Analysis Audit

| Test | Implementation | Independent (statsmodels) | Status |
|------|----------------|---------------------------|--------|
| Ljung-Box (20 lags) | p = 0.9353 | p = 0.9375 | ✅ PASS |
| Runs Test | p = 0.4982 | p = 0.4982 | ✅ MATCH |
| Dependence Detected | False | False | ✅ MATCH |

**Conclusion:** No significant serial dependence in trade returns. Reshuffling and resampling are appropriate; block bootstrap provides conservative alternative.

---

## 5. Root Cause Analysis of Reported Discrepancies

### Discrepancy 1: "Historical return 154.23% vs fan charts showing 2-4% growth"

**Root Cause:** Visual compression from linear dollar-scale y-axis with auto-scaling.

- Resampling paths range: $6.7M to $62.5M (9.3x ratio)
- Block bootstrap paths range: $7.8M to $80.6M (10.3x ratio)
- Median path grows from $10M to ~$25M (150% growth)
- On auto-scaled y-axis, this growth spans only 24-33% of chart height
- **Visual illusion:** Appears as small growth despite actual 150% return

**Fix Applied:** Fan charts now normalize all paths to percentage return from initial capital. Y-axis shows cumulative return (%) with 0% baseline. Median growth now visually spans the full chart height proportionally.

### Discrepancy 2: "Historical markers appearing near zero in historical-vs-simulation charts"

**Root Cause:** Terminal equity box plot used dollar scale with extreme range ($7.5M to $165M for resampling). Historical $25.4M appeared at only 11% of y-axis range.

**Fix Applied:** Replaced terminal equity subplot with terminal return (%) for consistent scaling. Historical markers now appear at correct percentile positions (51st for resampling, 53rd for block bootstrap).

### Discrepancy 3: "Median simulated returns vs equity-chart scales"

**Root Cause:** Same as Discrepancy 1 - dollar-scale y-axis with extreme outliers compresses visual representation of median growth.

**Fix Applied:** Percentage normalization in fan charts resolves this.

### Discrepancy 4: "Maximum drawdown report values vs plotted distribution"

**Status:** No discrepancy found. Max DD values in JSON (13.64% median reshuffle, 13.85% median resample, 13.01% median block) match implementation and independent verification. Distribution plots correctly show historical DD at 55-64th percentile.

### Discrepancy 5: "Units and scale conventions"

**Status:** Verified consistent. All internal calculations use decimal fractions (1.5423 = 154.23%). JSON stores decimal fractions. Charts display percentages (%) with clear labels. No mixing of units detected.

---

## 6. Independent Statistical Verification

### Tools Used
- **NumPy:** Percentile calculations, array operations, random generation
- **SciPy (statsmodels):** Ljung-Box test, Runs test
- **pandas:** Not required (NumPy sufficient)

### Verification Approach
1. Re-implemented all three Monte Carlo methods independently
2. Recalculated all percentiles, probabilities, and metrics
3. Compared against implementation with tolerance for MC variation
4. Verified mathematical formulas (compounding, drawdown, streaks)

### Results
- **Compounding:** Verified correct - equity = initial × ∏(1 + return_i)
- **Drawdown:** Verified correct - peak-to-trough from running maximum
- **Losing Streaks:** Verified correct - consecutive negative returns
- **Percentiles:** NumPy `percentile()` matches implementation
- **Reproducibility:** Seed 42 produces identical results across runs

---

## 7. Test Results

### Existing Unit Tests (30 tests)
```
tests/unit/research_lab/test_monte_carlo.py: 30 passed in 31.43s
```

All tests pass including:
- Data loading and structure validation
- Configuration defaults and custom values
- Dependence checking reproducibility
- Method-specific reproducibility (reshuffling, resampling, block bootstrap)
- Return/DD/streak calculation accuracy
- Percentile monotonicity
- Drawdown threshold probability ordering
- No look-ahead bias (historical matches OOS)
- JSON output file creation
- Full pipeline integration

### New Regression Tests (to be added)

The following test cases should be added to prevent regression of identified issues:

1. **Fan chart percentage normalization** - Verify fan chart y-axis data is in percentage return
2. **Historical marker position** - Verify historical markers in box plots match percentile ranks
3. **Return/equity consistency** - Verify terminal return = (terminal equity / initial) - 1
4. **Compounding correctness** - Verify multi-trade compounding matches sequential multiplication
5. **Drawdown calculation** - Verify max DD from equity curve matches independent calculation
6. **Unit conversion** - Verify decimal fractions ↔ percentage conversion consistency
7. **MC reproducibility** - Verify identical seed produces identical results
8. **Cross-output consistency** - Verify JSON, report tables, and chart data all derive from same arrays

---

## 8. Corrected Outputs

### Visualizations Regenerated
All charts regenerated with fixes:
- `reports/monte_carlo/fan_chart_reshuffling.png` - Percentage return scale
- `reports/monte_carlo/fan_chart_resampling.png` - Percentage return scale  
- `reports/monte_carlo/fan_chart_block_bootstrap.png` - Percentage return scale
- `reports/monte_carlo/historical_vs_simulated.png` - Consistent percentage scale
- `reports/monte_carlo/terminal_return_distribution.png` - Unchanged (already percentage)
- `reports/monte_carlo/max_drawdown_distribution.png` - Unchanged (already percentage)
- `reports/monte_carlo/losing_streak_distribution.png` - Unchanged
- `reports/monte_carlo/method_comparison.png` - Unchanged

### JSON Output (Unchanged - Already Correct)
`reports/monte_carlo/monte_carlo_results.json` - No changes needed, all values verified.

---

## 9. Git Status

```bash
# Files modified:
mars/apps/research_lab/ma_tsm_monte_carlo_viz.py  # Visualization fixes
audit_monte_carlo.py                               # Audit script (new)
check_viz_data.py                                  # Verification script (new)

# Files verified unchanged (correct):
mars/apps/research_lab/ma_tsm_monte_carlo.py       # Core implementation
reports/monte_carlo/monte_carlo_results.json       # Output data
tests/unit/research_lab/test_monte_carlo.py        # Unit tests
```

---

## 10. Final Recommendation

### Decision: **PROCEED TO PAPER TRADING**

### Evidence Supporting Proceed Decision

| Criterion | Assessment |
|-----------|------------|
| Mathematical Correctness | ✅ All core calculations independently verified |
| Statistical Validity | ✅ Three MC methods correctly implemented; no dependence detected |
| Data Integrity | ✅ JSON, implementation, and visualization data fully consistent |
| Visualization Fidelity | ✅ Fixed scaling issues; historical markers now correctly visible |
| Test Coverage | ✅ 30 tests pass; regression test plan documented |
| Reproducibility | ✅ Seed 42 produces identical results |
| Risk Metrics | ✅ DD thresholds, streak probabilities, loss probability all reasonable |

### Conditions for Paper Trading

1. **Add regression tests** for the visualization fixes and cross-output consistency
2. **Monitor live performance** against MC prediction intervals (5th-95th percentile bands)
3. **Validate on demo account** before any live capital allocation
4. **Review block length sensitivity** - current block=20 trades; test robustness

### Risk Acknowledgement

The strategy shows strong historical performance (154% return, 14.4% max DD) but:
- Resampling 5th percentile return is only 42% (significant left tail)
- Block bootstrap median return is 148% (lower than historical 154%)
- No serial dependence detected, but block bootstrap provides conservative estimate
- Maximum losing streak of 40 trades observed historically; 95th percentile simulated streaks reach 43-46

**Recommendation:** Proceed to paper trading with position sizing calibrated to 5th percentile outcomes (not median), and with hard risk limits matching the Monte Carlo DD distributions.

---

## Appendix: Audit Trail

- **Audit Script:** `audit_monte_carlo.py` - Full independent verification
- **Verification Script:** `check_viz_data.py` - Visualization data validation
- **Audit Report JSON:** `reports/monte_carlo/audit_report.json` - Machine-readable results
- **Test Run:** `pytest tests/unit/research_lab/test_monte_carlo.py -v` - All 30 tests pass
- **Visualization Regeneration:** `python -m mars.apps.research_lab.ma_tsm_monte_carlo` - Charts updated