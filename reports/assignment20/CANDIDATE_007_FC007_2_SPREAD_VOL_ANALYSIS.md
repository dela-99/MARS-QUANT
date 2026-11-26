# M.A.R.S. Quant — Assignment 20
## Candidate 007 FC-007-2 Spread-Volatility Correlation Analysis
### Hard Gate Diagnostic Plan — Must Pass Before Full Backtest

**Date:** 2026-11-25  
**Phase:** Assignment 20 — Phase F Formal Specification Audit and Pre-Backtest Feasibility  
**Candidate:** XAU-ASIAN-VOL-BREAKOUT-007 (Secondary)  
**Authority:** Pre-registered diagnostic plan — **no computation in Assignment 20; execution in Phase G**  
**Reference:** Research Specification Brief §2.6, Gate E Falsification Criterion 2, Advancement Decision Report §2.2

---

## Executive Summary

**FC-007-2 is a HARD GATE.** If the spread-volatility correlation at 08:00 UTC exceeds 0.5, Candidate 007 **terminates immediately** before any full backtest proceeds. This diagnostic runs **first in Phase G (Week 2)** per the Research Specification Brief timeline.

**Core Risk:** High-volatility Asian sessions (the strategy's entry condition) may coincide with widened spreads at 08:00 UTC (Europe open), eroding or eliminating the breakout edge. The correlation measures this joint occurrence.

**Pass Threshold:** Pearson correlation ≤ 0.3  
**Fail Threshold:** Pearson correlation > 0.5  
**Indeterminate:** 0.3 < correlation ≤ 0.5

---

## 1. Correlation Definition (Frozen)

### 1.1 Variables

| Variable | Symbol | Computation | Source |
|----------|--------|-------------|--------|
| **Asian Session Realized Volatility** | `vol_asia` | H1 realized volatility (20-bar lookback) computed over Asian session 00:00-08:00 UTC | Research Brief §2.4 |
| **Spread at 08:00 UTC** | `spread_0800` | M5 spread (points) of the **first M5 bar at 08:00 UTC** (Europe open) | Research Brief §2.4, Instrument Spec |

### 1.2 Correlation Metric

**Pearson Product-Moment Correlation Coefficient:**
```
ρ = Cov(vol_asia, spread_0800) / (σ_vol_asia × σ_spread_0800)
```

**Population:** All trading sessions in the **In-Sample period** (2021-10-16 to 2024-12-31) — approximately 780 sessions.

**Note:** This is a **diagnostic correlation**, not a trading signal correlation. It measures whether the strategy's entry condition (high vol) systematically coincides with high transaction costs at entry.

---

## 2. Data Extraction Specification

### 2.1 Asian Session Realized Volatility (`vol_asia`)

**Source Data:** H1 v1.2.0 bars (resampled from M5 v1.2.0)  
**Time Window:** Asian session 00:00-08:00 UTC (8 H1 bars per session)  
**Lookback:** 20 H1 bars trailing (includes prior sessions)  
**Calculation:**
```
For each session date D:
  1. Identify H1 bars with timestamp in [D 00:00, D 08:00) UTC
  2. Take the last 20 available H1 bars ending at or before D 08:00
  3. Compute realized volatility = std(log(close_t / close_{t-1})) × sqrt(252 × 24)
     (Annualized standard deviation of log returns)
  4. If < 20 bars available (burn-in), mark as NaN → excluded from correlation
```

**Burn-in Handling:** First 60 sessions (2021-07-16 to 2021-10-15) used to initialize trailing window. Correlation computed **only on IS period** (2021-10-16 onward) where full 20-bar history exists.

### 2.2 Spread at 08:00 UTC (`spread_0800`)

**Source Data:** M5 v1.2.0 bars  
**Time Point:** First M5 bar with timestamp **08:00:00 UTC** (Europe session open)  
**Field:** `spread` column (points, broker tick)  
**Handling:**
```
For each session date D:
  1. Find M5 bar where timestamp == D 08:00:00 UTC
  2. Extract spread value (points)
  3. If spread == 0 (98 bars in dataset): substitute dataset median (200 pts) per cost model
  4. If bar missing (feed outage): mark as NaN → excluded from correlation
```

**Zero-Spread Substitution:** Per Assignment 17 Audit §B.3 and Instrument Spec §45-51: 98 bars carry spread == 0; cost model substitutes dataset median spread (200 pts). Same rule applies here.

### 2.3 Session Alignment

| Session Date | vol_asia (H1, 20-bar trailing) | spread_0800 (M5, 08:00 UTC) | Pair Status |
|--------------|--------------------------------|------------------------------|-------------|
| 2021-10-16 | ✅ Computed | ✅ Extracted | ✅ Included |
| 2021-10-17 | ✅ Computed | ✅ Extracted | ✅ Included |
| ... | ... | ... | ... |
| 2024-12-31 | ✅ Computed | ✅ Extracted | ✅ Included |

**Exclusion Criteria:**
- Sessions where `vol_asia` is NaN (insufficient H1 history)
- Sessions where `spread_0800` is NaN (missing M5 bar at 08:00)
- Weekend sessions (no trading) — not in dataset

**Expected Sample Size:** ~780 sessions (IS period) minus ~5-10 for missing data → **~770-775 valid pairs**

---

## 3. Computation Procedure (Phase G Execution)

### 3.1 Step-by-Step Algorithm

```python
# Pseudocode for Phase G execution (pre-registered)

# 1. Load data
m5 = load_parquet("data/processed/xauusdm/m5/v1.2.0/data.parquet")
h1 = load_parquet("data/processed/xauusdm/h1/v1.2.0/data.parquet")

# 2. Define IS period
is_start = "2021-10-16"
is_end = "2024-12-31"

# 3. Compute Asian session realized vol (H1, 20-bar trailing)
asian_h1 = h1.between_time("00:00", "07:59")  # 8 bars per session
vol_asia = compute_trailing_realized_vol(asian_h1, lookback=20, annualize=True)

# 4. Extract spread at 08:00 UTC (M5)
spread_0800 = m5[m5.index.time == time(8, 0)]['spread']
spread_0800 = spread_0800.replace(0, 200)  # Zero-spread substitution

# 5. Align by session date
aligned = pd.DataFrame({'vol': vol_asia, 'spread': spread_0800}).dropna()

# 6. Compute Pearson correlation
rho, p_value = scipy.stats.pearsonr(aligned['vol'], aligned['spread'])

# 7. Decision
if rho <= 0.3:
    status = "PASS"
elif rho > 0.5:
    status = "FAIL"  # HARD GATE — TERMINATE CANDIDATE 007
else:
    status = "INDETERMINATE"
```

### 3.2 Required Outputs

| Output | Format | Description |
|--------|--------|-------------|
| Correlation coefficient (ρ) | Float | Primary metric |
| p-value | Float | Two-sided test of ρ = 0 |
| Sample size (n) | Integer | Valid session pairs |
| Scatter plot | PNG | vol_asia vs spread_0800 with regression line |
| Distribution plots | PNG | Marginal distributions of vol and spread |
| Quantile table | CSV | Correlation by vol quintile (diagnostic) |

---

## 4. Decision Rules (Frozen)

| Correlation (ρ) | Status | Action |
|-----------------|--------|--------|
| **ρ ≤ 0.3** | **PASS** | Proceed to full Candidate 007 backtest (FC-007-1, 3, 4) |
| **0.3 < ρ ≤ 0.5** | **INDETERMINATE** | Proceed with caution; document as risk factor; full backtest runs but Phase K requires additional evidence |
| **ρ > 0.5** | **FAIL** | **HARD GATE TRIGGERED — Candidate 007 TERMINATED immediately. No further research on 007.** |

**No Appeals. No Re-computation. No Parameter Changes.** This is a pre-registered hard gate per Research Brief §2.6 and Advancement Decision Report §2.2.

---

## 5. Diagnostic Extensions (Pre-Registered, Non-Gating)

These analyses run **only if FC-007-2 passes or is indeterminate**. They do not affect the hard gate decision.

### 5.1 Correlation by Volatility Quintile
- Compute ρ within each quintile of `vol_asia`
- Tests whether correlation is driven by extreme vol sessions only

### 5.2 Correlation by Spread Quintile
- Compute ρ within each quintile of `spread_0800`
- Tests asymmetry

### 5.3 Spearman Rank Correlation
- Non-parametric robustness check
- Reported alongside Pearson

### 5.4 Time-Varying Correlation
- Rolling 100-session window correlation
- Tests regime stability of the correlation itself

### 5.5 Conditional Expectancy by Correlation Regime
- Split sessions into low-correlation vs high-correlation periods
- Test whether strategy expectancy differs

---

## 6. Sample Size and Power Considerations

| Parameter | Value | Basis |
|-----------|-------|-------|
| IS Sessions | ~780 | Research Brief §2.5 |
| Expected Valid Pairs | ~770 | After NaN exclusion |
| Minimum for Valid Test | 30 | Statistical convention |
| Power at ρ=0.3 (α=0.05) | > 99% | n=770, two-sided |
| Power at ρ=0.2 (α=0.05) | ~85% | n=770, two-sided |

**Verdict:** Sample size is **more than adequate** for precise correlation estimation. Standard error of ρ ≈ 1/√(n-3) ≈ 0.036. A true ρ of 0.3 would be detected with >99% power.

---

## 7. Risk Factors and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Missing M5 bars at 08:00 | LOW (20 outages max 10 bars) | MEDIUM | NaN exclusion documented; sensitivity with imputation |
| Zero-spread bars at 08:00 | LOW (98 total in dataset) | LOW | Median substitution per verified cost model |
| H1/M5 timestamp misalignment | NONE | N/A | H1 v1.2.0 resampled from M5 v1.2.0 — same grid |
| DST effect on 08:00 UTC | NONE | N/A | Fixed UTC sessions, no DST adjustment |
| Non-stationarity of correlation | MEDIUM | MEDIUM | Rolling window diagnostic (Section 5.4) |

---

## 8. Comparison with Candidate 005

| Aspect | Candidate 005 | Candidate 007 |
|--------|---------------|---------------|
| Spread Regime Filter | Explicit (≤ 40th pctl) | **None** (relies on FC-007-2) |
| Vol Regime Filter | Explicit (≤ 40th pctl) | Explicit (> 60th pctl) |
| Cost Risk at Entry | Filtered out | **Measured by FC-007-2** |
| Hard Gate | None | **FC-007-2 (this analysis)** |

**Key Difference:** Candidate 005 **filters out** high-spread regimes pre-trade. Candidate 007 **trades high-vol regimes** and uses FC-007-2 to verify the cost assumption holds. This is why FC-007-2 is a hard gate for 007 but not needed for 005.

---

## 9. Pre-Registration Checklist

- [x] Correlation definition frozen (Pearson, two variables defined)
- [x] Data sources specified (M5 v1.2.0, H1 v1.2.0)
- [x] Computation procedure specified (trailing vol, 08:00 spread)
- [x] Population defined (IS period sessions)
- [x] Pass/Fail/Indeterminate thresholds frozen
- [x] Hard gate consequence documented (termination)
- [x] Sample size verified adequate
- [x] Diagnostic extensions pre-registered (non-gating)
- [x] Risk factors identified
- [x] No computation in Assignment 20 — execution in Phase G Week 2

---

## 10. Sign-Off

**Diagnostic Plan Pre-Registered:** 2026-11-25  
**Author:** M.A.R.S. Quant Research Pipeline  
**Authorization:** This plan is **frozen**. Execution in Phase G Week 2 per Research Specification Brief timeline. **No modifications permitted.** If ρ > 0.5, Candidate 007 is terminated immediately with no further research.

> **Reminder:** This is a **diagnostic plan only**. No correlation computation occurs in Assignment 20. The actual FC-007-2 test executes in Phase G (In-Sample Research) as the first diagnostic for Candidate 007.

---

*End of Candidate 007 FC-007-2 Spread-Volatility Correlation Analysis*  
*Deliverable 3 of 8 — Assignment 20*